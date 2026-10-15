from datetime import UTC, datetime, timedelta

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


def test_mistrealm_channel_moderation(tmp_path):
    from dzmm_bot.core.schema import (
        MistrealmChannelMessageRecord,
        MistrealmPlayerRecord,
    )

    repository = make_repository(tmp_path)
    now = datetime(2026, 10, 15, 12, tzinfo=UTC)
    with repository._session_factory.begin() as session:
        player = MistrealmPlayerRecord(
            platform_uid="traveler-1",
            name="旅人",
            created_at=now,
            updated_at=now,
            rate_limits={},
        )
        session.add(player)
        session.flush()
        message = MistrealmChannelMessageRecord(
            player_id=player.id,
            kind="text",
            text="有人约战吗？",
            created_at=now,
        )
        session.add(message)
        session.flush()
        player_id, message_id = player.id, message.id

    overview = repository.mistrealm_channel_overview()
    assert overview["items"][0]["text"] == "有人约战吗？"
    assert repository.delete_mistrealm_channel_message(message_id, now)
    muted = repository.mute_mistrealm_channel_player(player_id, 60, now)
    assert muted["muted_until"] == (now + timedelta(hours=1)).isoformat()
    item = repository.mistrealm_channel_overview()["items"][0]
    assert item["deleted"] is True
    assert datetime.fromisoformat(item["player"]["muted_until"]) == datetime.fromisoformat(
        muted["muted_until"]
    )
