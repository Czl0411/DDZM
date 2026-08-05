from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.runtime.contracts import InboundMessage


BEIJING = ZoneInfo("Asia/Shanghai")


def _service():
    from dzmm_bot.core.commands import GroupCommandHandler
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import Base
    from dzmm_bot.core.service import CoreService

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(factory)
    return CoreService(repository, GroupCommandHandler(repository)), repository, factory


def _receive(service, message_id, sender, content, received_at):
    return service.receive_inbound(
        InboundMessage(message_id, sender, content, received_at)
    )


def _latest_reply(factory):
    from dzmm_bot.core.schema import OutboundRecord

    with factory() as session:
        return session.scalar(
            select(OutboundRecord.text).order_by(OutboundRecord.created_at.desc())
        )


def test_join_registers_employee_with_zero_balance_and_beijing_timestamp():
    from dzmm_bot.core.schema import UserRecord

    service, _, factory = _service()
    received_at = datetime(2026, 8, 5, 1, 5, tzinfo=UTC)

    _receive(service, "message-1", "platform-xiaoming", "/入职 小明", received_at)

    with factory() as session:
        employee = session.scalar(select(UserRecord))
        assert employee.platform_id == "platform-xiaoming"
        assert employee.display_name == "小明"
        assert employee.balance == 0
        assert employee.joined_at == received_at.astimezone(BEIJING)
    assert _latest_reply(factory) == "小明，欢迎入职摸鱼公司。当前余额：0 摸鱼币。"


def test_checkin_awards_five_once_per_beijing_date_and_uses_beijing_dates():
    from dzmm_bot.core.schema import DailyCheckinRecord, UserRecord

    service, _, factory = _service()
    _receive(
        service,
        "message-1",
        "platform-xiaoming",
        "/入职 小明",
        datetime(2026, 8, 5, 15, 0, tzinfo=UTC),
    )

    _receive(
        service,
        "message-2",
        "platform-xiaoming",
        "/打卡",
        datetime(2026, 8, 5, 15, 30, tzinfo=UTC),
    )
    assert _latest_reply(factory) == "打卡成功，领取 5 摸鱼币。当前余额：5 摸鱼币。"

    _receive(
        service,
        "message-3",
        "platform-xiaoming",
        "/打卡",
        datetime(2026, 8, 5, 15, 45, tzinfo=UTC),
    )
    assert _latest_reply(factory) == "今天已经打过卡啦，明天再来。"

    _receive(
        service,
        "message-4",
        "platform-xiaoming",
        "/打卡",
        datetime(2026, 8, 5, 16, 0, tzinfo=UTC),
    )
    assert _latest_reply(factory) == "打卡成功，领取 5 摸鱼币。当前余额：10 摸鱼币。"

    with factory() as session:
        employee = session.scalar(select(UserRecord))
        checkins = session.scalars(
            select(DailyCheckinRecord).order_by(DailyCheckinRecord.checkin_date)
        ).all()
        assert employee.balance == 10
        assert [record.checkin_date.isoformat() for record in checkins] == [
            "2026-08-05",
            "2026-08-06",
        ]
        assert checkins[0].checked_in_at.tzinfo == BEIJING


def test_balance_inventory_and_shop_require_employee_and_return_persisted_data():
    service, repository, factory = _service()
    received_at = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)

    _receive(service, "message-1", "platform-xiaoming", "/余额", received_at)
    assert _latest_reply(factory) == "请先用 /入职 名字 加入摸鱼公司。"

    _receive(service, "message-2", "platform-xiaoming", "/入职 小明", received_at)
    _receive(service, "message-3", "platform-xiaoming", "/我的物品", received_at)
    assert _latest_reply(factory) == "小明的物品：\n暂时空空如也。"

    repository.add_item("工位午睡券", "允许正大光明眯十分钟。", 5, 3)
    _receive(service, "message-4", "platform-xiaoming", "/商店", received_at)
    assert _latest_reply(factory) == "总监事小卖部：\n工位午睡券（5 摸鱼币，库存 3）"


def test_disabled_command_does_not_reply_or_change_data():
    from dzmm_bot.core.schema import UserRecord

    service, repository, factory = _service()
    repository.set_command_enabled("/入职", False)

    _receive(
        service,
        "message-1",
        "platform-xiaoming",
        "/入职 小明",
        datetime(2026, 8, 5, 2, 0, tzinfo=UTC),
    )

    with factory() as session:
        assert session.scalar(select(UserRecord)) is None
    assert _latest_reply(factory) is None


def test_custom_checkin_template_receives_current_balance_and_reward():
    """Fails if a successful check-in ignores the administrator's template."""
    service, repository, factory = _service()
    received_at = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)
    repository.set_reply_template(
        "/打卡", "checked_in", "{昵称} 今日 +{打卡奖励}，余额 {余额}"
    )

    _receive(service, "join", "platform-xiaoming", "/入职 小明", received_at)
    _receive(service, "checkin", "platform-xiaoming", "/打卡", received_at)

    assert _latest_reply(factory) == "小明 今日 +5，余额 5"


def test_template_date_uses_the_beijing_calendar_date():
    service, repository, factory = _service()
    repository.set_reply_template("/余额", "shown", "{日期} {昵称}")

    _receive(
        service,
        "join",
        "platform-xiaoming",
        "/入职 小明",
        datetime(2026, 8, 5, 15, 59, tzinfo=UTC),
    )
    _receive(
        service,
        "balance",
        "platform-xiaoming",
        "/余额",
        datetime(2026, 8, 5, 16, 1, tzinfo=UTC),
    )

    assert _latest_reply(factory) == "2026-08-06 小明"


def test_invalid_persisted_template_falls_back_after_checkin_awards_balance():
    from dzmm_bot.core.schema import CommandReplyTemplateRecord, UserRecord

    service, _, factory = _service()
    received_at = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)
    _receive(service, "join", "platform-xiaoming", "/入职 小明", received_at)

    with factory() as session:
        template = session.scalar(
            select(CommandReplyTemplateRecord).where(
                CommandReplyTemplateRecord.command == "/打卡",
                CommandReplyTemplateRecord.scenario == "checked_in",
            )
        )
        template.template = "{商店列表}"
        session.commit()

    _receive(service, "checkin", "platform-xiaoming", "/打卡", received_at)

    assert _latest_reply(factory) == "打卡成功，领取 5 摸鱼币。当前余额：5 摸鱼币。"
    with factory() as session:
        assert session.scalar(select(UserRecord)).balance == 5


def test_help_lists_only_enabled_commands_and_uses_its_template():
    """Fails if help does not reflect the command library or its template."""
    service, repository, factory = _service()
    received_at = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)
    repository.set_command_enabled("/打卡", False)
    repository.set_reply_template("/帮助", "shown", "可用：\n{指令列表}")

    _receive(service, "help", "platform-xiaoming", "/帮助", received_at)

    assert "/帮助" in _latest_reply(factory)
    assert "/打卡" not in _latest_reply(factory)
