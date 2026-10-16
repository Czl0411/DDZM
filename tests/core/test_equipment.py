from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.commands import GroupCommandHandler
from dzmm_bot.core.equipment import DEFAULT_EQUIPMENT, EQUIPMENT_COMMANDS
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import (
    BalanceTransactionRecord, Base, EquipmentItemRecord, EquipmentOwnershipRecord,
    EquipmentPurchaseRecord, OutboundRecord, PRIMARY_GROUP_CHAT_ID, UserItemRecord,
)
from dzmm_bot.core.service import CoreService
from dzmm_bot.runtime.contracts import InboundMessage


NOW = datetime(2026, 10, 15, 12, tzinfo=ZoneInfo("Asia/Shanghai"))


@pytest.fixture
def context():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, connection_record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(factory)
    repository.bootstrap_primary_group("https://www.aikda.com/chat?c=group-main", NOW)
    handler = GroupCommandHandler(repository)
    service = CoreService(repository, handler)
    context = service, repository, factory
    receive(context, "join", "/入职 糯糯")
    user = repository.find_user("user-1")
    repository.record_balance_change(user.id, 128 - user.balance, "board_bonus", NOW)
    yield context
    engine.dispose()


def receive(context, message_id, content, sender="user-1", **options):
    service, _, factory = context
    options.setdefault("chatroom_id", "group-main")
    message = InboundMessage(message_id, sender, content, NOW, **options)
    result = service.receive_inbound(message)
    with factory() as session:
        return "\n".join(session.scalars(select(OutboundRecord.text).where(
            OutboundRecord.inbound_message_id == result.message_id
        ).order_by(OutboundRecord.reply_index)))


def count(factory, model):
    with factory() as session:
        return session.scalar(select(func.count()).select_from(model))


def test_equipment_catalog_is_separate_and_purchases_do_not_auto_equip(context):
    _, repository, factory = context
    ordinary_before = repository.list_shop_items(PRIMARY_GROUP_CHAT_ID)
    catalog = receive(context, "catalog", "/装备商城")
    assert "【装备商城】" in catalog
    assert "#1 主显示器" in catalog
    assert "预计 +2 摸鱼币/日" in catalog
    assert "主显示器" not in receive(context, "ordinary-shop", "/商店")
    assert "主显示器" in receive(context, "alias", "/装备商店")
    assert ordinary_before == repository.list_shop_items(PRIMARY_GROUP_CHAT_ID)
    assert "当前余额：92" in receive(context, "purchase", "/购买装备 1")
    assert "未装备" in receive(context, "inventory", "/我的装备")
    assert repository.find_user("user-1").balance == 92
    assert not next(item for item in repository.list_equipment("user-1") if item.number == 1).equipped
    assert count(factory, EquipmentPurchaseRecord) == 1
    assert count(factory, EquipmentOwnershipRecord) == 1
    with factory() as session:
        ledger = session.scalars(select(BalanceTransactionRecord).where(
            BalanceTransactionRecord.source == "equipment_purchase"
        )).all()
        assert [row.amount for row in ledger] == [-36]


def test_duplicate_delivery_and_new_purchase_attempt_only_charge_once(context):
    _, repository, factory = context
    first = receive(context, "purchase", "/购买装备 1")
    assert receive(context, "purchase", "/购买装备 1") == first
    result = repository.purchase_equipment("purchase", "user-1", 1, PRIMARY_GROUP_CHAT_ID, NOW)
    assert result.status == "purchased"
    assert result.balance == 92
    assert "无需重复购买" in receive(context, "purchase-again", "/购买装备 1")
    assert repository.purchase_equipment("purchase", "user-1", 2, PRIMARY_GROUP_CHAT_ID, NOW).status == "request_conflict"
    assert repository.find_user("user-1").balance == 92
    assert count(factory, EquipmentPurchaseRecord) == 1


def test_equipping_and_ownership_are_shared_across_groups_and_survive_removal(context):
    _, repository, factory = context
    repository.create_group_chat("第二群", "https://www.aikda.com/chat?c=group-other", True, True, False, False, NOW)
    receive(context, "purchase", "/购买装备 1")
    assert "已装备 主显示器" in receive(context, "equip", "/装备 1", chatroom_id="group-other")
    assert "已经装备" in receive(context, "equip-again", "/装备 1")
    assert "预计工位日收入：2" in receive(context, "workstation", "/我的工位")
    assert "糯糯的工位" in receive(context, "workstation-name", "/我的工位")
    assert "已装备" in receive(context, "inventory", "/我的装备", chatroom_id="group-other")
    assert "已卸下 主显示器" in receive(context, "remove", "/卸下 1")
    assert "当前未装备" in receive(context, "remove-again", "/卸下 1")
    assert "预计工位日收入：0" in receive(context, "empty-workstation", "/我的工位")
    assert repository.find_user("user-1").balance == 92
    assert count(factory, EquipmentOwnershipRecord) == 1


def test_insufficient_balance_unowned_and_nonexistent_equipment(context):
    _, repository, factory = context
    receive(context, "purchase-pc", "/购买装备 9")
    receive(context, "purchase-chair", "/购买装备 10")
    assert "余额不足" in receive(context, "too-expensive", "/购买装备 1")
    assert repository.find_user("user-1").balance == 24
    assert count(factory, EquipmentPurchaseRecord) == 2
    assert count(factory, EquipmentOwnershipRecord) == 2
    assert "尚未拥有" in receive(context, "unowned", "/装备 1")
    assert "编号不存在" in receive(context, "missing", "/购买装备 999")
    assert "预计工位日收入：0" in receive(context, "unowned-workstation", "/我的工位")


@pytest.mark.parametrize("content", ["/购买装备", "/购买装备 -1", "/购买装备 0", "/装备 abc", "/卸下 1 2", "/购买装备 １", "/购买装备 9999999999", "/装备商城 1", "/我的装备 1"])
def test_invalid_arguments_never_charge(context, content):
    _, repository, factory = context
    assert "用法" in receive(context, "invalid", content)
    assert repository.find_user("user-1").balance == 128
    assert count(factory, EquipmentPurchaseRecord) == 0


@pytest.mark.parametrize("command", sorted(EQUIPMENT_COMMANDS | {"/装备商店"}))
def test_equipment_commands_reject_direct_messages(context, command):
    content = f"{command} 1" if command in {"/购买装备", "/装备", "/卸下"} else command
    assert "群聊" in receive(context, "direct", content, source_type="direct", chatroom_id="dm-1")


def test_not_joined_and_disabled_commands(context):
    _, repository, factory = context
    assert "主显示器" in receive(context, "visitor-shop", "/装备商城", sender="visitor")
    assert "先使用 /入职" in receive(context, "visitor-buy", "/购买装备 1", sender="visitor")
    assert "先使用 /入职" in receive(context, "visitor-owned", "/我的装备", sender="visitor")
    repository.set_command_enabled("/购买装备", False)
    assert receive(context, "disabled-buy", "/购买装备 1") == ""
    assert repository.find_user("user-1").balance == 128


def test_catalog_seed_preserves_configuration_and_delisted_ownership(context):
    _, repository, factory = context
    receive(context, "catalog", "/装备商城")
    with factory.begin() as session:
        item = session.scalar(select(EquipmentItemRecord).where(EquipmentItemRecord.public_number == 1))
        item.price = 7
        item.daily_income = 4
    assert "花费 7" in receive(context, "purchase", "/购买装备 1")
    with factory.begin() as session:
        item = session.scalar(select(EquipmentItemRecord).where(EquipmentItemRecord.public_number == 1))
        item.enabled = False
    assert "#1 主显示器" not in receive(context, "catalog-again", "/装备商城")
    assert "主显示器" in receive(context, "owned-delisted", "/我的装备")
    assert "预计工位日收入：4" in receive(context, "equip-delisted", "/装备 1")
    assert "预计工位日收入：4" in receive(context, "workstation", "/我的工位")
    assert repository.find_user("user-1").balance == 121
    assert len(repository.list_equipment("visitor")) == len(DEFAULT_EQUIPMENT) - 1


def test_transaction_rolls_back_deduction_and_inventory_on_failure(context, monkeypatch):
    _, repository, factory = context
    receive(context, "catalog", "/装备商城")
    message = InboundMessage("purchase-failed", "user-1", "/购买装备 1", NOW, chatroom_id="group-main")
    repository.accept_inbound(message, PRIMARY_GROUP_CHAT_ID)
    original = repository._apply_balance_change

    def fail_after_deduction(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("simulated storage failure")

    monkeypatch.setattr(repository, "_apply_balance_change", fail_after_deduction)
    with pytest.raises(RuntimeError, match="simulated storage failure"):
        repository.purchase_equipment("purchase-failed", "user-1", 1, PRIMARY_GROUP_CHAT_ID, NOW)
    assert repository.find_user("user-1").balance == 128
    assert count(factory, EquipmentPurchaseRecord) == 0
    assert count(factory, EquipmentOwnershipRecord) == 0
    with factory() as session:
        assert not session.scalar(select(BalanceTransactionRecord).where(BalanceTransactionRecord.source == "equipment_purchase"))


def test_equipment_help_is_independent(context):
    assert "/帮助 装备商城" in receive(context, "help", "/帮助")
    help_text = receive(context, "equipment-help", "/帮助 装备商城")
    for command in EQUIPMENT_COMMANDS:
        assert command in help_text


def test_normal_shop_purchase_and_use_are_not_routed_to_equipment(context):
    _, repository, factory = context
    ordinary = next(item for item in repository.list_shop_items(PRIMARY_GROUP_CHAT_ID) if item.system_key == "ai_quota")
    receive(context, "equipment-buy", "/购买装备 5")
    assert repository.find_user("user-1").balance == 106
    reply = receive(context, "ordinary-buy", f"/购买 {ordinary.public_number}")
    assert ordinary.name in reply
    assert repository.find_user("user-1").balance == 106 - ordinary.price
    assert "机械键盘" not in receive(context, "ordinary-items", "/我的物品")
    receive(context, "ordinary-use", f"/使用 {ordinary.public_number}")
    assert count(factory, EquipmentPurchaseRecord) == 1
    assert count(factory, UserItemRecord) == 1
    assert "未装备" in receive(context, "equipment-items", "/我的装备")


def test_purchase_is_blocked_when_delisted_and_users_have_separate_ownership(context):
    _, repository, factory = context
    receive(context, "equipment-buy", "/购买装备 1")
    receive(context, "join-second", "/入职 同事", sender="user-2")
    assert "尚未拥有" in receive(context, "other-equip", "/装备 1", sender="user-2")
    with factory.begin() as session:
        item = session.scalar(select(EquipmentItemRecord).where(EquipmentItemRecord.public_number == 1))
        item.enabled = False
    assert "已下架" in receive(context, "delisted-buy", "/购买装备 1", sender="user-2")
    assert count(factory, EquipmentOwnershipRecord) == 1
    with pytest.raises(ValueError, match="入站消息不存在"):
        repository.purchase_equipment("equipment-buy", "user-2", 1, PRIMARY_GROUP_CHAT_ID, NOW)
