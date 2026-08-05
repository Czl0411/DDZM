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


def test_activity_settings_default_to_the_initial_rules(repository):
    settings = repository.get_activity_settings()

    assert settings.report_times == ["12:00", "16:00", "20:00", "23:59"]
    assert [
        (rule.level, rule.character_threshold, rule.reward) for rule in settings.rules
    ] == [
        (1, 10, 1),
        (2, 25, 2),
        (3, 60, 3),
        (4, 90, 4),
        (5, 140, 5),
        (6, 190, 6),
        (7, 250, 7),
        (8, 330, 8),
        (9, 410, 9),
        (10, 500, 10),
    ]


def test_system_outbound_can_be_claimed(repository, now):
    outbound = repository.enqueue_system_outbound("系统推送")
    claimed = repository.claim_outbound("worker-a", now, 30)

    assert claimed.id == outbound.id
    assert claimed.inbound_message_id is None


def test_activity_counts_joined_non_command_text_without_whitespace(repository, now):
    repository.create_user("u1", "小明", now, 0)

    repository.record_activity("u1", now, "你 好\n！")
    repository.record_activity("u1", now, "/我")
    repository.record_activity("unknown", now, "一二三四五六七八九十")
    repository.record_activity("u1", now, "甲乙丙丁戊己庚")

    assert repository.personal_activity("u1", now).level == 1


def test_user_page_returns_newest_records_and_total(repository, now):
    for index in range(21):
        repository.create_user(
            f"u-{index}", f"员工{index}", now + timedelta(minutes=index), 0
        )

    users, total = repository.list_users_page(1, 20)
    final_page, final_total = repository.list_users_page(2, 20)

    assert total == 21
    assert [user.display_name for user in users] == [
        f"员工{index}" for index in range(20, 0, -1)
    ]
    assert final_total == 21
    assert [user.display_name for user in final_page] == ["员工0"]


def test_item_page_returns_newest_records_and_total(repository, session_factory, now):
    from dzmm_bot.core.schema import ItemRecord

    with session_factory.begin() as session:
        for index in range(21):
            session.add(
                ItemRecord(
                    name=f"物品{index}",
                    description="说明",
                    price=index,
                    stock=1,
                    enabled=True,
                    created_at=now + timedelta(minutes=index),
                )
            )

    items, total = repository.list_active_items_page(2, 20)

    assert total == 21
    assert [item.name for item in items] == ["物品0"]


def test_daily_jobs_backfill_current_day_history_and_legacy_checkin_income(
    repository, session_factory
):
    from dzmm_bot.core.schema import BEIJING, DailyCheckinRecord, UserRecord

    joined_at = datetime(2026, 8, 5, 9, 0, tzinfo=BEIJING)
    checkin_at = datetime(2026, 8, 5, 10, 0, tzinfo=BEIJING)
    now = datetime(2026, 8, 5, 19, 45, tzinfo=BEIJING)
    user, _ = repository.create_user("u1", "小明", joined_at, 0)
    repository.accept_inbound(
        InboundMessage("historic-text", "u1", "一二三四五六七八九十", checkin_at)
    )
    with session_factory.begin() as session:
        session.get(UserRecord, user.id).balance = 5
        session.add(
            DailyCheckinRecord(
                id=uuid4(),
                user_id=user.id,
                checkin_date=checkin_at.date(),
                checked_in_at=checkin_at,
            )
        )

    repository.run_daily_jobs(now)

    assert repository.personal_activity("u1", now).level == 1
    assert repository.today_income(user.id, now) == 5
    repository.run_daily_jobs(now + timedelta(minutes=1))
    assert repository.find_user("u1").balance == 5
    assert repository.today_income(user.id, now) == 5


def test_activity_settings_reject_non_increasing_thresholds(repository):
    from dzmm_bot.core.repository import ActivityLevelRule

    with pytest.raises(ValueError, match="门槛"):
        repository.set_activity_settings(
            [ActivityLevelRule(level, 10, level) for level in range(1, 11)],
            ["12:00"],
        )


def test_activity_settlement_is_once_and_negative_does_not_reduce_today_income(
    repository,
):
    from dzmm_bot.core.schema import BEIJING

    yesterday = datetime(2026, 8, 5, 23, 59, tzinfo=BEIJING)
    today = datetime(2026, 8, 6, 0, 0, tzinfo=BEIJING)
    user, _ = repository.create_user("u1", "小明", yesterday, 0)
    repository.record_activity("u1", yesterday, "一二三四五六七八九十")

    repository.run_daily_jobs(today)
    repository.record_balance_change(
        user.id, -4, "penalty", datetime(2026, 8, 6, 1, 0, tzinfo=BEIJING)
    )

    assert repository.find_user("u1").balance == -3
    assert repository.today_income(
        user.id, datetime(2026, 8, 6, 2, 0, tzinfo=BEIJING)
    ) == 1
    repository.run_daily_jobs(today + timedelta(minutes=1))
    assert repository.find_user("u1").balance == -3


def test_due_income_report_is_queued_once_and_empty_slot_is_skipped(repository, now):
    from dzmm_bot.core.schema import BEIJING

    repository.run_daily_jobs(datetime(2026, 8, 5, 12, 0, tzinfo=BEIJING))
    assert repository.claim_outbound("worker-a", now, 30) is None

    repository.create_user(
        "u1", "小明", datetime(2026, 8, 5, 13, 0, tzinfo=BEIJING), 3
    )
    repository.run_daily_jobs(datetime(2026, 8, 5, 16, 0, tzinfo=BEIJING))

    assert repository.claim_outbound("worker-a", now, 30).text.startswith("今日收益榜")
    repository.run_daily_jobs(datetime(2026, 8, 5, 16, 1, tzinfo=BEIJING))
    assert repository.claim_outbound("worker-b", now, 30) is None


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


def test_manual_login_lease_is_exclusive_and_expires(repository):
    from dzmm_bot.core.repository import ManualLoginBusyError
    from dzmm_bot.core.schema import BEIJING

    now = datetime(2026, 8, 5, 12, tzinfo=BEIJING)
    lease = repository.start_manual_login("alice-id", "alice", now)

    assert lease.operator_name == "alice"
    with pytest.raises(ManualLoginBusyError):
        repository.start_manual_login("bob-id", "bob", now)

    start = repository.claim_worker_command("worker", now, 30)
    assert start.command == "start_auth"
    assert repository.complete_worker_command(
        start.id, "worker", start.lease_token, "completed", now
    )
    assert repository.manual_login_lease(now + timedelta(seconds=181)) is None
    command = repository.claim_worker_command("worker", now + timedelta(seconds=181), 30)
    assert command.command == "cancel_auth"


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
        "admin_accounts",
        "admin_sessions",
        "admin_idempotency_records",
        "admin_config_revisions",
        "manual_login_leases",
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
