from datetime import timedelta
from hashlib import sha256
import json
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .schema import (
    AdultCardSessionRecord, AuditEventRecord, ItemRecord, RankRecord,
    ShopCatalogStateRecord, ShopChangeBatchRecord, ShopCommonSenseStateRecord,
    ShopItemUseRecord, ShopSceneJobRecord, UserItemRecord, beijing_now,
)
from .shop_effects import effect_dictionary, effective_config, validate_effect_config


FIELD_LABELS = {
    "operation": "操作", "public_number": "商品编号", "name": "商品名称",
    "description": "商品描述", "price": "价格", "stock": "库存",
    "unlimited_stock": "无限库存", "enabled": "上架状态", "category": "分类",
    "daily_purchase_limit": "每日限购", "minimum_rank_order": "最低职位序号",
    "effect_type": "效果类型", "effect_config": "效果参数", "reward": "赠送金额",
    "reward_min": "随机最小金额", "reward_max": "随机最大金额", "quota": "增加次数",
    "template": "场景模板", "recipient_count": "受邀人数", "duration_minutes": "持续分钟数",
    "system_key": "系统标识", "configuration_version": "配置版本",
    "id": "商品ID", "base_stock": "库存基准", "deleted_at": "删除时间",
}
EDITABLE_FIELDS = (
    "name", "description", "price", "stock", "unlimited_stock", "enabled",
    "category", "daily_purchase_limit", "minimum_rank_order", "effect_type", "effect_config",
)
OPERATIONS = {"新增": "create", "更新": "update", "删除": "delete", "恢复": "restore", "跳过": "skip"}


class ShopChangesPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[dict] = Field(max_length=2000)
    parser_errors: list[dict] = Field(default_factory=list, max_length=60000)
    actor: str = Field(min_length=1, max_length=128)
    super_admin: StrictBool
    synchronize_stock: StrictBool = False


class ShopChangesConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1, max_length=128)
    super_admin: StrictBool
    acknowledgements: list[str] = Field(default_factory=list, max_length=4000)


def shop_issue(row, column, value, message, suggestion):
    return {
        "sheet": "商品列表", "row": row, "column": FIELD_LABELS.get(column, column),
        "value": value if isinstance(value, (str, int, float, bool)) or value is None else str(value),
        "message": message, "suggestion": suggestion,
    }


def shop_snapshot(item):
    return {
        "id": str(item.id), "public_number": item.public_number,
        **{field: getattr(item, field) for field in EDITABLE_FIELDS if field != "effect_config"},
        "effect_config": effective_config(item), "system_key": item.system_key,
        "configuration_version": item.configuration_version,
        "deleted_at": item.deleted_at.isoformat() if item.deleted_at else None,
    }


def shop_fingerprint(snapshot, synchronize_stock):
    values = {key: value for key, value in snapshot.items() if synchronize_stock or key != "stock"}
    return sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ShopManagementMixin:
    def _lock_shop_catalog(self, session):
        dialect = session.get_bind().dialect.name
        if dialect in ("postgresql", "sqlite"):
            insert = postgresql_insert if dialect == "postgresql" else sqlite_insert
            session.execute(insert(ShopCatalogStateRecord).values(id=1).on_conflict_do_nothing())
        elif session.get(ShopCatalogStateRecord, 1) is None:
            session.add(ShopCatalogStateRecord(id=1))
            session.flush()
        session.scalar(select(ShopCatalogStateRecord).where(ShopCatalogStateRecord.id == 1).with_for_update())

    @staticmethod
    def _shop_impacts(session):
        holdings = {
            item_id: {"holders": holders, "quantity": quantity}
            for item_id, holders, quantity in session.execute(
                select(UserItemRecord.item_id, func.count(), func.sum(UserItemRecord.quantity))
                .where(UserItemRecord.quantity > 0).group_by(UserItemRecord.item_id)
            )
        }
        active_ids = set(session.scalars(
            select(ShopItemUseRecord.item_id).where(ShopItemUseRecord.state == "reserved")
        ))
        active_ids.update(session.scalars(
            select(ShopItemUseRecord.item_id)
            .join(AdultCardSessionRecord, AdultCardSessionRecord.item_use_id == ShopItemUseRecord.id)
            .where(AdultCardSessionRecord.state.in_((
                "collecting_scene", "collecting_m_count", "collecting_participants",
                "awaiting_consent", "active", "generating",
            )))
        ))
        active_ids.update(session.scalars(
            select(ShopItemUseRecord.item_id)
            .join(AdultCardSessionRecord, AdultCardSessionRecord.item_use_id == ShopItemUseRecord.id)
            .join(ShopSceneJobRecord, ShopSceneJobRecord.session_id == AdultCardSessionRecord.id)
            .where(ShopSceneJobRecord.status.in_(("pending", "leased", "failed")))
        ))
        active_ids.update(session.scalars(
            select(ShopItemUseRecord.item_id)
            .join(AdultCardSessionRecord, AdultCardSessionRecord.item_use_id == ShopItemUseRecord.id)
            .join(ShopCommonSenseStateRecord, ShopCommonSenseStateRecord.session_id == AdultCardSessionRecord.id)
            .where(ShopCommonSenseStateRecord.state == "active")
        ))
        return holdings, active_ids

    def get_shop_catalog(self, include_deleted=False):
        with self.transaction(), self._session() as session:
            self._lock_shop_catalog(session)
            self._ensure_shop_catalog(session)
            holdings, active_ids = self._shop_impacts(session)
            records = session.scalars(select(ItemRecord).order_by(ItemRecord.public_number))
            return {
                "items": [
                    {**shop_snapshot(item), **holdings.get(item.id, {"holders": 0, "quantity": 0}),
                     "has_active_use": item.id in active_ids}
                    for item in records if include_deleted or item.deleted_at is None
                ],
                "effects": effect_dictionary(),
            }

    @staticmethod
    def _validate_shop_values(values, rank_orders):
        errors = []
        normalized = dict(values)
        for field, maximum, required in (("name", 64, True), ("description", 200, True), ("category", 32, False)):
            value = normalized.get(field)
            if value is None and not required:
                continue
            if not isinstance(value, str) or (required and not value.strip()) or (isinstance(value, str) and len(value.strip()) > maximum):
                errors.append((field, "文字为空、类型无效或长度超限", f"填写{'1–' if required else '不超过 '}{maximum} 字的文字"))
            else:
                normalized[field] = value.strip() or None
        for field, minimum, maximum, nullable in (
            ("price", 0, 999, False), ("stock", 0, 99999, False),
            ("daily_purchase_limit", 0, 99, True), ("minimum_rank_order", 1, 999, True),
        ):
            value = normalized.get(field)
            if value is None and nullable:
                continue
            if type(value) is not int or not minimum <= value <= maximum:
                errors.append((field, "需要范围内的整数", f"填写 {minimum}–{maximum} 的整数" + ("，或留空" if nullable else "")))
        if type(normalized.get("minimum_rank_order")) is int and normalized["minimum_rank_order"] not in rank_orders:
            errors.append(("minimum_rank_order", "职位序号不存在", "从当前后台职位列表选择有效序号"))
        if normalized.get("daily_purchase_limit") == 0:
            normalized["daily_purchase_limit"] = None
        for field in ("enabled", "unlimited_stock"):
            if type(normalized.get(field)) is not bool:
                errors.append((field, "需要是或否", "填写“是”或“否”"))
        if normalized.get("effect_type") == "none":
            normalized["effect_type"] = None
        errors.extend(validate_effect_config(normalized.get("effect_type"), normalized.get("effect_config")))
        return normalized, errors

    def preview_shop_changes(self, rows, actor, super_admin, synchronize_stock=False, parser_errors=None, now=None):
        now = now or beijing_now()
        errors = list(parser_errors or [])
        warnings, changes = [], []
        if not rows:
            errors.append(shop_issue(1, "operation", None, "没有可导入的商品行", "填写商品列表后重新上传"))
        with self.transaction(), self._session() as session:
            self._lock_shop_catalog(session)
            self._ensure_shop_catalog(session)
            records = list(session.scalars(select(ItemRecord).order_by(ItemRecord.public_number)))
            by_number = {item.public_number: item for item in records}
            holdings, active_ids = self._shop_impacts(session)
            rank_orders = set(session.scalars(select(RankRecord.sort_order)))
            seen_numbers = {}
            seen_lines = set()
            final_names = {item.public_number: item.name for item in records}
            for position, row in enumerate(rows, 2):
                line = row.get("row", position)
                if type(line) is not int or not 2 <= line <= 2001:
                    line = position
                raw_operation = row.get("operation")
                operation = OPERATIONS.get(raw_operation, raw_operation) if isinstance(raw_operation, str) else None
                number = row.get("public_number")
                values = row.get("values", {})
                start_errors = len(errors)
                def issue(column, value, message, suggestion):
                    errors.append(shop_issue(line, column, value, message, suggestion))
                if line in seen_lines:
                    issue("operation", line, "操作行号重复", "每条操作使用独立行号，或使用 Excel 模板上传")
                seen_lines.add(line)
                if operation == "skip":
                    continue
                if operation not in ("create", "update", "delete", "restore"):
                    issue("operation", row.get("operation"), "操作不受支持", "填写新增、更新、删除、恢复或跳过")
                    continue
                if operation == "create":
                    if number is not None:
                        issue("public_number", number, "新增商品不能指定编号", "清空编号，由系统自动分配")
                    item = None
                    before = None
                    for field in ("id", "system_key", "configuration_version", "base_stock", "deleted_at"):
                        if row.get(field) is not None:
                            issue(field, row[field], "新增商品的只读标识必须留空", "清空只读标识，由系统生成新商品身份")
                else:
                    if type(number) is not int or number < 1:
                        issue("public_number", number, "商品编号无效", "填写已有商品的正整数编号")
                        continue
                    item = by_number.get(number)
                    if item is None:
                        issue("public_number", number, "商品编号不存在", "检查编号；若要新增，改为新增并清空编号")
                        continue
                    if number in seen_numbers:
                        issue("public_number", number, f"与第 {seen_numbers[number]} 行重复", "每个商品只保留一条操作")
                    seen_numbers[number] = line
                    before = shop_snapshot(item)
                    for field in ("id", "configuration_version", "system_key", "deleted_at"):
                        if field in row and row[field] != before[field]:
                            issue(field, row[field], "只读标识不匹配或配置已变化", "重新导出商品列表，不修改只读列")
                    if synchronize_stock and "base_stock" in row and row["base_stock"] != item.stock:
                        issue("base_stock", row["base_stock"], "导出后库存已变化", "重新导出，或关闭库存同步以保留实时库存")
                    if operation in ("update", "delete") and item.deleted_at is not None:
                        issue("operation", operation, "商品已经删除", "先使用恢复操作；恢复后再编辑")
                    if operation == "restore" and item.deleted_at is None:
                        issue("operation", operation, "商品没有被删除", "改为更新操作")
                if not isinstance(values, dict):
                    issue("operation", values, "商品数据格式错误", "使用最新模板重新填写")
                    continue
                unknown = set(values) - set(EDITABLE_FIELDS)
                for field in sorted(unknown):
                    issue(field, values[field], "字段不允许编辑", "移除未知字段，使用模板中的可编辑列")
                sensitive = operation in ("delete", "restore")
                after = dict(before) if before else {
                    "name": "", "description": "", "price": 0, "stock": 0,
                    "unlimited_stock": False, "enabled": True, "category": None,
                    "daily_purchase_limit": None, "minimum_rank_order": None,
                    "effect_type": None, "effect_config": {}, "system_key": None,
                    "deleted_at": None,
                }
                if operation in ("create", "update"):
                    patch = {field: value for field, value in values.items() if field in EDITABLE_FIELDS}
                    if item is not None and not synchronize_stock:
                        patch.pop("stock", None)
                    after.update(patch)
                    after, validation_errors = self._validate_shop_values(after, rank_orders)
                    for field, message, suggestion in validation_errors:
                        issue(field, after.get(field, after.get("effect_config", {}).get(field) if isinstance(after.get("effect_config"), dict) else None), message, suggestion)
                    sensitive = sensitive or (
                        after.get("effect_type") != (before or {}).get("effect_type")
                        or after.get("effect_config") != (before or {}).get("effect_config", {})
                    )
                    if len(errors) == start_errors:
                        final_names[number if item else f"new:{line}"] = after["name"]
                elif operation == "delete":
                    impact = holdings.get(item.id, {"holders": 0, "quantity": 0})
                    if impact["quantity"] > 0 or item.id in active_ids:
                        issue("operation", "删除", f"仍有 {impact['holders']} 人持有 {impact['quantity']} 件，或存在未完成流程", "先下架，待背包存量和使用流程处理完毕后删除")
                    after["deleted_at"] = now.isoformat()
                    after["enabled"] = False
                else:
                    after["deleted_at"] = None
                    after["enabled"] = False
                if sensitive and not super_admin:
                    issue("operation", operation, "删除、恢复、效果变更需要超级管理员权限", "请超级管理员登录后操作")
                if len(errors) != start_errors:
                    continue
                impact = holdings.get(item.id, {"holders": 0, "quantity": 0}) if item else {"holders": 0, "quantity": 0}
                diff = {
                    field: {"before": (before or {}).get(field), "after": after.get(field)}
                    for field in (*EDITABLE_FIELDS, "deleted_at")
                    if after.get(field) != (before or {}).get(field)
                }
                if sensitive:
                    warnings.append({"code": f"risk:{line}", "row": line,
                        "message": f"高风险操作：{next(label for label, code in OPERATIONS.items() if code == operation)} / 效果变更；影响 {impact['holders']} 人、{impact['quantity']} 件已有商品。未使用商品采用新效果，进行中的流程保留旧效果。"})
                if item and synchronize_stock and "stock" in diff:
                    warnings.append({"code": f"stock:{line}", "row": line, "message": "按 Excel 覆盖实时库存，请确认并非过期库存。"})
                changes.append({"row": line, "operation": operation, "public_number": number,
                    "before": before, "after": after, "diff": diff, "sensitive": sensitive,
                    "impact": {**impact, "has_active_use": bool(item and item.id in active_ids)},
                    "fingerprint": shop_fingerprint(before, synchronize_stock) if before else None})
            name_owners = {}
            for number, name in final_names.items():
                name_owners.setdefault(name, []).append(number)
            for change in changes:
                if change["operation"] in ("create", "update") and len(name_owners[change["after"]["name"]]) > 1:
                    errors.append(shop_issue(change["row"], "name", change["after"]["name"], "整批处理后商品名称重复（含已删除商品）", "修改名称，保证所有商品名称唯一"))
            batch_id = None
            if not errors:
                batch = ShopChangeBatchRecord(actor=actor, created_at=now,
                    expires_at=now + timedelta(minutes=30),
                    plan={"changes": changes, "synchronize_stock": synchronize_stock, "warnings": warnings})
                session.add(batch)
                session.flush()
                batch_id = str(batch.id)
            return {"batch_id": batch_id, "errors": errors, "warnings": warnings,
                "changes": changes, "summary": {
                    "create": sum(change["operation"] == "create" for change in changes),
                    "update": sum(change["operation"] == "update" and bool(change["diff"]) for change in changes),
                    "unchanged": sum(change["operation"] == "update" and not change["diff"] for change in changes),
                    "delete": sum(change["operation"] == "delete" for change in changes),
                    "restore": sum(change["operation"] == "restore" for change in changes),
                    "errors": len(errors), "error_rows": len({error.get("row") for error in errors}),
                }}

    def confirm_shop_changes(self, batch_id, actor, super_admin, acknowledgements, now=None):
        now = now or beijing_now()
        with self.transaction(), self._session() as session:
            self._lock_shop_catalog(session)
            self._ensure_shop_catalog(session)
            batch = session.get(ShopChangeBatchRecord, batch_id, with_for_update=True)
            if batch is None or batch.actor != actor:
                raise LookupError("导入批次不存在或不属于当前管理员")
            if any(change["sensitive"] for change in batch.plan["changes"]) and not super_admin:
                raise PermissionError("此批次需要超级管理员权限")
            if batch.result is not None:
                return batch.result
            if now >= batch.expires_at:
                raise ValueError("预览已超过 30 分钟，请重新上传或重新预览")
            required = {warning["code"] for warning in batch.plan["warnings"]}
            if not required.issubset(set(acknowledgements)):
                raise ValueError("请逐项确认全部风险提醒后再执行")
            changes = batch.plan["changes"]
            records = list(session.scalars(select(ItemRecord).order_by(ItemRecord.public_number).with_for_update()))
            by_number = {item.public_number: item for item in records}
            holdings, active_ids = self._shop_impacts(session)
            for change in changes:
                if change["before"] is None:
                    continue
                item = by_number.get(change["public_number"])
                if item is None or shop_fingerprint(shop_snapshot(item), batch.plan["synchronize_stock"]) != change["fingerprint"]:
                    raise ValueError(f"商品 #{change['public_number']} 配置或库存已变化，请重新预览；本批次未执行")
                if change["operation"] == "delete" and (holdings.get(item.id, {}).get("quantity", 0) or item.id in active_ids):
                    raise ValueError(f"商品 #{item.public_number} 新增了持有或使用记录，请先下架并重新预览；本批次未执行")
                if change["sensitive"] and change["operation"] == "update" and holdings.get(item.id, {"holders": 0, "quantity": 0}) != {key: change["impact"][key] for key in ("holders", "quantity")}:
                    raise ValueError(f"商品 #{item.public_number} 的持有数量已变化，请重新预览影响范围")
            final_names = {item.public_number: item.name for item in records}
            for change in changes:
                if change["operation"] in ("create", "update"):
                    final_names[change["public_number"] if change["before"] else f"new:{change['row']}"] = change["after"]["name"]
            if len(set(final_names.values())) != len(final_names):
                raise ValueError("商品名称发生并发冲突，请重新预览；本批次未执行")
            live_before = {item.public_number: shop_snapshot(item) for item in records}
            for change in changes:
                if change["before"] and "name" in change["diff"]:
                    by_number[change["public_number"]].name = f"__shop_{uuid4().hex}"
            session.flush()
            next_number = self._next_item_public_number(session)
            applied = []
            for change in changes:
                if change["operation"] == "update" and not change["diff"]:
                    continue
                before, after = change["before"], change["after"]
                if before is None:
                    item = ItemRecord(id=uuid4(), public_number=next_number)
                    next_number += 1
                    session.add(item)
                else:
                    item = by_number[change["public_number"]]
                if change["operation"] in ("create", "update"):
                    for field in EDITABLE_FIELDS:
                        if field == "stock" and before and not batch.plan["synchronize_stock"]:
                            continue
                        setattr(item, field, after[field])
                elif change["operation"] == "delete":
                    item.deleted_at = now
                    item.enabled = False
                else:
                    item.deleted_at = None
                    item.enabled = False
                item.configuration_version = (before["configuration_version"] + 1) if before else 1
                applied.append({"row": change["row"], "public_number": item.public_number, "operation": change["operation"]})
                session.add(AuditEventRecord(event_type="shop_item_management", actor=actor,
                    payload={"batch_id": str(batch.id), "row": change["row"], "operation": change["operation"],
                             "before": live_before.get(change["public_number"]), "after": shop_snapshot(item)}, created_at=now))
            batch.result = {"batch_id": str(batch.id), "applied": applied, "count": len(applied)}
            session.flush()
            return batch.result
