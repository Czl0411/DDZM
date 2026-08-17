from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Uuid,
    create_engine,
    inspect,
    text,
)


ROOT = Path(__file__).resolve().parents[2]


def _legacy_database(database_url: str) -> None:
    engine = create_engine(database_url)
    metadata = MetaData()
    users = Table(
        "users",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("platform_id", String(255), nullable=False),
        Column("display_name", String(64), nullable=False),
        Column("employee_number", Integer, nullable=False),
        Column("joined_at", DateTime(timezone=True), nullable=False),
    )
    Table(
        "random_event_settings",
        metadata,
        Column("id", Integer, primary_key=True),
    )
    Table(
        "inbound_messages",
        metadata,
        Column("id", Uuid, primary_key=True),
    )
    random_events = Table(
        "random_events",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("group_key", String(255), nullable=False),
        Column("state", String(16), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE UNIQUE INDEX ux_random_events_one_active_group "
                "ON random_events (group_key) "
                "WHERE state IN ('signup', 'in_progress')"
            )
        )
        connection.execute(
            users.insert(),
            [
                {
                    "id": UUID(int=1),
                    "platform_id": "duplicate-1",
                    "display_name": "同名",
                    "employee_number": 1,
                    "joined_at": datetime(2026, 8, 1, tzinfo=UTC),
                },
                {
                    "id": UUID(int=2),
                    "platform_id": "duplicate-2",
                    "display_name": "同名",
                    "employee_number": 2,
                    "joined_at": datetime(2026, 8, 2, tzinfo=UTC),
                },
                {
                    "id": UUID(int=3),
                    "platform_id": "generated-collision",
                    "display_name": "同名#0001",
                    "employee_number": 3,
                    "joined_at": datetime(2026, 8, 3, tzinfo=UTC),
                },
                {
                    "id": UUID(int=4),
                    "platform_id": "unique",
                    "display_name": "唯一名称",
                    "employee_number": 4,
                    "joined_at": datetime(2026, 8, 4, tzinfo=UTC),
                },
            ],
        )
        connection.execute(text("INSERT INTO random_event_settings (id) VALUES (1)"))
        connection.execute(
            random_events.insert(),
            {
                "id": UUID(int=10),
                "group_key": "default",
                "state": "ended",
            },
        )


def _display_name_is_unique(inspector) -> bool:
    if any(
        constraint["column_names"] == ["display_name"]
        for constraint in inspector.get_unique_constraints("users")
    ):
        return True
    return any(
        index["unique"] and index["column_names"] == ["display_name"]
        for index in inspector.get_indexes("users")
    )


def test_random_event_tipping_migration_resolves_names_and_round_trips(
    tmp_path, monkeypatch
):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'random-event-tipping.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    config = Config(str(ROOT / "alembic.ini"))
    _legacy_database(database_url)
    command.stamp(config, "20260815_43")

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    with engine.connect() as connection:
        names = connection.execute(
            text("SELECT display_name FROM users ORDER BY employee_number")
        ).scalars().all()
        duration = connection.execute(
            text(
                "SELECT tipping_duration_seconds "
                "FROM random_event_settings WHERE id = 1"
            )
        ).scalar_one()
        index_sql = connection.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'index' "
                "AND name = 'ux_random_events_one_active_group'"
            )
        ).scalar_one()

    assert names == [
        "同名#0001#0001",
        "同名#0002",
        "同名#0001#0003",
        "唯一名称",
    ]
    assert duration == 120
    assert {"tipping_started_at", "tipping_deadline"} <= {
        column["name"] for column in inspector.get_columns("random_events")
    }
    assert "random_event_tips" in inspector.get_table_names()
    assert _display_name_is_unique(inspector)
    assert "'tipping'" in index_sql

    command.downgrade(config, "20260815_43")

    inspector = inspect(engine)
    assert "random_event_tips" not in inspector.get_table_names()
    assert "tipping_duration_seconds" not in {
        column["name"] for column in inspector.get_columns("random_event_settings")
    }
    assert "tipping_deadline" not in {
        column["name"] for column in inspector.get_columns("random_events")
    }
    assert not _display_name_is_unique(inspector)
    with engine.connect() as connection:
        index_sql = connection.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'index' "
                "AND name = 'ux_random_events_one_active_group'"
            )
        ).scalar_one()
    assert "'tipping'" not in index_sql
