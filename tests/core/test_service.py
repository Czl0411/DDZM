from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.runtime.contracts import InboundMessage


@pytest.fixture
def session_factory():
    from dzmm_bot.core.schema import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def inbound():
    return InboundMessage(
        "platform-1",
        "sender-1",
        "hello",
        datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
    )


def test_noop_service_accepts_message_without_creating_reply(session_factory, inbound):
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import OutboundRecord
    from dzmm_bot.core.service import CoreService

    service = CoreService(CoreRepository(session_factory))

    result = service.receive_inbound(inbound)

    assert result.inserted is True
    with session_factory() as session:
        assert session.scalar(select(OutboundRecord)) is None


def test_duplicate_message_does_not_invoke_handler_twice(session_factory, inbound):
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.service import CoreService

    class CountingHandler:
        def __init__(self):
            self.calls = 0

        def handle(self, message):
            self.calls += 1
            return "reply"

    handler = CountingHandler()
    service = CoreService(CoreRepository(session_factory), handler)

    first = service.receive_inbound(inbound)
    second = service.receive_inbound(inbound)

    assert first.inserted is True
    assert second.inserted is False
    assert second.message_id == first.message_id
    assert handler.calls == 1


def test_service_queues_multiple_replies_for_one_inbound_in_order(session_factory, inbound):
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import OutboundRecord
    from dzmm_bot.core.service import CoreService

    class MultiReplyHandler:
        def handle(self, message):
            return ["第一条", "第二条"]

    service = CoreService(CoreRepository(session_factory), MultiReplyHandler())
    result = service.receive_inbound(inbound)
    duplicate = service.receive_inbound(inbound)

    with session_factory() as session:
        replies = list(
            session.scalars(
                select(OutboundRecord)
                .where(OutboundRecord.inbound_message_id == result.message_id)
                .order_by(OutboundRecord.reply_index)
            )
        )
    assert [reply.text for reply in replies] == ["第一条", "第二条"]
    assert [reply.reply_index for reply in replies] == [0, 1]
    assert duplicate.inserted is False


def test_service_records_an_accepted_joined_message_once(session_factory):
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.service import CoreService

    repository = CoreRepository(session_factory)
    received_at = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    repository.create_user("sender-1", "小明", received_at, 0)
    service = CoreService(repository)
    message = InboundMessage(
        "platform-activity-1", "sender-1", "一二三四五六七八九十", received_at
    )

    service.receive_inbound(message)
    service.receive_inbound(message)

    assert repository.personal_activity("sender-1", received_at).level == 1


def test_commands_and_parenthesized_messages_are_not_memory_eligible(session_factory):
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import InboundRecord
    from dzmm_bot.core.service import CoreService

    repository = CoreRepository(session_factory)
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    repository.create_user("player", "玩家", now, 0)
    service = CoreService(repository)

    service.receive_inbound(InboundMessage("command", "player", "/打卡", now))
    service.receive_inbound(
        InboundMessage("observer", "player", "（围观）", now + timedelta(seconds=1))
    )
    service.receive_inbound(
        InboundMessage("ordinary", "player", "今天群里很热闹", now + timedelta(seconds=2))
    )

    with session_factory() as session:
        rows = list(
            session.scalars(select(InboundRecord).order_by(InboundRecord.received_at))
        )
    assert [row.ai_memory_eligible for row in rows] == [False, False, True]


def test_active_blame_dialogue_is_excluded_until_the_game_ends(session_factory):
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import (
        BlameGamePlayerRecord,
        BlameGameRecord,
        InboundRecord,
    )
    from dzmm_bot.core.service import CoreService

    repository = CoreRepository(session_factory)
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    user, _ = repository.create_user("blame-player", "甩锅玩家", now, 100)
    with session_factory.begin() as session:
        game = BlameGameRecord(
            state="active",
            active_key="global",
            creator_user_id=user.id,
            target_player_count=2,
            signup_deadline=now + timedelta(minutes=1),
            settlement_complete=False,
            created_at=now,
        )
        session.add(game)
        session.flush()
        session.add(
            BlameGamePlayerRecord(
                game_id=game.id,
                user_id=user.id,
                signup_order=1,
                seat_number=1,
                state="joined",
                guarantee_amount=0,
                guarantee_state="held",
                joined_at=now,
            )
        )
    service = CoreService(repository)

    service.receive_inbound(
        InboundMessage("blame-dialogue", user.platform_id, "这个锅不是我的", now)
    )
    with session_factory.begin() as session:
        game = session.scalar(select(BlameGameRecord))
        game.state = "finished"
        game.active_key = None
        game.finished_at = now + timedelta(seconds=1)
    service.receive_inbound(
        InboundMessage(
            "after-blame", user.platform_id, "这局终于结束了", now + timedelta(seconds=2)
        )
    )

    with session_factory() as session:
        rows = list(
            session.scalars(select(InboundRecord).order_by(InboundRecord.received_at))
        )
    assert [row.ai_memory_eligible for row in rows] == [False, True]


def test_service_queues_only_non_command_bot_mentions(session_factory):
    """Fails if commands or ordinary text are routed to the model queue."""
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import (
        AIAssistantSettingsRecord,
        AIMemoryJobRecord,
        AIRequestRecord,
    )
    from dzmm_bot.core.service import CoreService

    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    repository = CoreRepository(session_factory)
    repository.create_user("sender-1", "小明", now, 0)
    repository.get_ai_assistant_settings()
    with session_factory.begin() as session:
        session.get(AIAssistantSettingsRecord, 1).enabled = True
    service = CoreService(repository)

    service.receive_inbound(InboundMessage("ai-command", "sender-1", "/帮助 @总监事", now))
    service.receive_inbound(InboundMessage("ai-plain", "sender-1", "@总监事 今天适合摸鱼吗？", now))
    service.receive_inbound(InboundMessage("ai-empty", "sender-1", "@总监事   ", now))
    service.receive_inbound(InboundMessage("ai-platform-empty", "sender-1", "@总监事「Bot」", now))

    with session_factory() as session:
        requests = list(session.scalars(select(AIRequestRecord)))
        memory_job = session.scalar(select(AIMemoryJobRecord))
    assert len(requests) == 1
    assert memory_job is None


def test_service_strips_platform_bot_label_from_ai_mention(session_factory):
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import AIAssistantSettingsRecord, AIRequestRecord
    from dzmm_bot.core.service import CoreService

    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    repository = CoreRepository(session_factory)
    repository.create_user("sender-1", "小明", now, 0)
    repository.get_ai_assistant_settings()
    with session_factory.begin() as session:
        session.get(AIAssistantSettingsRecord, 1).enabled = True
    service = CoreService(repository)

    service.receive_inbound(
        InboundMessage("ai-platform-label", "sender-1", "@总监事「Bot」 今天适合摸鱼吗？", now)
    )

    with session_factory() as session:
        assert session.scalar(select(AIRequestRecord)) is not None
    request = repository.claim_ai_request("ai-worker", now, 30)
    assert request is not None
    assert request.user_content == "今天适合摸鱼吗？"


def test_service_uses_random_event_block_message_for_unwrapped_observer(session_factory):
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import BEIJING, InboundRecord, OutboundRecord
    from dzmm_bot.core.service import CoreService

    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository = CoreRepository(session_factory)
    repository.create_random_event_scene(
        "茶水间", "快点加入吧。", ["正式开始。"], 1, 1, [("员工", 1)]
    )
    repository.set_random_event_settings(["10:00"], "{可选身份}", 15, 5)
    repository.create_user("player", "小明", now, 0)
    repository.schedule_random_events(now)
    repository.run_random_event_jobs(now)
    assert repository.join_random_event("player", "员工", now) == "started"
    service = CoreService(repository)

    result = service.receive_inbound(
        InboundMessage("observer-message", "observer", "你好，你们在干什么", now)
    )

    with session_factory() as session:
        warning = session.scalar(
            select(OutboundRecord).where(OutboundRecord.inbound_message_id == result.message_id)
        )
        inbound = session.get(InboundRecord, result.message_id)
    assert warning.text == "当前有随机事件发生，监事不会处理。"
    assert inbound.ai_memory_eligible is False


@pytest.mark.parametrize("content", ["（围观一下）", "(围观一下)"])
def test_service_allows_parenthesized_observer_during_random_event_signup(
    session_factory, content
):
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import BEIJING, OutboundRecord
    from dzmm_bot.core.service import CoreService

    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository = CoreRepository(session_factory)
    repository.create_random_event_scene(
        "茶水间", "快点加入吧。", ["正式开始。"], 1, 1, [("员工", 1)]
    )
    repository.set_random_event_settings(["10:00"], "{可选身份}", 15, 5)
    repository.schedule_random_events(now)
    repository.run_random_event_jobs(now)
    service = CoreService(repository)

    result = service.receive_inbound(
        InboundMessage("signup-observer-message", "observer", content, now)
    )

    with session_factory() as session:
        assert session.scalar(
            select(OutboundRecord).where(
                OutboundRecord.inbound_message_id == result.message_id
            )
        ) is None


def test_enqueue_failure_rolls_back_inbound(session_factory, inbound):
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import InboundRecord, WorkerCommandRecord
    from dzmm_bot.core.service import CoreService

    class ReplyHandler:
        def handle(self, message):
            repository.enqueue_worker_command("restart_browser")
            return "reply"

    repository = CoreRepository(session_factory)
    service = CoreService(repository, ReplyHandler())
    original_enqueue = repository.enqueue_outbound

    def fail_enqueue(message_id, reply, reply_index=0):
        raise RuntimeError("enqueue failed")

    repository.enqueue_outbound = fail_enqueue
    with pytest.raises(RuntimeError, match="enqueue failed"):
        service.receive_inbound(inbound)
    repository.enqueue_outbound = original_enqueue

    with session_factory() as session:
        assert session.scalar(select(InboundRecord)) is None
        assert session.scalar(select(WorkerCommandRecord)) is None
