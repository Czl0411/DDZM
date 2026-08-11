from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Uuid, create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[2]


def test_employee_number_migration_backfills_by_joined_at_then_uuid(
    tmp_path, monkeypatch
):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'employees.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(database_url)
    metadata = MetaData()
    users = Table(
        "users",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("platform_id", String(255), nullable=False),
        Column("display_name", String(64), nullable=False),
        Column("balance", Integer, nullable=False),
        Column("joined_at", DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    early = datetime(2026, 8, 1, tzinfo=UTC)
    late = datetime(2026, 8, 2, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            users.insert(),
            [
                {
                    "id": UUID(int=3),
                    "platform_id": "late",
                    "display_name": "晚",
                    "balance": 0,
                    "joined_at": late,
                },
                {
                    "id": UUID(int=1),
                    "platform_id": "early-1",
                    "display_name": "早甲",
                    "balance": 0,
                    "joined_at": early,
                },
                {
                    "id": UUID(int=2),
                    "platform_id": "early-2",
                    "display_name": "早乙",
                    "balance": 0,
                    "joined_at": early,
                },
            ],
        )
    command.stamp(config, "20260811_36")

    command.upgrade(config, "head")

    columns = {column["name"]: column for column in inspect(engine).get_columns("users")}
    assert columns["employee_number"]["nullable"] is False
    assert any(
        constraint["column_names"] == ["employee_number"]
        for constraint in inspect(engine).get_unique_constraints("users")
    )
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT platform_id, employee_number "
                "FROM users ORDER BY employee_number"
            )
        ).all()
        assert rows == [("early-1", 1), ("early-2", 2), ("late", 3)]
        assert connection.execute(
            text(
                "SELECT next_number FROM employee_number_counters WHERE id = 1"
            )
        ).scalar_one() == 4
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20260811_37"
