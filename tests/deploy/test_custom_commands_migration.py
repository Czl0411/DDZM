from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Boolean, Column, MetaData, String, Table, Text, create_engine, inspect, select


ROOT = Path(__file__).resolve().parents[2]


def test_custom_commands_migration_preserves_builtin_commands(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'custom-commands.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    engine = create_engine(database_url)
    metadata = MetaData()
    commands = Table(
        "command_definitions", metadata,
        Column("command", String(32), primary_key=True),
        Column("syntax", Text, nullable=False),
        Column("description", Text, nullable=False),
        Column("enabled", Boolean, nullable=False),
        Column("created_at", String(64), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(commands.insert().values(
            command="/打卡", syntax="/打卡", description="签到",
            enabled=True, created_at="2026-10-12 12:00:00",
        ))
    config = Config(str(ROOT / "alembic.ini"))
    command.stamp(config, "20261010_103")

    command.upgrade(config, "20261012_104")

    columns = {column["name"] for column in inspect(engine).get_columns("command_definitions")}
    assert {"is_custom", "reply_type", "reply_value"} <= columns
    assert "custom_command_image_uploads" in inspect(engine).get_table_names()
    upgraded_commands = Table("command_definitions", MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        row = connection.execute(select(upgraded_commands).where(
            upgraded_commands.c.command == "/打卡"
        )).one()
    assert row.is_custom is False
    assert row.reply_type is None
    assert row.reply_value is None
