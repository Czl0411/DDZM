from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.runtime.contracts import InboundMessage


BEIJING = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 10, 3, 15, 0, tzinfo=BEIJING)


def _service():
    from dzmm_bot.core.commands import GroupCommandHandler
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import Base
    from dzmm_bot.core.service import CoreService

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(factory)
    repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=group-main", NOW
    )
    return (
        CoreService(repository, GroupCommandHandler(repository)),
        repository,
        factory,
    )


def _receive(service, message_id, sender, content, received_at, **kwargs):
    kwargs.setdefault("chatroom_id", "group-main")
    return service.receive_inbound(
        InboundMessage(message_id, sender, content, received_at, **kwargs)
    )


def _latest_reply(factory):
    from dzmm_bot.core.schema import OutboundRecord

    with factory() as session:
        latest = session.scalar(
            select(OutboundRecord).order_by(OutboundRecord.created_at.desc())
        )
        if latest is None:
            return ""
        if latest.inbound_message_id is None:
            return latest.text
        return "\n".join(
            session.scalars(
                select(OutboundRecord.text)
                .where(OutboundRecord.inbound_message_id == latest.inbound_message_id)
                .order_by(OutboundRecord.reply_index)
            )
        )


def _join_employees(service, now, count=4):
    names = ("甲", "乙", "丙", "丁")
    for index in range(count):
        _receive(
            service, f"join-{index}", f"user-{index}", f"/入职 {names[index]}", now
        )


def _game(repository):
    from dzmm_bot.core.schema import TruthTradeGameRecord

    with repository._session() as session:
        return session.scalar(
            select(TruthTradeGameRecord).where(
                TruthTradeGameRecord.active_key == "global"
            )
        )


def _finished_game(repository):
    from dzmm_bot.core.schema import TruthTradeGameRecord

    with repository._session() as session:
        return session.scalar(
            select(TruthTradeGameRecord).order_by(
                TruthTradeGameRecord.created_at.desc()
            )
        )


def _outbound_texts(factory):
    from dzmm_bot.core.schema import OutboundRecord

    with factory() as session:
        return list(
            session.scalars(select(OutboundRecord.text).order_by(OutboundRecord.id))
        )


def _setup_game(service, repository, factory, now, players=3):
    """开一局 players 人局并开局；玩家为 user-0..N-1，1号位由 user-0 占据。"""
    _join_employees(service, now, players)
    _receive(service, "start", "user-0", "/真心换真心", now)
    for index in range(1, players):
        _receive(service, f"signup-{index}", f"user-{index}", "/加入", now)
    _receive(service, "begin", "user-0", "/开始", now)
    assert "第 1 轮开始" in _latest_reply(factory)


def test_truth_trade_wen_alias_for_ask():
    """/问、/问吧 是 /问题 的别名：正常路由，且只剥离自身前缀。"""
    service, repository, factory = _service()
    now = NOW
    _setup_game(service, repository, factory, now)

    _receive(service, "q1", "user-0", "/问 今天吃了什么", now)
    assert "其他人发送 /回答 你的回答" in _latest_reply(factory)
    from dzmm_bot.core.schema import TruthTradeQuestionRecord

    with repository._session() as session:
        question = session.scalar(
            select(TruthTradeQuestionRecord).where(
                TruthTradeQuestionRecord.position == 1
            )
        )
        assert question.content == "今天吃了什么"

    _receive(service, "a1", "user-1", "/回答 米饭", now)
    _receive(service, "a2", "user-2", "/答 面条", now)
    _receive(service, "q2", "user-1", "/问 跳过", now)
    assert "已跳过本轮提问" in _latest_reply(factory)

    # /问吧 同样可用
    _receive(service, "q3", "user-2", "/问吧 最喜欢的游戏", now)
    with repository._session() as session:
        question = session.scalar(
            select(TruthTradeQuestionRecord)
            .order_by(TruthTradeQuestionRecord.position.desc())
        )
        assert question.content == "最喜欢的游戏"


def test_truth_trade_full_flow_round_complete_and_continue():
    service, repository, factory = _service()
    now = NOW
    _setup_game(service, repository, factory, now)

    # 1号 提问 → 2、3号回答 → 自动轮到 2号
    _receive(service, "q1", "user-0", "/问题 今天吃了什么", now)
    assert "今天吃了什么" in _latest_reply(factory)
    assert "其他人发送 /回答 你的回答" in _latest_reply(factory)
    _receive(service, "a1", "user-1", "/真心 米饭", now)
    assert "已记录 2号 乙 的回答（1/2）" in _latest_reply(factory)
    _receive(service, "a2", "user-2", "/真心 面条", now)
    recap = _latest_reply(factory)
    assert "1号 甲 的问题收集完毕" in recap
    assert "乙：米饭" in recap and "丙：面条" in recap
    assert "轮到 2号 乙 提问" in recap
    assert _game(repository).state == "asking"

    # 2号 跳过提问 → 轮到 3号；3号的问题收到拒答+回答后收齐
    _receive(service, "q2", "user-1", "/问题 跳过", now)
    assert "已跳过本轮提问" in _latest_reply(factory)
    assert any("轮到 3号 丙 提问" in text for text in _outbound_texts(factory))
    _receive(service, "q3", "user-2", "/问题 最喜欢的游戏", now)
    _receive(service, "a3", "user-0", "/真心 跳过", now)
    assert "拒答" in _latest_reply(factory)
    _receive(service, "a4", "user-1", "/真心 原神", now)
    recap = _latest_reply(factory)
    assert "3号 丙 的问题收集完毕" in recap
    assert "甲：拒答" in recap and "乙：原神" in recap
    # 全员问完 → 本轮完毕结算 + 参与计局
    assert "第 1 轮结束" in recap
    assert "/继续 开下一轮" in recap
    game = _game(repository)
    assert game.state == "round_complete"
    assert game.round_number == 1 and game.settled_rounds == 1

    # /继续：活跃名单开第 2 轮，从最小序号 1号 开始
    _receive(service, "cont", "user-1", "/继续", now)
    reply = _latest_reply(factory)
    assert "第 2 轮开始（共 3 人）" in reply
    assert "1号 甲" in reply and "轮到 1号 甲 提问" in reply
    assert _game(repository).state == "asking"

    # 总战绩跨局累计（跳过的问题不计）
    _receive(service, "stat", "user-0", "/真心换真心数据", now)
    stats = _latest_reply(factory)
    assert "对局：1 局" in stats
    assert "提问：2 个" in stats
    assert "回答：3 条" in stats
    assert "提问最多" in stats and "回答最多" in stats


def test_truth_trade_signup_errors():
    service, repository, factory = _service()
    now = NOW
    _join_employees(service, now)
    _receive(service, "s1", "user-0", "/真心换真心", now)
    assert "报名开启" in _latest_reply(factory)
    _receive(service, "s2", "user-1", "/真心换真心", now)
    assert "当前已有真心换真心对局" in _latest_reply(factory)
    _receive(service, "begin", "user-0", "/开始", now)
    assert "报名人数不足 2 人" in _latest_reply(factory)

    # 其他游戏进行中 → 拒绝开新局
    from dzmm_bot.core.schema import TruthTradeGameRecord

    with repository._session() as session:
        game = session.scalar(
            select(TruthTradeGameRecord).where(
                TruthTradeGameRecord.active_key == "global"
            )
        )
        game.active_key = None
        game.state = "cancelled"
    _receive(service, "dice", "user-0", "/大话骰子", now)
    assert "【大话骰子】报名已开启" in _latest_reply(factory)
    _receive(service, "s3", "user-1", "/真心换真心", now)
    assert "当前已有游戏或随机事件进行中" in _latest_reply(factory)


def test_truth_trade_midway_join_is_exempt_from_current_question():
    service, repository, factory = _service()
    now = NOW
    _join_employees(service, now, 4)
    _setup_game(service, repository, factory, now, players=3)

    _receive(service, "q1", "user-0", "/问题 今天吃了什么", now)
    _receive(service, "join4", "user-3", "/加入", now)
    assert "4号 丁 加入" in _latest_reply(factory)
    assert "从下一个问题开始参与回答" in _latest_reply(factory)
    _receive(service, "a1", "user-3", "/真心 顺答", now)
    assert "你加入晚于本题，无需回答" in _latest_reply(factory)
    _receive(service, "a2", "user-1", "/真心 米饭", now)
    _receive(service, "a3", "user-2", "/真心 面条", now)
    recap = _latest_reply(factory)
    recap_body = recap.split("收集完毕")[1].split("轮到")[0]
    assert "丁" not in recap_body

    # 第 2 个提问者的问题：丁需要回答
    _receive(service, "q2", "user-1", "/问题 昨天玩了什么", now)
    _receive(service, "a4", "user-3", "/真心 原神", now)
    assert "已记录 4号 丁 的回答" in _latest_reply(factory)


def test_truth_trade_leave_edges():
    service, repository, factory = _service()
    now = NOW
    _setup_game(service, repository, factory, now, players=3)

    # 当前提问者退出 → 跳过他的提问轮，轮到下一位
    _receive(service, "lv1", "user-0", "/退出", now)
    texts = _outbound_texts(factory)
    assert any("轮到 2号 乙 提问" in text for text in texts)

    # 2号提问后，唯一必答者 3号 退出 → 记中途退出并收齐 → 本轮结算
    _receive(service, "q2", "user-1", "/问题 晚饭吃什么", now)
    _receive(service, "lv2", "user-2", "/退出", now)
    texts = _outbound_texts(factory)
    assert any("丙：中途退出" in text for text in texts)
    assert any("第 1 轮结束" in text for text in texts)
    assert any("剩余活跃人数不足 2 人，本局已结束" in text for text in texts)
    finished = _finished_game(repository)
    assert finished.state == "finished"
    assert finished.finish_reason == "not_enough_players"


def test_truth_trade_question_timeout_skips_asker():
    service, repository, factory = _service()
    now = NOW
    _join_employees(service, now, 4)
    _setup_game(service, repository, factory, now, players=3)
    late = now + timedelta(seconds=301)

    _receive(service, "late-join", "user-3", "/加入", late)
    texts = _outbound_texts(factory)
    assert any("1号 甲 提问超时，自动跳过" in text for text in texts)
    assert any("轮到 2号 乙 提问" in text for text in texts)
    assert _game(repository).current_position == 2


def test_truth_trade_answer_timeout_marks_unanswered():
    service, repository, factory = _service()
    now = NOW
    _join_employees(service, now, 4)
    _setup_game(service, repository, factory, now, players=3)
    _receive(service, "q1", "user-0", "/问题 今天吃了什么", now)
    late = now + timedelta(seconds=601)

    _receive(service, "late-join", "user-3", "/加入", late)
    texts = _outbound_texts(factory)
    assert any("1号 甲 的问题收集完毕" in text for text in texts)
    assert any("乙：超时未答" in text for text in texts)
    assert any("丙：超时未答" in text for text in texts)
    assert _game(repository).state == "asking"


def test_truth_trade_current_game_shows_roster_and_count():
    service, repository, factory = _service()
    now = NOW
    _setup_game(service, repository, factory, now, players=3)
    _receive(service, "cur", "user-1", "/当前游戏", now)
    reply = _latest_reply(factory)
    assert "真心换真心" in reply
    assert "提问轮" in reply
    assert "轮到 甲 提问" in reply
    assert "当前玩家共 3 人" in reply
    assert "1号 甲" in reply


def test_truth_trade_allowance_host_and_round_bump():
    from dzmm_bot.core.schema import (
        DepartmentGamePlayRecord,
        DepartmentRecord,
        UserRecord,
    )

    service, repository, factory = _service()
    now = NOW
    _join_employees(service, now, 3)
    with factory.begin() as session:
        department = session.scalar(
            select(DepartmentRecord).where(
                DepartmentRecord.name == "小游戏娱乐部"
            )
        )
        department.allowance_kind = "game"
        department_id = department.id
        for index in range(3):
            user = session.scalar(
                select(UserRecord).where(UserRecord.platform_id == f"user-{index}")
            )
            user.department_id = department_id

    _receive(service, "s1", "user-0", "/真心换真心", now)
    _receive(service, "s2", "user-1", "/加入", now)
    _receive(service, "s3", "user-2", "/加入", now)

    # 开局：发起人 +1 开局奖励
    with factory() as session:
        host = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == "user-0")
        )
        balance_before = host.balance
    _receive(service, "begin", "user-0", "/开始", now)
    with factory() as session:
        host = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == "user-0")
        )
        assert host.balance == balance_before + 1

    # 一轮结算 → 每个参与者计 1 局
    _receive(service, "q1", "user-0", "/问题 今天吃了什么", now)
    _receive(service, "a1", "user-1", "/真心 米饭", now)
    _receive(service, "a2", "user-2", "/真心 面条", now)
    _receive(service, "q2", "user-1", "/问题 跳过", now)
    _receive(service, "q3", "user-2", "/问题 跳过", now)
    assert _game(repository).state == "round_complete"
    with factory() as session:
        counts = session.scalars(select(DepartmentGamePlayRecord.count)).all()
        assert sorted(counts) == [1, 1, 1]

    # 已结算后再 /结束游戏：不重复计局
    _receive(service, "end", "user-0", "/结束游戏", now)
    with factory() as session:
        counts = session.scalars(select(DepartmentGamePlayRecord.count)).all()
        assert sorted(counts) == [1, 1, 1]
    finished = _finished_game(repository)
    assert finished.state == "finished"
