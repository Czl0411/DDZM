from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def make_repository(tmp_path):
    from dzmm_bot.admin.repository import AdminRepository
    from dzmm_bot.core.schema import Base

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'admin.db'}")
    Base.metadata.create_all(engine)
    return AdminRepository(sessionmaker(engine, expire_on_commit=False))


def test_disabling_account_revokes_its_session(tmp_path):
    repository = make_repository(tmp_path)
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)
    account = repository.create_account("alice", "strong-password")

    session_token = repository.create_session(account.id, now)
    assert repository.resolve_session(session_token, now).username == "alice"

    repository.set_account_active(account.id, False)

    assert repository.resolve_session(session_token, now) is None


def test_completed_idempotency_key_replays_first_result(tmp_path):
    repository = make_repository(tmp_path)
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)

    assert repository.reserve_idempotency_key("super_admin", "key-1", now) is None
    repository.complete_idempotency_key(
        "super_admin", "key-1", 201, {"id": "item-1"}, now
    )

    assert repository.reserve_idempotency_key("super_admin", "key-1", now) == (
        201,
        {"id": "item-1"},
    )
