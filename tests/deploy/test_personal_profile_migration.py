from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Uuid, create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[2]


def test_personal_profile_migration_backfills_profiles_and_defaults(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'profiles.db'}"
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
        Column("employee_number", Integer, nullable=False),
        Column("balance", Integer, nullable=False),
        Column("rank_id", Uuid),
        Column("department_id", Uuid),
        Column("joined_at", DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            users.insert(),
            {
                "id": uuid4(),
                "platform_id": "legacy",
                "display_name": "历史员工",
                "employee_number": 9999,
                "balance": 30,
                "rank_id": None,
                "department_id": None,
                "joined_at": datetime(2026, 8, 12, tzinfo=UTC),
            },
        )
    command.stamp(config, "20260811_38")

    command.upgrade(config, "20260812_39")

    assert inspect(engine).get_columns("users")[-1]["name"] == "profile_text"
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT profile_text FROM users WHERE platform_id = 'legacy'")
        ).scalar_one() == ""
        assert connection.execute(
            text("SELECT edit_cost, shared_labor, version FROM profile_settings WHERE id = 1")
        ).one() == (10, 5, 0)
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260812_39"

    command.downgrade(config, "20260811_38")
    assert "profile_text" not in {
        column["name"] for column in inspect(engine).get_columns("users")
    }
    assert "profile_settings" not in inspect(engine).get_table_names()
