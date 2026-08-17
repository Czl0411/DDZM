from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    create_engine,
    inspect,
    text,
)


ROOT = Path(__file__).resolve().parents[2]


def test_outbound_reference_and_submission_migrations_round_trip(
    tmp_path, monkeypatch
):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'outbound-submissions.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(database_url)
    metadata = MetaData()
    outbound = Table(
        "outbound_messages",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("destination_chatroom_id", String(255)),
        Column("status", String(32), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("reply_index", Integer, nullable=False),
        Column("text", Text, nullable=False),
    )
    Table("random_event_settings", metadata, Column("id", Integer, primary_key=True))
    Table(
        "users",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("display_name", String(64), nullable=False),
        Column("employee_number", Integer, nullable=False),
    )
    Table("inbound_messages", metadata, Column("id", Uuid, primary_key=True))
    random_events = Table(
        "random_events",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("group_key", String(255), nullable=False),
        Column("state", String(16), nullable=False),
    )
    Table("random_event_scenes", metadata, Column("id", Uuid, primary_key=True))
    metadata.create_all(engine)
    group_id = uuid4()
    direct_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE UNIQUE INDEX ux_random_events_one_active_group "
                "ON random_events (group_key) "
                "WHERE state IN ('signup', 'in_progress')"
            )
        )
        connection.execute(
            outbound.insert(),
            [
                {
                    "id": group_id,
                    "destination_chatroom_id": None,
                    "status": "pending",
                    "created_at": datetime(2026, 8, 15, tzinfo=UTC),
                    "reply_index": 0,
                    "text": "group",
                },
                {
                    "id": direct_id,
                    "destination_chatroom_id": "direct-1",
                    "status": "pending",
                    "created_at": datetime(2026, 8, 15, tzinfo=UTC),
                    "reply_index": 0,
                    "text": "direct",
                },
            ],
        )
        connection.execute(text("INSERT INTO random_event_settings (id) VALUES (1)"))
    command.stamp(config, "20260813_41")

    command.upgrade(config, "head")

    inspector = inspect(engine)
    outbound_columns = {
        column["name"] for column in inspector.get_columns("outbound_messages")
    }
    assert {
        "delivery_key",
        "reference_message_id",
        "reference_sender_platform_id",
        "reference_content_type",
        "reference_text",
    } <= outbound_columns
    assert "random_event_submissions" in inspector.get_table_names()
    assert "random_event_submission_counters" in inspector.get_table_names()
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT delivery_key FROM outbound_messages "
                "WHERE id = :id"
            ),
            {"id": group_id.hex},
        ).scalar_one() == "__group__"
        assert connection.execute(
            text(
                "SELECT delivery_key FROM outbound_messages "
                "WHERE id = :id"
            ),
            {"id": direct_id.hex},
        ).scalar_one() == "direct-1"
        settings = connection.execute(
            text(
                "SELECT submission_enabled, submission_draft_timeout_minutes, "
                "submission_max_participants, submission_default_target_rounds, "
                "submission_default_event_reward, submission_approval_reward "
                "FROM random_event_settings WHERE id = 1"
            )
        ).one()
        counter = connection.execute(
            text("SELECT id, next_number FROM random_event_submission_counters")
        ).one()
    assert settings == (1, 30, 99, 10, 6, 10)
    assert counter == (1, 1)

    command.downgrade(config, "20260813_41")

    inspector = inspect(engine)
    assert "random_event_submissions" not in inspector.get_table_names()
    assert "delivery_key" not in {
        column["name"] for column in inspector.get_columns("outbound_messages")
    }
