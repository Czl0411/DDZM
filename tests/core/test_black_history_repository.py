from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def repository() -> CoreRepository:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return CoreRepository(sessionmaker(engine, expire_on_commit=False))


def test_recording_deducts_recorder_once_and_owns_entry(repository, now) -> None:
    repository.create_user("recorder", "记录者", now, 1)
    repository.create_user("subject", "当事人", now, 0)
    group = repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=black-history", now
    )

    first = repository.record_black_history(
        "recorder", "subject", group.id, "source-1", "text", "原话", None, None, now,
    )
    duplicate = repository.record_black_history(
        "recorder", "subject", group.id, "source-1", "text", "原话", None, None, now,
    )

    assert first.status == "recorded"
    assert duplicate.status == "duplicate"
    assert repository.find_user("recorder").balance == 0


def test_delete_only_removes_own_entry_and_only_charges_on_success(repository, now) -> None:
    repository.create_user("owner", "本人", now, 10)
    repository.create_user("other", "别人", now, 10)
    group = repository.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=black-history-delete", now
    )
    entry = repository.record_black_history(
        "other", "other", group.id, "source-other", "text", "别人的记录",
        None, None, now,
    )

    rejected = repository.delete_own_black_history("owner", entry.entry_id, now)
    deleted = repository.delete_own_black_history("other", entry.entry_id, now)

    assert rejected.status == "not_found"
    assert repository.find_user("owner").balance == 10
    assert deleted.status == "deleted"
    assert deleted.remaining_count == 0
    assert repository.find_user("other").balance == 4
