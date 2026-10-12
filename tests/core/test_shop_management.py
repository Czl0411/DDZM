from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import (
    Base, PRIMARY_GROUP_CHAT_ID, AuditEventRecord, GroupChatRecord, ItemRecord,
    AdultCardParticipantRecord, AdultCardSessionRecord, OutboundRecord,
    ShopChangeBatchRecord, ShopCommonSenseStateRecord, ShopDailyBonusRecord, ShopItemUseRecord, UserItemRecord,
)
from dzmm_bot.runtime.contracts import InboundMessage


NOW = datetime(2026, 10, 4, 4, tzinfo=UTC)


@pytest.fixture
def shop():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(factory)
    repository.bootstrap_primary_group("https://www.aikda.com/chat?c=shop-management", NOW)
    repository.list_ranks()
    return repository, factory


def item_row(item, values=None, operation="update", **extra):
    return {"row": 2, "operation": operation, "public_number": item["public_number"],
            "id": item["id"], "configuration_version": item["configuration_version"],
            "system_key": item["system_key"], "values": values or {}, **extra}


def create_row(name="测试商品", **values):
    return {"row": 2, "operation": "create", "public_number": None,
            "values": {"name": name, "description": "测试描述", "price": 2, "stock": 10, **values}}


def preview(repository, rows, **options):
    return repository.preview_shop_changes(rows, "超级管理员", True, now=NOW, **options)


def confirm(repository, plan, **options):
    assert not plan["errors"], plan["errors"]
    return repository.confirm_shop_changes(UUID(plan["batch_id"]), "超级管理员", True,
        [warning["code"] for warning in plan["warnings"]], now=NOW, **options)


def inbound(repository, user, content="/购买"):
    record, _ = repository.accept_inbound(InboundMessage(str(uuid4()), user, content, NOW,
        source_type="group", chatroom_id="shop-management"), PRIMARY_GROUP_CHAT_ID)
    return record.id


def test_defaults_and_export_preview_are_noops(shop):
    repository, factory = shop
    catalog = repository.get_shop_catalog()
    plan = preview(repository, [item_row(item, row=line) for line, item in enumerate(catalog["items"], 2)])
    assert plan["summary"]["unchanged"] == 23
    assert not plan["warnings"]
    assert confirm(repository, plan)["count"] == 0
    assert repository.get_shop_catalog() == catalog
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AuditEventRecord)) == 0


def test_create_rename_swap_and_audit_without_changing_ids(shop):
    repository, factory = shop
    confirm(repository, preview(repository, [create_row("甲"), {**create_row("乙"), "row": 3}]))
    items = {item["name"]: item for item in repository.get_shop_catalog()["items"]}
    plan = preview(repository, [item_row(items["甲"], {"name": "乙"}), item_row(items["乙"], {"name": "甲"}, row=3)])
    result = confirm(repository, plan)
    assert result["count"] == 2
    assert confirm(repository, plan) == result
    updated = {item["id"]: item for item in repository.get_shop_catalog()["items"]}
    assert updated[items["甲"]["id"]]["name"] == "乙"
    assert updated[items["乙"]["id"]]["name"] == "甲"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AuditEventRecord)) == 4


def test_validation_returns_all_errors_and_never_stages_invalid_batch(shop):
    repository, factory = shop
    plan = preview(repository, [create_row("", price="十币", stock=-1, effect_type="scratch",
        effect_config={"reward_min": 10, "reward_max": 2}), {**create_row("重复"), "row": 3}, {**create_row("重复"), "row": 4}])
    assert plan["batch_id"] is None
    assert len(plan["errors"]) >= 6
    assert all(error["suggestion"] and error["column"] and error["row"] for error in plan["errors"])
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ShopChangeBatchRecord)) == 0
        assert session.scalar(select(func.count()).select_from(ItemRecord)) == 23


def test_create_rejects_reused_identifiers_and_duplicate_line_numbers(shop):
    repository, _ = shop
    plan = preview(repository, [{**create_row(), "system_key": "gift_basic"}])
    assert any(issue["column"] == "系统标识" for issue in plan["errors"])
    plan = preview(repository, [create_row("甲"), create_row("乙")])
    assert any("行号重复" in issue["message"] for issue in plan["errors"])


@pytest.mark.parametrize("values", [
    {"effect_type": "scratch", "effect_config": {"reward_min": 1}},
    {"effect_type": "none", "effect_config": {"reward": 1}},
    {"effect_type": "adult_scene", "effect_config": {"template": "scratch_a", "recipient_count": 1}},
    {"effect_type": [], "effect_config": {}},
    {"effect_type": "adult_common", "effect_config": {"template": [], "duration_minutes": 60}},
    {"minimum_rank_order": []},
])
def test_invalid_effects_and_rank_are_rejected_without_crashing(shop, values):
    repository, _ = shop
    assert preview(repository, [create_row(**values)])["errors"]


def test_soft_delete_system_item_does_not_respawn_and_restore_is_delisted(shop):
    repository, _ = shop
    item = repository.get_shop_catalog()["items"][0]
    confirm(repository, preview(repository, [item_row(item, operation="delete")]))
    assert len(repository.get_shop_catalog()["items"]) == 22
    deleted = next(entry for entry in repository.get_shop_catalog(True)["items"] if entry["id"] == item["id"])
    assert deleted["deleted_at"] and not deleted["enabled"]
    assert not any(entry.public_number == item["public_number"] for entry in repository.list_active_items())
    confirm(repository, preview(repository, [item_row(deleted, operation="restore")]))
    restored = next(entry for entry in repository.get_shop_catalog()["items"] if entry["id"] == item["id"])
    assert restored["public_number"] == item["public_number"]
    assert restored["deleted_at"] is None and not restored["enabled"]


def test_delete_blocks_existing_and_new_holdings(shop):
    repository, factory = shop
    repository.create_user("buyer", "买家", NOW, 100)
    item = next(entry for entry in repository.get_shop_catalog()["items"] if entry["system_key"] == "scratch_a")
    plan = preview(repository, [item_row(item, operation="delete")])
    purchase = repository.purchase_shop_item(inbound(repository, "buyer"), "buyer", item["public_number"], PRIMARY_GROUP_CHAT_ID, NOW)
    assert purchase.status == "purchased"
    with pytest.raises(ValueError, match="新增了持有"):
        confirm(repository, plan)
    blocked = preview(repository, [item_row(item, operation="delete")])
    assert "仍有 1 人持有 1 件" in blocked["errors"][0]["message"]
    assert repository.get_shop_catalog()["items"]
    with factory() as session:
        assert session.scalar(select(UserItemRecord.quantity)) == 1


def test_stock_is_preserved_unless_explicitly_synchronized(shop):
    repository, factory = shop
    confirm(repository, preview(repository, [create_row()]))
    item = repository.get_shop_catalog()["items"][-1]
    plan = preview(repository, [item_row(item, {"stock": 99, "price": 3})])
    with factory.begin() as session:
        session.get(ItemRecord, UUID(item["id"])).stock = 9
    confirm(repository, plan)
    current = repository.get_shop_catalog()["items"][-1]
    assert current["stock"] == 9 and current["price"] == 3
    with factory() as session:
        audit = session.scalar(select(AuditEventRecord).where(AuditEventRecord.payload["operation"].as_string() == "update"))
        assert audit.payload["before"]["stock"] == audit.payload["after"]["stock"] == 9
    plan = preview(repository, [item_row(current, {"stock": 20}, base_stock=9)], synchronize_stock=True)
    assert plan["warnings"]
    with factory.begin() as session:
        session.get(ItemRecord, UUID(item["id"])).stock = 8
    with pytest.raises(ValueError, match="配置或库存已变化"):
        confirm(repository, plan)
    current = repository.get_shop_catalog()["items"][-1]
    confirm(repository, preview(repository, [item_row(current, {"stock": 20}, base_stock=8)], synchronize_stock=True))
    assert repository.get_shop_catalog()["items"][-1]["stock"] == 20


def test_permissions_risk_confirmation_and_batch_ownership(shop):
    repository, _ = shop
    item = repository.get_shop_catalog()["items"][0]
    for operation, values in (("delete", {}), ("update", {"effect_type": None, "effect_config": {}})):
        result = repository.preview_shop_changes([item_row(item, values, operation)], "普通管理员", False, now=NOW)
        assert any("超级管理员" in error["message"] for error in result["errors"])
    allowed = repository.preview_shop_changes([create_row()], "普通管理员", False, now=NOW)
    assert not allowed["errors"]
    plan = preview(repository, [item_row(item, operation="delete")])
    with pytest.raises(ValueError, match="逐项确认"):
        repository.confirm_shop_changes(UUID(plan["batch_id"]), "超级管理员", True, [], now=NOW)
    with pytest.raises(LookupError):
        repository.confirm_shop_changes(UUID(plan["batch_id"]), "其他管理员", True, [], now=NOW)
    with pytest.raises(PermissionError):
        repository.confirm_shop_changes(UUID(plan["batch_id"]), "超级管理员", False, [], now=NOW)
    with pytest.raises(ValueError, match="30 分钟"):
        repository.confirm_shop_changes(UUID(plan["batch_id"]), "超级管理员", True, [], now=NOW + timedelta(minutes=31))


def test_entire_batch_rolls_back_when_database_write_fails(shop, monkeypatch):
    repository, factory = shop
    plan = preview(repository, [create_row("甲"), {**create_row("乙"), "row": 3}])
    from dzmm_bot.core import shop_management
    original = shop_management.shop_snapshot
    def fail_on_second(item):
        if item.name == "乙":
            raise RuntimeError("injected failure")
        return original(item)
    monkeypatch.setattr(shop_management, "shop_snapshot", fail_on_second)
    with pytest.raises(RuntimeError, match="injected failure"):
        confirm(repository, plan)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ItemRecord)) == 23
        assert session.scalar(select(func.count()).select_from(AuditEventRecord)) == 0
        assert session.get(ShopChangeBatchRecord, UUID(plan["batch_id"])).result is None


@pytest.mark.parametrize("effect_type, config, expected", [
    ("scratch", {"reward_min": 17, "reward_max": 17}, 17),
    ("ai_quota", {"quota": 3}, 3),
    ("multiplayer_quota", {"quota": 4}, 4),
])
def test_custom_item_effects_execute_and_history_keeps_original_name(shop, effect_type, config, expected):
    repository, factory = shop
    confirm(repository, preview(repository, [create_row(effect_type=effect_type, effect_config=config)]))
    item = repository.get_shop_catalog()["items"][-1]
    repository.create_user("buyer", "买家", NOW, 100)
    assert repository.purchase_shop_item(inbound(repository, "buyer"), "buyer", item["public_number"], PRIMARY_GROUP_CHAT_ID, NOW).status == "purchased"
    confirm(repository, preview(repository, [item_row(item, {"name": "改名后"})]))
    used = repository.use_ordinary_shop_item(inbound(repository, "buyer", "/使用"), "buyer", item["public_number"], PRIMARY_GROUP_CHAT_ID, NOW)
    assert used.status == "completed" and used.reward == expected
    renamed = repository.get_shop_catalog()["items"][-1]
    confirm(repository, preview(repository, [item_row(renamed, {"name": "再次改名"})]))
    activity = repository.list_shop_admin_activity()
    assert activity["purchases"][0]["item_name"] == "测试商品"
    assert activity["uses"][0]["item_name"] == "改名后"
    if effect_type != "scratch":
        with factory() as session:
            bonus = session.scalar(select(ShopDailyBonusRecord))
            assert (bonus.ai_total if effect_type == "ai_quota" else bonus.multiplayer_total) == expected


def test_ongoing_adult_session_uses_snapshot_and_delete_is_blocked(shop):
    repository, factory = shop
    repository.create_user("buyer", "买家", NOW, 200)
    repository.create_user("target", "目标", NOW, 100)
    repository.upsert_direct_chats([("buyer", "direct-room")], NOW)
    with factory.begin() as session:
        session.get(GroupChatRecord, PRIMARY_GROUP_CHAT_ID).adult_shop_enabled = True
    item = next(entry for entry in repository.get_shop_catalog()["items"] if entry["system_key"] == "adult_flirt")
    assert repository.purchase_shop_item(inbound(repository, "buyer"), "buyer", item["public_number"], PRIMARY_GROUP_CHAT_ID, NOW).status == "purchased"
    started = repository.start_adult_shop_item(inbound(repository, "buyer", "/使用"), "buyer", item["public_number"], PRIMARY_GROUP_CHAT_ID, NOW, target_platform_id="target")
    assert started.status == "scene_required"
    assert preview(repository, [item_row(item, operation="delete")])["errors"]
    confirm(repository, preview(repository, [item_row(item, {"name": "改成公告卡", "effect_type": "adult_m", "effect_config": {}})]))
    consumed = repository.consume_adult_card_scene("buyer", "测试场景", NOW)
    assert consumed.status == "awaiting_consent"
    assert consumed.item.name == "发骚卡" and consumed.item.effect_type == "adult_scene"
    with factory() as session:
        use = session.scalar(select(ShopItemUseRecord))
        assert use.item_snapshot["effect_type"] == "adult_scene"
        assert use.item_snapshot["name"] == "发骚卡"


def test_held_custom_item_uses_new_gift_effect(shop):
    repository, _ = shop
    confirm(repository, preview(repository, [create_row()]))
    item = repository.get_shop_catalog()["items"][-1]
    repository.create_user("buyer", "买家", NOW, 100)
    repository.create_user("target", "目标", NOW, 0)
    purchase_id = inbound(repository, "buyer")
    assert repository.purchase_shop_item(purchase_id, "buyer", item["public_number"], PRIMARY_GROUP_CHAT_ID, NOW).status == "purchased"
    plan = preview(repository, [item_row(item, {"effect_type": "gift", "effect_config": {"reward": 5}, "name": "新赠送卡"})])
    assert plan["changes"][0]["impact"]["quantity"] == 1
    confirm(repository, plan)
    use_id = inbound(repository, "buyer", "/使用")
    used = repository.use_ordinary_shop_item(use_id, "buyer", item["public_number"], PRIMARY_GROUP_CHAT_ID, NOW, target_platform_id="target")
    assert used.status == "completed" and used.reward == 5
    assert repository.find_user("target").balance == 5
    current = repository.get_shop_catalog()["items"][-1]
    confirm(repository, preview(repository, [item_row(current, {"effect_type": "ai_quota", "effect_config": {"quota": 3}, "name": "改成次数卡"})]))
    replayed = repository.use_ordinary_shop_item(use_id, "buyer", item["public_number"], PRIMARY_GROUP_CHAT_ID, NOW)
    assert replayed.reward == 5 and replayed.item.effect_type == "gift" and replayed.item.name == "新赠送卡"
    replayed_purchase = repository.purchase_shop_item(purchase_id, "buyer", item["public_number"], PRIMARY_GROUP_CHAT_ID, NOW)
    assert replayed_purchase.item.name == "测试商品"


def test_effect_change_cannot_bypass_adult_group_switch(shop):
    repository, _ = shop
    item = next(entry for entry in repository.get_shop_catalog()["items"] if entry["system_key"] == "ai_quota")
    confirm(repository, preview(repository, [item_row(item, {"effect_type": "adult_scene",
        "effect_config": {"template": "adult_flirt", "recipient_count": 1}})]))
    repository.create_user("buyer", "买家", NOW, 100)
    result = repository.purchase_shop_item(inbound(repository, "buyer"), "buyer", item["public_number"], PRIMARY_GROUP_CHAT_ID, NOW)
    assert result.status == "adult_disabled"
    assert not any(entry.public_number == item["public_number"] for entry in repository.list_shop_items())


def test_timed_state_uses_configured_duration_snapshot_after_edits(shop):
    repository, factory = shop
    confirm(repository, preview(repository, [create_row(effect_type="adult_common",
        effect_config={"template": "adult_common_1h", "duration_minutes": 7})]))
    item = repository.get_shop_catalog()["items"][-1]
    repository.create_user("buyer", "买家", NOW, 100)
    repository.create_user("target", "目标", NOW, 0)
    repository.upsert_direct_chats([("buyer", "direct-room")], NOW)
    with factory.begin() as session:
        session.get(GroupChatRecord, PRIMARY_GROUP_CHAT_ID).adult_shop_enabled = True
    assert repository.purchase_shop_item(inbound(repository, "buyer"), "buyer", item["public_number"], PRIMARY_GROUP_CHAT_ID, NOW).status == "purchased"
    started = repository.start_adult_shop_item(inbound(repository, "buyer", "/使用"), "buyer", item["public_number"], PRIMARY_GROUP_CHAT_ID, NOW, target_platform_id="target")
    assert started.status == "scene_required"
    confirm(repository, preview(repository, [item_row(item, {"effect_type": None, "effect_config": {}, "price": 99})]))
    assert repository.consume_adult_card_scene("buyer", "测试状态", NOW).status == "awaiting_consent"
    with factory.begin() as session:
        participant = session.scalar(select(AdultCardParticipantRecord))
        session.get(OutboundRecord, participant.authorization_outbound_id).platform_sent_id = "auth"
    assert repository.decide_adult_card_consent("target", "auth", True, NOW).status == "all_approved"
    with factory() as session:
        state = session.scalar(select(ShopCommonSenseStateRecord))
        assert state.ends_at - state.starts_at == timedelta(minutes=7)
        assert session.scalar(select(AdultCardSessionRecord)).state == "active"
