from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, Uuid, create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[2]


def test_profile_image_migration_backfills_and_downgrades(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'profile-images.db'}"
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
        Column("profile_text", Text, nullable=False),
        Column("rank_id", Uuid),
        Column("department_id", Uuid),
        Column("joined_at", DateTime(timezone=True), nullable=False),
    )
    outbound_messages = Table(
        "outbound_messages",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("text", Text, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            users.insert(),
            {
                "id": uuid4(), "platform_id": "legacy", "display_name": "历史员工",
                "employee_number": 9999, "balance": 30, "profile_text": "旧档案",
                "rank_id": None, "department_id": None,
                "joined_at": datetime(2026, 8, 13, tzinfo=UTC),
            },
        )
        connection.execute(
            outbound_messages.insert(),
            {"id": uuid4(), "text": "历史文本消息"},
        )
    command.stamp(config, "20260812_40")

    command.upgrade(config, "20260813_41")

    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    assert {"profile_image_url", "profile_version"} <= columns
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT profile_image_url, profile_version FROM users WHERE platform_id = 'legacy'")
        ).one() == (None, 0)
        assert connection.execute(
            text("SELECT content_type, image_url, image_alt FROM outbound_messages")
        ).one() == ("text", None, None)

    command.downgrade(config, "20260812_40")
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    assert "profile_image_url" not in columns
    assert "profile_version" not in columns
    outbound_columns = {
        column["name"] for column in inspect(engine).get_columns("outbound_messages")
    }
    assert "content_type" not in outbound_columns
    assert "image_url" not in outbound_columns
    assert "image_alt" not in outbound_columns
