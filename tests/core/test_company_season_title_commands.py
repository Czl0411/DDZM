from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from dzmm_bot.core.commands import is_reserved_command_name
from dzmm_bot.core.schema import (
    BalanceTransactionRecord,
    CompanySeasonTitleRecord,
    OutboundRecord,
    RankRecord,
    UserRecord,
)
from dzmm_bot.runtime.contracts import InboundMessage
from dzmm_bot.core.season_titles import (
    COMPANY_SEASONS,
    COMPANY_SEASON_SETTLEMENTS,
    SEASON_TABLES_METADATA,
)
from tests.core.test_group_commands import _latest_reply, _receive, _service


BEIJING = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=BEIJING)


def _season_context(rank_order: int):
    service, repository, factory = _service()
    SEASON_TABLES_METADATA.create_all(factory.kw["bind"])
    _receive(service, "join", "season-player", "/入职 玩家", NOW)
    with factory.begin() as session:
        user = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == "season-player")
        )
        rank = session.scalar(
            select(RankRecord).where(RankRecord.sort_order == rank_order)
        )
        session.execute(COMPANY_SEASONS.insert().values(code="S2", applied_at=NOW))
        session.execute(
            COMPANY_SEASON_SETTLEMENTS.insert().values(
                id=uuid4(),
                season_code="S2",
                user_id=user.id,
                is_bot=False,
                old_rank_id=rank.id,
                breakdown={"rank": {"sort_order": rank_order}},
            )
        )
    return service, repository, factory


def test_define_season_title_displays_in_me_and_rewards_first_checkin():
    service, _, factory = _season_context(8)

    _receive(
        service,
        "define",
        "season-player",
        "/定义赛季称号 摸鱼先锋",
        NOW,
    )
    assert _latest_reply(factory).startswith("S2 赛季称号已定义为：摸鱼先锋。")

    _receive(service, "me", "season-player", "/我", NOW)
    assert "赛季称号（S2）：摸鱼先锋" in _latest_reply(factory)

    _receive(service, "checkin", "season-player", "/打卡", NOW)
    reply = _latest_reply(factory)
    assert "领取 10 摸鱼币" in reply
    assert "赛季称号权益：+5 摸鱼币" in reply
    with factory() as session:
        user = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == "season-player")
        )
        assert user.balance == 10
        assert sorted(
            (record.source, record.amount)
            for record in session.scalars(
                select(BalanceTransactionRecord)
                .where(BalanceTransactionRecord.user_id == user.id)
                .order_by(BalanceTransactionRecord.occurred_at, BalanceTransactionRecord.id)
            )
        ) == [("checkin", 5), ("season_title_daily", 5)]

    _receive(service, "checkin-again", "season-player", "/打卡", NOW)
    with factory() as session:
        user = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == "season-player")
        )
        assert user.balance == 10

    _receive(
        service,
        "checkin-next-day",
        "season-player",
        "/打卡",
        NOW + timedelta(days=1),
    )
    with factory() as session:
        user = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == "season-player")
        )
        assert user.balance == 20


def test_define_season_title_uses_exact_ineligible_reply():
    service, _, factory = _season_context(7)

    _receive(
        service,
        "define-ineligible",
        "season-player",
        "/定义赛季称号 差一级",
        NOW,
    )

    assert _latest_reply(factory) == (
        "上个赛季你的职位等级不允许你有赛季称号，这个赛季努努力吧"
    )


def test_only_define_season_title_is_player_entry():
    service, _, factory = _season_context(8)

    retired = (
        ("legacy-group", "/赛季称号", "group", None),
        ("legacy-direct", "/修改赛季称号 旧入口", "direct", "dm"),
    )
    for message_id, content, source_type, chatroom_id in retired:
        result = service.receive_inbound(
            InboundMessage(
                message_id,
                "season-player",
                content,
                NOW,
                source_type=source_type,
                chatroom_id=chatroom_id,
            )
        )
        with factory() as session:
            assert session.scalar(
                select(func.count())
                .select_from(OutboundRecord)
                .where(OutboundRecord.inbound_message_id == result.message_id)
            ) == 0
            assert session.scalar(
                select(func.count()).select_from(CompanySeasonTitleRecord)
            ) == 0

    _receive(
        service,
        "define-current-season",
        "season-player",
        "/定义赛季称号 玩家自定",
        NOW,
    )
    with factory() as session:
        assert session.scalar(select(CompanySeasonTitleRecord)).title_name == "玩家自定"

    assert is_reserved_command_name("/赛季称号")
    assert is_reserved_command_name("/修改赛季称号")


def test_basic_help_only_lists_current_season_title_command():
    service, _, factory = _season_context(8)

    _receive(service, "season-help", "season-player", "/帮助 基础", NOW)
    lines = _latest_reply(factory).splitlines()

    assert any(line.startswith("/定义赛季称号 ") for line in lines)
    assert not any(line.startswith("/赛季称号：") for line in lines)
    assert not any(line.startswith("/修改赛季称号 ") for line in lines)
