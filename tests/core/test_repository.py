import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from dzmm_bot.runtime.contracts import InboundMessage, LoginState, WorkerHeartbeat


@pytest.fixture
def now():
    return datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def inbound(now):
    return InboundMessage("platform-1", "sender-1", "hello", now)


@pytest.fixture
def session_factory():
    from dzmm_bot.core.schema import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def repository(session_factory):
    from dzmm_bot.core.repository import CoreRepository

    return CoreRepository(session_factory)


def test_duplicate_platform_message_returns_existing_record(repository, inbound):
    first, inserted = repository.accept_inbound(inbound)
    second, duplicate = repository.accept_inbound(inbound)

    assert inserted is True
    assert duplicate is False
    assert second.id == first.id


def test_expired_lease_can_be_claimed_once_by_another_worker(
    repository, inbound, now
):
    stored, _ = repository.accept_inbound(inbound)
    outbound = repository.enqueue_outbound(stored.id, "reply")

    assert repository.claim_outbound("a", now, 30).id == outbound.id
    assert (
        repository.claim_outbound("b", now + timedelta(seconds=31), 30).id
        == outbound.id
    )
    assert repository.claim_outbound("c", now + timedelta(seconds=32), 30) is None


def test_confirmed_outbound_is_not_claimed_again(
    repository, session_factory, inbound, now
):
    from dzmm_bot.core.schema import OutboundRecord

    stored, _ = repository.accept_inbound(inbound)
    outbound = repository.enqueue_outbound(stored.id, "reply")
    claimed = repository.claim_outbound("worker-a", now, 30)

    confirmed = repository.confirm_sent(
        outbound.id, "worker-a", claimed.lease_token, "sent-1", now
    )

    assert confirmed is True
    with session_factory() as session:
        persisted = session.get(OutboundRecord, outbound.id)
        assert persisted.status == "sent"
        assert persisted.platform_sent_id == "sent-1"
    assert repository.claim_outbound("worker-b", now + timedelta(seconds=31), 30) is None


def test_stale_outbound_confirmation_is_rejected_after_reclaim(
    repository, session_factory, inbound, now
):
    from dzmm_bot.core.schema import OutboundRecord

    stored, _ = repository.accept_inbound(inbound)
    outbound = repository.enqueue_outbound(stored.id, "reply")
    first = repository.claim_outbound("worker-a", now, 30)
    second = repository.claim_outbound("worker-b", now + timedelta(seconds=31), 30)

    assert second.lease_token != first.lease_token
    assert (
        repository.confirm_sent(
            outbound.id,
            "worker-a",
            first.lease_token,
            "sent-by-a",
            now + timedelta(seconds=31),
        )
        is False
    )
    assert (
        repository.confirm_sent(
            outbound.id,
            "worker-b",
            second.lease_token,
            "sent-by-b",
            now + timedelta(seconds=32),
        )
        is True
    )
    with session_factory() as session:
        persisted = session.get(OutboundRecord, outbound.id)
        assert persisted.platform_sent_id == "sent-by-b"


def test_outbound_confirmation_requires_owner_token_and_live_lease(
    repository, inbound, now
):
    stored, _ = repository.accept_inbound(inbound)
    outbound = repository.enqueue_outbound(stored.id, "reply")
    claimed = repository.claim_outbound("worker-a", now, 30)

    assert (
        repository.confirm_sent(
            outbound.id, "worker-b", claimed.lease_token, "sent-1", now
        )
        is False
    )
    assert (
        repository.confirm_sent(
            outbound.id, "worker-a", uuid4(), "sent-1", now
        )
        is False
    )
    assert (
        repository.confirm_sent(
            outbound.id,
            "worker-a",
            claimed.lease_token,
            "sent-1",
            now + timedelta(seconds=30),
        )
        is False
    )


def test_worker_command_is_claimed_once_then_acknowledged(repository, now):
    command = repository.enqueue_worker_command("start_auth")
    claimed = repository.claim_worker_command("worker-a", now, 30)
    completed = repository.complete_worker_command(
        claimed.id, "worker-a", claimed.lease_token, "succeeded", now
    )

    assert claimed.id == command.id
    assert completed is True
    assert repository.claim_worker_command("worker-b", now + timedelta(seconds=31), 30) is None


def test_stale_worker_command_completion_is_rejected_after_reclaim(repository, now):
    command = repository.enqueue_worker_command("start_auth")
    first = repository.claim_worker_command("worker-a", now, 30)
    second = repository.claim_worker_command(
        "worker-b", now + timedelta(seconds=31), 30
    )

    assert second.lease_token != first.lease_token
    assert (
        repository.complete_worker_command(
            command.id,
            "worker-a",
            first.lease_token,
            "succeeded",
            now + timedelta(seconds=31),
        )
        is False
    )
    assert (
        repository.complete_worker_command(
            command.id,
            "worker-b",
            second.lease_token,
            "succeeded",
            now + timedelta(seconds=32),
        )
        is True
    )


def test_worker_command_completion_requires_owner_token_and_live_lease(
    repository, now
):
    command = repository.enqueue_worker_command("start_auth")
    claimed = repository.claim_worker_command("worker-a", now, 30)

    assert (
        repository.complete_worker_command(
            command.id, "worker-b", claimed.lease_token, "succeeded", now
        )
        is False
    )
    assert (
        repository.complete_worker_command(
            command.id, "worker-a", uuid4(), "succeeded", now
        )
        is False
    )
    assert (
        repository.complete_worker_command(
            command.id,
            "worker-a",
            claimed.lease_token,
            "succeeded",
            now + timedelta(seconds=30),
        )
        is False
    )


def test_worker_heartbeat_is_persisted(repository, now):
    heartbeat = WorkerHeartbeat("worker-a", LoginState.READY, now)

    first = repository.record_worker_heartbeat(heartbeat)
    second = repository.record_worker_heartbeat(
        WorkerHeartbeat("worker-a", LoginState.AUTH_REQUIRED, now + timedelta(seconds=5))
    )

    assert second.id == first.id
    assert second.login_state == LoginState.AUTH_REQUIRED.value
    assert second.recorded_at == now + timedelta(seconds=5)


def test_reply_template_defaults_seed_once_and_preserve_an_edit(repository):
    """Fails if a later default seed overwrites an administrator's template."""
    repository.ensure_reply_templates()
    repository.set_reply_template("/余额", "shown", "{昵称} 有 {余额} 币。")
    repository.ensure_reply_templates()

    assert (
        repository.get_reply_template("/余额", "shown").template
        == "{昵称} 有 {余额} 币。"
    )


def test_game_settings_default_to_the_initial_economy(repository):
    settings = repository.get_game_settings()

    assert (settings.currency_name, settings.onboarding_bonus, settings.checkin_reward) == (
        "摸鱼币",
        0,
        5,
    )


@pytest.mark.parametrize(
    "currency_name,onboarding_bonus,checkin_reward",
    [("", 0, 5), (" " * 13, 0, 5), ("工分", -1, 5), ("工分", 0, 1000)],
)
def test_game_settings_reject_invalid_values(
    repository, currency_name, onboarding_bonus, checkin_reward
):
    with pytest.raises(ValueError):
        repository.set_game_settings(
            currency_name, onboarding_bonus, checkin_reward
        )


def test_template_validation_rejects_a_variable_unavailable_to_its_scenario():
    """Fails if a shop-only variable can leak into a balance reply."""
    from dzmm_bot.core.reply_templates import validate_template

    with pytest.raises(ValueError, match="不支持"):
        validate_template("/余额", "shown", "{商店列表}")


@pytest.fixture
def migrated_postgres_url():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not set")

    schema = f"test_runtime_{uuid4().hex}"
    admin_engine = create_engine(database_url)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    test_url = make_url(database_url).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", test_url.render_as_string(hide_password=False))
    command.upgrade(config, "head")
    try:
        yield test_url
    finally:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


def test_migration_creates_all_runtime_tables(migrated_postgres_url):
    engine = create_engine(migrated_postgres_url)
    inspector = inspect(engine)

    assert {
        "inbound_messages",
        "outbound_messages",
        "worker_instances",
        "worker_commands",
        "login_sessions",
        "audit_events",
        "command_definitions",
        "command_reply_templates",
        "game_settings",
        "users",
        "daily_checkins",
        "items",
        "user_items",
    } <= set(inspector.get_table_names())
    assert "ux_inbound_messages_platform_message_id" in {
        index["name"] for index in inspector.get_indexes("inbound_messages")
    }
    assert "ix_outbound_messages_claim" in {
        index["name"] for index in inspector.get_indexes("outbound_messages")
    }
    assert "ix_worker_commands_claim" in {
        index["name"] for index in inspector.get_indexes("worker_commands")
    }
    assert "lease_token" in {
        column["name"] for column in inspector.get_columns("outbound_messages")
    }
    assert "lease_token" in {
        column["name"] for column in inspector.get_columns("worker_commands")
    }
    assert {"command", "scenario"} in {
        set(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("command_reply_templates")
    }
    with engine.connect() as connection:
        template_count = connection.scalar(
            text("SELECT count(*) FROM command_reply_templates")
        )
        help_command = connection.scalar(
            text("SELECT command FROM command_definitions WHERE command = '/帮助'")
        )
    assert template_count == 13
    assert help_command == "/帮助"


def test_postgres_enforces_uniqueness_and_atomic_enqueue(
    migrated_postgres_url, inbound, now
):
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import InboundRecord, OutboundRecord

    factory = sessionmaker(create_engine(migrated_postgres_url), expire_on_commit=False)
    repository = CoreRepository(factory)

    with pytest.raises(RuntimeError):
        with repository.transaction():
            stored, _ = repository.accept_inbound(inbound)
            repository.enqueue_outbound(stored.id, "reply")
            raise RuntimeError("roll back")

    with factory() as session:
        assert session.scalar(select(InboundRecord)) is None
        assert session.scalar(select(OutboundRecord)) is None

    first, inserted = repository.accept_inbound(inbound)
    duplicate, duplicate_inserted = repository.accept_inbound(inbound)
    assert inserted is True
    assert duplicate_inserted is False
    assert duplicate.id == first.id

    outbound = repository.enqueue_outbound(first.id, "reply")
    first_claim = repository.claim_outbound("worker-a", now, 30)
    assert first_claim.id == outbound.id
    claimed = repository.claim_outbound("worker-b", now + timedelta(seconds=31), 30)
    assert claimed.id == outbound.id
    assert repository.claim_outbound("worker-c", now + timedelta(seconds=32), 30) is None
    assert (
        repository.confirm_sent(
            outbound.id,
            "worker-a",
            first_claim.lease_token,
            "stale-send",
            now + timedelta(seconds=31),
        )
        is False
    )
    assert (
        repository.confirm_sent(
            outbound.id,
            "worker-b",
            claimed.lease_token,
            "sent-1",
            now + timedelta(seconds=32),
        )
        is True
    )
    assert repository.claim_outbound("worker-c", now + timedelta(seconds=62), 30) is None

    heartbeat = repository.record_worker_heartbeat(
        WorkerHeartbeat("worker-a", LoginState.READY, now)
    )
    updated = repository.record_worker_heartbeat(
        WorkerHeartbeat(
            "worker-a", LoginState.AUTH_REQUIRED, now + timedelta(seconds=5)
        )
    )
    assert updated.id == heartbeat.id
    assert updated.recorded_at == now + timedelta(seconds=5)


def test_postgres_concurrent_claims_and_upserts_are_atomic(
    migrated_postgres_url, inbound, now
):
    from dzmm_bot.core.repository import CoreRepository

    factory = sessionmaker(create_engine(migrated_postgres_url), expire_on_commit=False)
    repository = CoreRepository(factory)

    duplicate_barrier = Barrier(2)

    def accept_inbound():
        duplicate_barrier.wait()
        return repository.accept_inbound(inbound)

    with ThreadPoolExecutor(max_workers=2) as executor:
        accepted = list(executor.map(lambda _: accept_inbound(), range(2)))
    assert sorted(inserted for _, inserted in accepted) == [False, True]
    assert len({record.id for record, _ in accepted}) == 1

    inbound_record = accepted[0][0]
    outbound = repository.enqueue_outbound(inbound_record.id, "reply")
    claim_barrier = Barrier(2)

    def claim_outbound(worker_id):
        claim_barrier.wait()
        return repository.claim_outbound(worker_id, now, 30)

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim_outbound, ("worker-a", "worker-b")))
    assert [claim.id for claim in claims if claim is not None] == [outbound.id]

    heartbeat_barrier = Barrier(2)

    def record_heartbeat(state):
        heartbeat_barrier.wait()
        return repository.record_worker_heartbeat(
            WorkerHeartbeat("worker-a", state, now)
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        heartbeats = list(
            executor.map(record_heartbeat, (LoginState.READY, LoginState.AUTH_REQUIRED))
        )
    assert len({heartbeat.id for heartbeat in heartbeats}) == 1
