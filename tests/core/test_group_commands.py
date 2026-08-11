from datetime import UTC, datetime, timedelta
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
        latest = session.scalar(
            select(OutboundRecord).order_by(OutboundRecord.created_at.desc())
        )
        if latest is None:
            return None
        if latest.inbound_message_id is None:
            return latest.text
        return "\n".join(
            session.scalars(
                select(OutboundRecord.text)
                .where(OutboundRecord.inbound_message_id == latest.inbound_message_id)
                .order_by(OutboundRecord.reply_index)
            )
        )


def _replies_for(factory, inbound_id):
    from dzmm_bot.core.schema import OutboundRecord

    with factory() as session:
        return list(
            session.scalars(
                select(OutboundRecord.text)
                .where(OutboundRecord.inbound_message_id == inbound_id)
                .order_by(OutboundRecord.reply_index)
            )
        )


def test_join_registers_employee_with_zero_balance_and_beijing_timestamp():
    from dzmm_bot.core.schema import UserRecord

    service, repository, factory = _service()
    received_at = datetime(2026, 8, 5, 1, 5, tzinfo=UTC)

    _receive(service, "message-1", "platform-xiaoming", "/入职 小明", received_at)

    with factory() as session:
        employee = session.scalar(select(UserRecord))
        assert employee.platform_id == "platform-xiaoming"
        assert employee.display_name == "小明"
        assert employee.balance == 0
        assert employee.joined_at == received_at.astimezone(BEIJING)
    assert _latest_reply(factory) == "小明，欢迎入职摸鱼公司。当前余额：0 摸鱼币。"


def test_number_bomb_group_commands_start_join_and_reject_group_reports():
    service, repository, factory = _service()
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    for index in range(1, 4):
        _receive(service, f"join-{index}", f"bomb-p{index}", f"/入职 炸弹{index}", now)
    repository.upsert_direct_chats(
        [(f"bomb-p{index}", f"direct-bomb-p{index}") for index in range(1, 4)],
        now,
    )

    _receive(service, "bad-start", "bomb-p1", "/蹦蹦数字炸弹 6", now)
    assert _latest_reply(factory) == "请直接发送 /蹦蹦数字炸弹 创建报名局。"
    _receive(service, "start", "bomb-p1", "/蹦蹦数字炸弹", now)
    assert "炸弹1 发起了报名，当前 1 人" in _latest_reply(factory)
    _receive(service, "add-2", "bomb-p2", "/加入", now)
    assert "当前 2 人" in _latest_reply(factory)
    _receive(service, "add-3", "bomb-p3", "/加入", now)
    assert "当前 3 人" in _latest_reply(factory)
    _receive(service, "manual-start", "bomb-p2", "/开始", now)
    started = _latest_reply(factory)
    assert "第 1 轮 - 真心话" in started
    assert "参与者：炸弹1、炸弹2、炸弹3" in started
    assert started.count("请按这个格式报数给我 /报数 数字") == 3

    _receive(service, "group-report", "bomb-p1", "/报数 29", now)
    assert _latest_reply(factory) == "请私聊总监事发送 /报数 1-100，群内报数不会生效。"


def test_current_game_reports_number_bomb_and_next_commands():
    service, repository, factory = _service()
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    repository.create_user("current-p1", "甲", now, 20)
    repository.upsert_direct_chats([("current-p1", "direct-current-p1")], now)
    repository.start_number_bomb_game("current-p1", now)

    _receive(service, "current-game", "current-p1", "/当前游戏", now)

    reply = _latest_reply(factory)
    assert "蹦蹦数字炸弹" in reply
    assert "报名中" in reply
    assert "/开始" in reply


def test_number_bomb_skip_command_removes_targets_from_entire_game():
    service, repository, factory = _service()
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    for index in range(1, 6):
        repository.create_user(f"skip-command-p{index}", f"跳过玩家{index}", now, 0)
        repository.upsert_direct_chats(
            [(f"skip-command-p{index}", f"direct-skip-command-p{index}")], now
        )
    repository.start_number_bomb_game("skip-command-p1", now)
    for index in range(2, 6):
        repository.join_number_bomb_game(f"skip-command-p{index}", now)
    repository.start_number_bomb_round("skip-command-p1", now)

    _receive(service, "skip-early", "skip-command-p1", "/跳过 2", now)
    assert "首次未报数提醒后" in _latest_reply(factory)
    repository.run_number_bomb_jobs(now + timedelta(seconds=15))
    _receive(service, "skip-batch", "skip-command-p1", "/跳过 2 4", now)

    reply = _latest_reply(factory)
    assert "2号 跳过玩家2" in reply
    assert "4号 跳过玩家4" in reply
    assert "已从整场移除" in reply
    assert [(player.roster_order, player.state) for player in repository.number_bomb_game_summary().players] == [
        (1, "current"), (3, "current"), (5, "current")
    ]


def test_end_game_hits_waiting_memory_duel_instead_of_undercover_fallback():
    service, repository, factory = _service()
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    repository.create_user("memory-host", "甲", now, 20)
    repository.start_memory_assessment_duel("memory-host", now)

    _receive(service, "end-memory", "memory-host", "/结束游戏", now)

    reply = _latest_reply(factory)
    assert "记忆考核" in reply
    assert "谁是卧底" not in reply
    assert repository.active_gameplay_summary("memory-host", now).game_type is None


def test_generic_exit_cancels_waiting_memory_duel_immediately():
    service, repository, factory = _service()
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    repository.create_user("memory-exit-host", "甲", now, 20)
    repository.start_memory_assessment_duel("memory-exit-host", now)

    _receive(service, "exit-memory", "memory-exit-host", "/退出", now)

    assert "已取消" in _latest_reply(factory)
    assert repository.active_gameplay_summary("memory-exit-host", now).game_type is None
    assert repository.find_user("memory-exit-host").balance == 20


def test_board_member_can_force_end_another_players_memory_assessment():
    from dzmm_bot.core.schema import RankRecord, UserRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
    repository.create_user("memory-player", "记忆玩家", now, 0)
    repository.create_user("board", "董事", now, 0)
    with factory.begin() as session:
        board_rank = session.scalar(
            select(RankRecord).where(RankRecord.is_board.is_(True))
        )
        board = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == "board")
        )
        assert board_rank is not None
        assert board is not None
        board.rank_id = board_rank.id
    repository.start_memory_assessment_single("memory-player", now)

    _receive(service, "board-force-end", "board", "/结束游戏", now)

    assert repository.active_gameplay_summary("board", now).game_type is None
    assert _latest_reply(factory) == "【记忆考核】管理员已强制结束当前游戏。"


def test_nonboard_group_manager_cannot_force_end_another_players_game():
    from dzmm_bot.core.schema import RankRecord, UserRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
    repository.create_user("memory-player", "记忆玩家", now, 0)
    repository.create_user("manager", "负责人", now, 0)
    with factory.begin() as session:
        manager_rank = session.scalar(
            select(RankRecord).where(
                RankRecord.has_group_management.is_(True),
                RankRecord.is_board.is_(False),
            )
        )
        manager = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == "manager")
        )
        assert manager_rank is not None
        assert manager is not None
        manager.rank_id = manager_rank.id
    repository.start_memory_assessment_single("memory-player", now)

    _receive(service, "manager-force-end", "manager", "/结束游戏", now)

    assert _latest_reply(factory) == (
        "已命中当前记忆考核；对战开始后请发送 /退出 执行投降，"
        "等待对手阶段可直接取消。"
    )
    assert (
        repository.active_gameplay_summary("manager", now).game_type
        == "memory_single"
    )


def test_board_member_force_end_is_not_blocked_by_random_event_rules():
    from dzmm_bot.core.schema import RankRecord, UserRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 11, 10, 0, tzinfo=BEIJING)
    repository.create_user("board", "董事", now, 0)
    with factory.begin() as session:
        board_rank = session.scalar(
            select(RankRecord).where(RankRecord.is_board.is_(True))
        )
        board = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == "board")
        )
        assert board_rank is not None
        assert board is not None
        board.rank_id = board_rank.id
    repository.create_random_event_scene(
        "会议室", "临时会议开始。", ["正式开始。"], 4, 1, [("员工", 1)]
    )
    repository.set_random_event_settings(
        ["10:00"], "可选身份：{可选身份}", 15, 5
    )
    repository.schedule_random_events(now)
    repository.run_random_event_jobs(now)

    _receive(service, "board-force-end-event", "board", "/结束游戏", now)

    assert repository.active_gameplay_summary("board", now).game_type is None
    assert _latest_reply(factory) == "【随机事件】管理员已强制结束当前游戏。"


def test_board_bonus_command_grants_single_and_all_employees():
    from dzmm_bot.core.schema import RankRecord, UserRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 11, 10, 0, tzinfo=BEIJING)
    board, _ = repository.create_user("board", "董事", now, 0)
    repository.create_user("recipient", "苏  白", now, 0)
    repository.create_user("other", "其他员工", now, 0)
    with factory.begin() as session:
        board_rank = session.scalar(
            select(RankRecord).where(RankRecord.is_board.is_(True))
        )
        assert board_rank is not None
        session.get(UserRecord, board.id).rank_id = board_rank.id

    _receive(service, "single-bonus", "board", "/发奖金 苏  白 10", now)

    assert _latest_reply(factory) == "【奖金】董事向苏  白发放 10 摸鱼币。"
    assert repository.find_user("recipient").balance == 10

    _receive(service, "all-bonus", "board", "/发奖金 全部 7", now)

    assert _latest_reply(factory) == "【奖金】董事向全体 3 名员工每人发放 7 摸鱼币。"
    assert {user.platform_id: user.balance for user in repository.list_users()} == {
        "board": 7,
        "recipient": 17,
        "other": 7,
    }


def test_board_bonus_all_target_precedes_name_lookup_and_is_idempotent():
    from dzmm_bot.core.schema import RankRecord, UserRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 11, 10, 0, tzinfo=BEIJING)
    board, _ = repository.create_user("board", "董事", now, 0)
    repository.create_user("reserved-name", "全部", now, 0)
    with factory.begin() as session:
        board_rank = session.scalar(
            select(RankRecord).where(RankRecord.is_board.is_(True))
        )
        assert board_rank is not None
        session.get(UserRecord, board.id).rank_id = board_rank.id

    first = _receive(service, "same-bonus", "board", "/发奖金 全部 7", now)
    duplicate = _receive(service, "same-bonus", "board", "/发奖金 全部 7", now)

    assert first.inserted is True
    assert duplicate.inserted is False
    assert _latest_reply(factory) == "【奖金】董事向全体 2 名员工每人发放 7 摸鱼币。"
    assert {user.platform_id: user.balance for user in repository.list_users()} == {
        "board": 7,
        "reserved-name": 7,
    }


def test_board_bonus_command_rejects_nonboard_missing_and_ambiguous_targets():
    from dzmm_bot.core.schema import RankRecord, UserRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 11, 10, 0, tzinfo=BEIJING)
    board, _ = repository.create_user("board", "董事", now, 0)
    manager, _ = repository.create_user("manager", "负责人", now, 0)
    repository.create_user("duplicate-1", "同名", now, 0)
    repository.create_user("duplicate-2", "同名", now, 0)
    with factory.begin() as session:
        board_rank = session.scalar(
            select(RankRecord).where(RankRecord.is_board.is_(True))
        )
        manager_rank = session.scalar(
            select(RankRecord).where(
                RankRecord.has_group_management.is_(True),
                RankRecord.is_board.is_(False),
            )
        )
        assert board_rank is not None
        assert manager_rank is not None
        session.get(UserRecord, board.id).rank_id = board_rank.id
        session.get(UserRecord, manager.id).rank_id = manager_rank.id

    _receive(service, "unauthorized-bonus", "manager", "/发奖金 同名 10", now)
    assert _latest_reply(factory) == "只有核心董事会成员可以发放奖金。"
    _receive(service, "missing-bonus", "board", "/发奖金 不存在 10", now)
    assert _latest_reply(factory) == "未找到该员工，请检查员工名。"
    _receive(service, "ambiguous-bonus", "board", "/发奖金 同名 10", now)
    assert _latest_reply(factory) == "存在多名同名员工，请使用唯一员工名后重试。"
    assert all(user.balance == 0 for user in repository.list_users())


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("/发奖金", "请用 /发奖金 员工名 金额 或 /发奖金 全部 金额。"),
        ("/发奖金 苏白", "请用 /发奖金 员工名 金额 或 /发奖金 全部 金额。"),
        ("/发奖金 苏白 0", "奖金金额必须是 1–99999 的整数。"),
        ("/发奖金 苏白 -1", "奖金金额必须是 1–99999 的整数。"),
        ("/发奖金 苏白 1.5", "奖金金额必须是 1–99999 的整数。"),
        ("/发奖金 苏白 １００", "奖金金额必须是 1–99999 的整数。"),
        ("/发奖金 苏白 100000", "奖金金额必须是 1–99999 的整数。"),
    ],
)
def test_board_bonus_command_rejects_invalid_syntax_and_amounts(content, expected):
    from dzmm_bot.core.schema import RankRecord, UserRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 11, 10, 0, tzinfo=BEIJING)
    board, _ = repository.create_user("board", "董事", now, 0)
    repository.create_user("recipient", "苏白", now, 0)
    with factory.begin() as session:
        board_rank = session.scalar(
            select(RankRecord).where(RankRecord.is_board.is_(True))
        )
        assert board_rank is not None
        session.get(UserRecord, board.id).rank_id = board_rank.id

    _receive(service, f"invalid-bonus-{content}", "board", content, now)

    assert _latest_reply(factory) == expected
    assert all(user.balance == 0 for user in repository.list_users())


def test_help_basic_lists_board_bonus_command():
    service, _, factory = _service()
    now = datetime(2026, 8, 11, 10, 0, tzinfo=BEIJING)

    _receive(service, "bonus-help", "viewer", "/帮助 基础", now)

    assert "/发奖金 员工名 金额；/发奖金 全部 金额：仅核心董事会发放" in _latest_reply(factory)


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


def test_updated_economy_applies_to_future_join_and_checkin_only():
    service, repository, factory = _service()
    repository.set_game_settings("工分", 3, 7, 5)
    received_at = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)

    _receive(service, "join", "platform-xiaoming", "/入职 小明", received_at)
    assert _latest_reply(factory) == "小明，欢迎入职摸鱼公司。当前余额：3 工分。"

    _receive(service, "checkin", "platform-xiaoming", "/打卡", received_at)
    assert _latest_reply(factory) == "打卡成功，领取 7 工分。当前余额：10 工分。"

    _receive(service, "help", "platform-xiaoming", "/帮助 基础", received_at)
    assert "/打卡：每日领取 7 工分" in _latest_reply(factory)


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


def test_me_alias_shows_balance_level_and_today_income_without_count():
    service, repository, factory = _service()
    received_at = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)
    repository.set_game_settings("摸鱼币", 3, 5, 5)

    _receive(service, "join", "platform-xiaoming", "/入职 小明", received_at)
    _receive(
        service,
        "activity",
        "platform-xiaoming",
        "一二三四五六七八九十",
        received_at,
    )
    _receive(service, "me", "platform-xiaoming", "/me", received_at)

    reply = _latest_reply(factory)
    assert "小明" in reply
    assert "3 摸鱼币" in reply
    assert "LV1" in reply
    assert "今日收益：3 摸鱼币" in reply
    assert "连续打卡：0 天" in reply
    assert "10" not in reply


def test_undercover_group_commands_signup_deal_vote_and_settle():
    from dzmm_bot.core.schema import (
        UndercoverGamePlayerRecord,
        UndercoverGameRecord,
        UndercoverWordSetRecord,
        UserRecord,
    )

    service, repository, factory = _service()
    now = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)
    platform_ids = ["undercover-1", "undercover-2", "undercover-3", "undercover-4"]
    for number, platform_id in enumerate(platform_ids, start=1):
        _receive(service, f"join-{number}", platform_id, f"/入职 员工{number}", now)
    with factory.begin() as session:
        session.add(
            UndercoverWordSetRecord(
                category="测试",
                civilian_word="咖啡",
                undercover_word="奶茶",
                enabled=True,
                created_at=now,
            )
        )
    repository.upsert_direct_chats(
        [(platform_id, f"direct-{platform_id}") for platform_id in platform_ids], now
    )

    _receive(service, "undercover-start", platform_ids[0], "/谁是卧底 4", now)
    assert "报名开启" in _latest_reply(factory)
    for index, platform_id in enumerate(platform_ids[1:], start=2):
        _receive(service, f"undercover-join-{index}", platform_id, "/加入", now)
    assert "正在私聊发放身份" in _latest_reply(factory)

    with factory() as session:
        game = session.scalar(select(UndercoverGameRecord))
        assert game is not None
        players = list(
            session.execute(
                select(
                    UserRecord.platform_id,
                    UndercoverGamePlayerRecord.role,
                    UndercoverGamePlayerRecord.seat_number,
                )
                .join(UserRecord, UserRecord.id == UndercoverGamePlayerRecord.user_id)
                .where(UndercoverGamePlayerRecord.game_id == game.id)
            )
        )
    for platform_id in platform_ids:
        repository.record_undercover_card_delivery(game.id, platform_id, True, now)
    undercover_seat = next(seat for _, role, seat in players if role == "undercover")

    _receive(service, "undercover-vote", platform_ids[0], "/开始投票", now)
    assert "投票开始" in _latest_reply(factory)
    for index, platform_id in enumerate(platform_ids, start=1):
        _receive(
            service,
            f"undercover-ballot-{index}",
            platform_id,
            f"/投票 {undercover_seat}",
            now,
        )
    assert "平民阵营获胜" in _latest_reply(factory)
    assert repository.undercover_session_summary().state == "awaiting_continue"


def test_help_lists_undercover_commands():
    service, _, factory = _service()
    now = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)

    _receive(service, "help-undercover", "employee", "/帮助 谁是卧底", now)

    reply = _latest_reply(factory)
    assert "/谁是卧底 人数：" in reply
    assert "/开始投票：" in reply
    assert "/退出：" in reply
    assert "/退出谁是卧底：" not in reply


def test_blame_group_commands_create_join_transfer_and_end():
    from dzmm_bot.core.schema import RankRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)
    repository.create_user("blame-1", "甲", now, 100)
    repository.create_user("blame-2", "乙", now, 100)
    repository.create_blame_incident_card(
        "咖啡事故", "咖啡泼到了报表", ["咖啡", "报表"]
    )
    with factory.begin() as session:
        rank = session.scalar(select(RankRecord).where(RankRecord.sort_order == 1))
        rank.multiplayer_game_limit = 3

    _receive(service, "blame-start", "blame-1", "/甩锅游戏 2", now)
    assert "报名" in _latest_reply(factory)
    _receive(service, "blame-join", "blame-2", "/加入", now)
    start_reply = _latest_reply(factory)
    assert "咖啡事故" in start_reply
    assert "咖啡、报表" in start_reply

    summary = repository.blame_game_summary(now)
    holder = next(
        player for player in summary.players if player.seat_number == summary.current_holder_number
    )
    target = next(player for player in summary.players if player.platform_id != holder.platform_id)
    _receive(
        service,
        "blame-transfer",
        holder.platform_id,
        f"/甩锅 {target.seat_number} 咖啡弄脏了报表",
        now,
    )
    assert f"{target.display_name}" in _latest_reply(factory)
    assert "温热" in _latest_reply(factory)

    _receive(service, "blame-end", target.platform_id, "/结束游戏", now)
    assert "已结束" in _latest_reply(factory)


def _start_three_player_blame_group(service, repository, factory, now):
    from dzmm_bot.core.schema import RankRecord

    for platform_id, display_name in (("blame-a", "甲"), ("blame-b", "乙"), ("blame-c", "丙")):
        repository.create_user(platform_id, display_name, now, 100)
    repository.create_blame_incident_card(
        "咖啡事故", "咖啡泼到了报表", ["咖啡", "报表"]
    )
    with factory.begin() as session:
        rank = session.scalar(select(RankRecord).where(RankRecord.sort_order == 1))
        rank.multiplayer_game_limit = 3
    _receive(service, "blame-start-complete", "blame-a", "/甩锅游戏 3", now)
    _receive(service, "blame-join-b-complete", "blame-b", "/加入", now)
    _receive(service, "blame-join-c-complete", "blame-c", "/加入", now)


def test_generic_exit_hits_active_blame_game():
    service, repository, factory = _service()
    now = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)
    _start_three_player_blame_group(service, repository, factory, now)

    _receive(service, "blame-generic-exit", "blame-a", "/退出", now)

    assert "甲 主动退出并背锅" in _latest_reply(factory)


def test_blame_active_leave_complete_settlement_notice_includes_net_results():
    service, repository, factory = _service()
    now = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)
    _start_three_player_blame_group(service, repository, factory, now)

    _receive(service, "blame-leave-complete", "blame-a", "/退出甩锅", now)

    assert _latest_reply(factory) == (
        "【甩锅游戏】甲 主动退出并背锅，扣除 2 摸鱼币；"
        "乙、丙 获胜，每人获得 1 摸鱼币。"
    )


def test_blame_due_transfer_complete_settlement_notice_keeps_timeout_reason():
    from dzmm_bot.core.schema import BlameGamePlayerRecord, BlameGameRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)
    _start_three_player_blame_group(service, repository, factory, now)
    with factory.begin() as session:
        game = session.scalar(select(BlameGameRecord))
        players = list(
            session.scalars(
                select(BlameGamePlayerRecord)
                .where(BlameGamePlayerRecord.game_id == game.id)
                .order_by(BlameGamePlayerRecord.seat_number)
            )
        )
        game.current_holder_user_id = players[0].user_id
        game.explosion_deadline = now.astimezone(BEIJING) + timedelta(seconds=30)
        game.turn_deadline = now.astimezone(BEIJING)

    _receive(
        service,
        "blame-transfer-due-complete",
        "blame-a",
        "/甩锅 2 咖啡碰到报表",
        now + timedelta(seconds=1),
    )

    assert _latest_reply(factory) == (
        "【甩锅游戏】操作超时，甲 背锅，扣除 2 摸鱼币；"
        "乙、丙 获胜，每人获得 1 摸鱼币。"
    )


def test_department_join_application_keeps_employee_in_default_department_until_approved():
    service, _, factory = _service()
    now = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)

    _receive(service, "join", "platform-xiaoming", "/入职 小明", now)
    _receive(service, "department", "platform-xiaoming", "/加入部门 核心技术部", now)
    assert "已提交加入核心技术部申请" in _latest_reply(factory)

    _receive(service, "me", "platform-xiaoming", "/我", now)
    reply = _latest_reply(factory)
    assert "职位：实习生（LV1）" in reply
    assert "部门：未分配部门" in reply


def test_department_commands_apply_only_after_target_department_approval():
    from dzmm_bot.core.schema import DepartmentRecord, RankRecord, UserRecord

    service, _, factory = _service()
    now = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)
    _receive(service, "join-1", "u1", "/入职 小明", now)
    _receive(service, "join-2", "u2", "/入职 小红", now)
    with factory.begin() as session:
        target = session.scalar(
            select(DepartmentRecord).where(DepartmentRecord.name == "核心技术部")
        )
        rank_two = session.scalar(select(RankRecord).where(RankRecord.sort_order == 2))
        approver = session.scalar(select(UserRecord).where(UserRecord.platform_id == "u2"))
        assert target is not None
        assert rank_two is not None
        assert approver is not None
        approver.department_id = target.id
        approver.rank_id = rank_two.id

    _receive(service, "apply", "u1", "/加入部门 核心技术部", now)
    assert _latest_reply(factory) == "小明已提交加入核心技术部申请，等待该部门更高职位成员审批。"
    _receive(service, "list", "u2", "/部门申请列表", now)
    assert "1. 小明：未分配部门 → 核心技术部" in _latest_reply(factory)
    _receive(service, "approve", "u2", "/同意部门 1", now)
    assert _latest_reply(factory) == "小明已加入核心技术部。"
    _receive(service, "departments", "u1", "/部门", now)
    assert "核心技术部" in _latest_reply(factory)


def test_board_members_can_directly_change_departments_and_review_all_requests():
    from dzmm_bot.core.schema import RankRecord, UserRecord

    service, _, factory = _service()
    now = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)
    _receive(service, "join-1", "u1", "/入职 小明", now)
    _receive(service, "join-2", "board", "/入职 董事", now)
    with factory.begin() as session:
        board_rank = session.scalar(select(RankRecord).where(RankRecord.is_board.is_(True)))
        board = session.scalar(select(UserRecord).where(UserRecord.platform_id == "board"))
        assert board_rank is not None
        assert board is not None
        board.rank_id = board_rank.id

    _receive(service, "board-change", "board", "/加入部门 核心技术部", now)
    assert _latest_reply(factory) == "董事已直接加入核心技术部。"
    _receive(service, "board-switch", "board", "/切换部门 学院", now)
    assert _latest_reply(factory) == "董事已直接切换至学院。"
    _receive(service, "apply", "u1", "/加入部门 核心技术部", now)
    _receive(service, "list", "board", "/部门申请列表", now)
    assert "1. 小明：未分配部门 → 核心技术部" in _latest_reply(factory)


def test_promotion_request_list_and_numbered_approval():
    from dzmm_bot.core.schema import RankRecord, UserRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)
    _receive(service, "join-1", "u1", "/入职 小明", now)
    _receive(service, "join-2", "u2", "/入职 小红", now)
    applicant = repository.find_user("u1")
    assert applicant is not None
    repository.record_balance_change(applicant.id, 80, "test", now)
    with factory.begin() as session:
        approver = session.scalar(select(UserRecord).where(UserRecord.platform_id == "u2"))
        rank_two = session.scalar(select(RankRecord).where(RankRecord.sort_order == 2))
        assert approver is not None
        assert rank_two is not None
        approver.rank_id = rank_two.id

    _receive(service, "apply", "u1", "/晋升", now)
    assert _latest_reply(factory) == "小明已提交晋升申请：实习生 → 正式员工，需要 80 摸鱼币。"

    _receive(service, "list", "u2", "/晋升申请列表", now)
    assert "1. 小明：实习生 → 正式员工（80 摸鱼币" in _latest_reply(factory)

    _receive(service, "approve", "u2", "/同意 1", now)
    assert _latest_reply(factory) == "小明已晋升为正式员工，扣除 80 摸鱼币。"


def test_positions_and_reject_promotion():
    from dzmm_bot.core.schema import RankRecord, UserRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)
    _receive(service, "join-1", "u1", "/入职 小明", now)
    _receive(service, "join-2", "u2", "/入职 小红", now)
    applicant = repository.find_user("u1")
    assert applicant is not None
    repository.record_balance_change(applicant.id, 80, "test", now)
    with factory.begin() as session:
        approver = session.scalar(select(UserRecord).where(UserRecord.platform_id == "u2"))
        rank_two = session.scalar(select(RankRecord).where(RankRecord.sort_order == 2))
        assert approver is not None
        assert rank_two is not None
        approver.rank_id = rank_two.id

    _receive(service, "positions", "u1", "/职位", now)
    assert "正式员工（LV2）：晋升价格 80 摸鱼币" in _latest_reply(factory)
    _receive(service, "apply", "u1", "/晋升", now)
    _receive(service, "reject", "u2", "/拒绝 1", now)
    assert _latest_reply(factory) == "已拒绝小明的晋升申请。"
    assert repository.find_user("u1").balance == 80


def test_promotion_reply_uses_the_next_enabled_rank():
    from dzmm_bot.core.schema import RankRecord

    service, _, factory = _service()
    now = datetime(2026, 8, 7, 10, 0, tzinfo=BEIJING)
    _receive(service, "join", "u1", "/入职 小明", now)
    with factory.begin() as session:
        rank_two = session.scalar(select(RankRecord).where(RankRecord.sort_order == 2))
        assert rank_two is not None
        rank_two.enabled = False

    requested = _receive(service, "promotion", "u1", "/晋升", now)

    assert "实习生 → 小组长" in _replies_for(factory, requested.message_id)[0]


def test_random_event_commands_join_count_rounds_and_settle_on_exit():
    service, repository, factory = _service()
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_random_event_scene(
        "茶水间",
        "咖啡机突然发出一声巨响。",
        ["咖啡机突然发出一声巨响。"],
        4,
        2,
        [("员工", 2)],
    )
    repository.set_random_event_settings(
        ["10:00"], "可选身份：{可选身份}；截止：{报名截止分钟}", 15, 5
    )
    _receive(service, "join-1", "u1", "/入职 小明", now)
    _receive(service, "join-2", "u2", "/入职 小红", now)
    repository.schedule_random_events(now)
    repository.run_random_event_jobs(now)
    assert "可选身份：员工 × 2；截止：15" in _latest_reply(factory)

    _receive(service, "event-join-1", "u1", "/加入 员工", now)
    assert _latest_reply(factory) == "小明 已加入随机事件，担任 员工。\n剩余可选身份：员工 × 1"
    _receive(service, "event-join-2", "u2", "/加入 员工", now)
    _receive(service, "round-1", "u1", "第一句", now)
    _receive(service, "round-2", "u1", "第二句", now)
    _receive(service, "event-leave", "u1", "/退出", now)

    assert "领取 4 摸鱼币" in _latest_reply(factory)


@pytest.mark.parametrize("seat_count", [2, 1])
def test_random_event_replies_when_blocking_checkin_but_keeps_required_event_actions(seat_count):
    from dzmm_bot.core.schema import UserRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_random_event_scene(
        "茶水间", "咖啡机突然发出一声巨响。", ["正式开始。"], 4, 1, [("员工", seat_count)]
    )
    repository.set_random_event_settings(["10:00"], "可选身份：{可选身份}", 15, 5)
    _receive(service, "join-1", "u1", "/入职 小明", now)
    _receive(service, "join-2", "u2", "/入职 小红", now)
    repository.schedule_random_events(now)
    repository.run_random_event_jobs(now)

    if seat_count == 1:
        _receive(service, "start-event", "u2", "/加入 员工", now)

    checkin = _receive(service, f"checkin-{seat_count}", "u1", "/打卡", now)
    assert _replies_for(factory, checkin.message_id) == [
        "当前有随机事件发生，监事不会处理。"
    ]
    with factory() as session:
        employee = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == "u1")
        )
        assert employee.balance == 0

    if seat_count == 2:
        joined = _receive(service, "event-join", "u1", "/加入 员工", now)
        assert "已加入随机事件" in _replies_for(factory, joined.message_id)[0]


@pytest.mark.parametrize("seat_count", [2, 1])
def test_random_event_executes_checkin_when_admin_explicitly_allows_it(seat_count):
    from dzmm_bot.core.schema import UserRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_random_event_scene(
        "茶水间", "咖啡机突然发出一声巨响。", ["正式开始。"], 4, 1, [("员工", seat_count)]
    )
    repository.set_random_event_settings(
        ["10:00"],
        "可选身份：{可选身份}",
        15,
        5,
        signup_allowed_commands=["/打卡"],
        in_progress_allowed_commands=["/打卡"],
        blocked_message="当前有随机事件发生，监事不会处理。",
    )
    _receive(service, "join-1", "u1", "/入职 小明", now)
    _receive(service, "join-2", "u2", "/入职 小红", now)
    repository.schedule_random_events(now)
    repository.run_random_event_jobs(now)
    if seat_count == 1:
        assert repository.join_random_event("u2", "员工", now) == "started"

    checkin = _receive(service, f"checkin-allowed-{seat_count}", "u1", "/打卡", now)
    assert _replies_for(factory, checkin.message_id) == [
        "打卡成功，领取 5 摸鱼币。当前余额：5 摸鱼币。"
    ]
    with factory() as session:
        employee = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == "u1")
        )
        assert employee.balance == 5


def test_random_event_uses_the_configured_block_message():
    service, repository, factory = _service()
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_random_event_scene(
        "茶水间", "咖啡机突然发出一声巨响。", ["正式开始。"], 4, 1, [("员工", 2)]
    )
    repository.set_random_event_settings(
        ["10:00"],
        "可选身份：{可选身份}",
        15,
        5,
        blocked_message="活动进行中，监事暂不处理。",
    )
    _receive(service, "join", "u1", "/入职 小明", now)
    repository.schedule_random_events(now)
    repository.run_random_event_jobs(now)

    blocked = _receive(service, "blocked", "u1", "/余额", now)

    assert _replies_for(factory, blocked.message_id) == ["活动进行中，监事暂不处理。"]


def test_hide_and_seek_short_commands_list_places_and_patrol(monkeypatch):
    service, _, factory = _service()
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    _receive(service, "join", "u1", "/入职 小明", now)
    monkeypatch.setattr("dzmm_bot.core.repository.randbelow", lambda _: 0)

    _receive(service, "start", "u1", "/开始摸鱼躲藏", now)
    started_reply = _latest_reply(factory)
    chosen = _receive(service, "choose", "u1", "/躲 7", now)
    finished_replies = _replies_for(factory, chosen.message_id)

    assert "1（" in started_reply and "7（" in started_reply
    assert "开局不扣除" in started_reply
    assert len(finished_replies) == 2
    assert "【系统巡查·第一轮】巡查" in finished_replies[0]
    assert "奇怪，人躲哪里去了......." in finished_replies[0]
    assert "【系统巡查·第二轮】巡查" in finished_replies[1]
    assert "躲藏成功" in finished_replies[1]


def test_hide_and_seek_found_template_receives_frozen_penalty_amount(monkeypatch):
    service, repository, factory = _service()
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    _receive(service, "join", "u1", "/入职 小明", now)
    repository.set_reply_template(
        "/摸鱼躲猫猫",
        "found_first_round",
        "{昵称}，扣除 {惩罚金额} {货币}，当前余额 {余额} {货币}。",
    )
    monkeypatch.setattr("dzmm_bot.core.repository.randbelow", lambda _: 0)

    _receive(service, "start", "u1", "/开始摸鱼躲藏", now)
    _receive(service, "choose", "u1", "/躲 1", now)

    assert _latest_reply(factory) == "小明，扣除 1 摸鱼币，当前余额 -1 摸鱼币。"


def test_hide_and_seek_first_round_found_sends_only_one_reply(monkeypatch):
    service, _, factory = _service()
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    _receive(service, "join", "u1", "/入职 小明", now)
    monkeypatch.setattr("dzmm_bot.core.repository.randbelow", lambda _: 0)

    _receive(service, "start", "u1", "/开始摸鱼躲藏", now)
    chosen = _receive(service, "choose", "u1", "/躲 1", now)
    replies = _replies_for(factory, chosen.message_id)

    assert len(replies) == 1
    assert "【系统巡查·第一轮】巡查" in replies[0]
    assert "【系统巡查·第二轮】" not in replies[0]


def test_memory_assessment_single_uses_continue_and_cash_out_commands(monkeypatch):
    from dzmm_bot.core.schema import MemoryAssessmentRoundRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    _receive(service, "join", "u1", "/入职 小明", now)
    monkeypatch.setattr("dzmm_bot.core.repository.choice", lambda _: "A")

    _receive(service, "start", "u1", "/记忆考核", now)
    with factory() as session:
        round_record = session.scalar(select(MemoryAssessmentRoundRecord))
    _receive(service, "too-early", "u1", "/答案 AAAAA", now)
    repository.mark_memory_assessment_round_recalled(round_record.id, now)
    _receive(service, "answer", "u1", "/答案 AAAAA", now)
    _receive(service, "cash-out", "u1", "/收手", now)

    assert _latest_reply(factory) == "小明 收手成功，获得 1 摸鱼币。当前余额：1 摸鱼币。"


def test_memory_assessment_only_accepts_answers_prefixed_with_answer_command(monkeypatch):
    from dzmm_bot.core.schema import MemoryAssessmentRoundRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    _receive(service, "join", "u1", "/入职 小明", now)
    monkeypatch.setattr("dzmm_bot.core.repository.choice", lambda _: "A")

    _receive(service, "start", "u1", "/记忆考核", now)
    with factory() as session:
        round_record = session.scalar(select(MemoryAssessmentRoundRecord))
    repository.mark_memory_assessment_round_recalled(round_record.id, now)

    casual = _receive(service, "casual", "u1", "今天正常聊天", now)
    with factory() as session:
        assert session.get(MemoryAssessmentRoundRecord, round_record.id).state == "awaiting_answer"
    assert _replies_for(factory, casual.message_id) == []

    answer = _receive(service, "answer", "u1", "/答案 AAAAA", now)

    assert _replies_for(factory, answer.message_id) == [
        "第 1 级通过。现在收手可获得 1 摸鱼币，或发送 /继续 挑战下一层。"
    ]


def test_memory_assessment_prompt_is_queued_for_automatic_recall(monkeypatch):
    from dzmm_bot.core.schema import MemoryAssessmentRoundRecord, OutboundRecord

    service, _, factory = _service()
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    _receive(service, "join", "u1", "/入职 小明", now)
    monkeypatch.setattr("dzmm_bot.core.repository.choice", lambda _: "A")

    _receive(service, "start", "u1", "/记忆考核", now)

    with factory() as session:
        outbound = session.scalar(
            select(OutboundRecord).where(OutboundRecord.recall_after_seconds.is_not(None))
        )
        round_record = session.scalar(select(MemoryAssessmentRoundRecord))
    assert outbound.recall_after_seconds == 3
    assert round_record.outbound_message_id == outbound.id


def test_memory_assessment_duel_is_joined_with_plain_join_command(monkeypatch):
    from dzmm_bot.core.schema import MemoryAssessmentRoundRecord

    service, repository, factory = _service()
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    _receive(service, "join-1", "u1", "/入职 小明", now)
    _receive(service, "join-2", "u2", "/入职 小红", now)
    monkeypatch.setattr("dzmm_bot.core.repository.choice", lambda _: "A")

    _receive(service, "duel", "u1", "/记忆考核 对战", now)
    _receive(service, "duel-join", "u2", "/加入", now)
    with factory() as session:
        round_record = session.scalar(select(MemoryAssessmentRoundRecord))
    repository.mark_memory_assessment_round_recalled(round_record.id, now)
    _receive(service, "answer", "u1", "/答案 " + "A" * 13, now)

    assert "小明 最先答对，赢得奖池 10 摸鱼币。" in _latest_reply(factory)


def test_memory_assessment_duel_replies_when_multiplayer_game_is_active():
    """Fails if a multiplayer conflict crashes inbound command handling."""
    service, repository, factory = _service()
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    _receive(service, "join", "u1", "/入职 小明", now)
    repository.upsert_direct_chats([("u1", "direct-u1")], now)
    assert repository.start_undercover_signup("u1", 4, now).status == "signup_started"

    _receive(service, "duel", "u1", "/记忆考核 对战", now)

    assert _latest_reply(factory) == "当前已有多人玩法进行中，暂不能发起记忆考核对战。"


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

    _receive(service, "help", "platform-xiaoming", "/帮助 基础", received_at)

    assert "【基础与资产】" in _latest_reply(factory)
    assert "/打卡" not in _latest_reply(factory)


def test_help_shows_category_entrypoints_instead_of_all_commands():
    service, _, factory = _service()
    received_at = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)

    _receive(service, "help", "platform-xiaoming", "/帮助", received_at)

    reply = _latest_reply(factory)
    assert "发送 /帮助 分类，查看详细用法：" in reply
    assert "/帮助 基础" in reply
    assert "/帮助 游戏" in reply
    assert "/帮助 随机事件" in reply
    assert "/帮助 职位" in reply
    assert "/帮助 部门" in reply
    assert "/同意部门" not in reply


def test_help_game_topic_links_to_each_game_guide():
    service, _, factory = _service()
    received_at = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)

    _receive(service, "help-games", "platform-xiaoming", "/帮助 游戏", received_at)

    reply = _latest_reply(factory)
    assert "【游戏玩法】" in reply
    assert "/帮助 摸鱼躲藏" in reply
    assert "/帮助 记忆考核" in reply
    assert "/帮助 谁是卧底" in reply
    assert "/帮助 蹦蹦数字炸弹" in reply
    for command in (
        "/蹦蹦数字炸弹", "/加入", "/开始", "/报数 数字",
        "/跳过 编号", "/继续", "/结束游戏",
    ):
        assert command in reply
    assert "3-10" not in reply
    assert "3 至 10" not in reply
    assert "无操作释放" not in reply


def test_help_number_bomb_topic_shows_group_and_private_commands():
    service, _, factory = _service()
    received_at = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)

    _receive(
        service,
        "help-number-bomb",
        "platform-xiaoming",
        "/帮助 蹦蹦数字炸弹",
        received_at,
    )

    reply = _latest_reply(factory)
    assert "【蹦蹦数字炸弹】" in reply
    for command in (
        "/蹦蹦数字炸弹", "/加入", "/开始", "/报数 数字",
        "/跳过 编号", "/退出", "/继续", "/结束游戏",
    ):
        assert command in reply
    assert "人数" not in reply
    assert "3-10" not in reply
    assert "3 至 10" not in reply
    assert "无操作释放" not in reply


def test_help_hide_and_seek_topic_shows_start_and_followup_syntax():
    service, _, factory = _service()
    received_at = datetime(2026, 8, 5, 2, 0, tzinfo=UTC)

    _receive(service, "help-hide-and-seek", "platform-xiaoming", "/帮助 摸鱼躲藏", received_at)

    reply = _latest_reply(factory)
    assert "【摸鱼躲藏】" in reply
    assert "/开始摸鱼躲藏" in reply
    assert "/躲 序号" in reply
    assert "/摸鱼躲猫猫" not in reply
