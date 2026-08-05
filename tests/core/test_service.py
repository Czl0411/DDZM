from datetime import UTC, datetime

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


def test_service_warns_unwrapped_observer_during_random_event(session_factory):
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import BEIJING, OutboundRecord
    from dzmm_bot.core.service import CoreService

    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository = CoreRepository(session_factory)
    repository.create_random_event_scene(
        "茶水间", "快点加入吧。", ["正式开始。"], 1, 1, [("员工", 1)]
    )
    repository.set_random_event_settings("10:00", "10:01", 1, 60, 15, 5)
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
    assert warning.text == "当前随机事件进行中，旁观请用（内容）或 (内容) 的形式发言。"


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

    def fail_enqueue(message_id, reply):
        raise RuntimeError("enqueue failed")

    repository.enqueue_outbound = fail_enqueue
    with pytest.raises(RuntimeError, match="enqueue failed"):
        service.receive_inbound(inbound)
    repository.enqueue_outbound = original_enqueue

    with session_factory() as session:
        assert session.scalar(select(InboundRecord)) is None
        assert session.scalar(select(WorkerCommandRecord)) is None
