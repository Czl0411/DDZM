from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Column,
    MetaData,
    Table,
    Uuid,
    create_engine,
    inspect,
)


ROOT = Path(__file__).resolve().parents[2]

EXPECTED_TABLES = {
    "department_allowances",
    "department_game_plays",
}

BASE_REVISION = "20261002_77"


def migrated_engine(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'allowance.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    engine = create_engine(database_url)
    metadata = MetaData()
    Table("group_chats", metadata, Column("id", Uuid, primary_key=True))
    Table("users", metadata, Column("id", Uuid, primary_key=True))
    Table(
        "departments",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("name", Uuid),
    )
    metadata.create_all(engine)

    config = Config(str(ROOT / "alembic.ini"))
    command.stamp(config, BASE_REVISION)
    command.upgrade(config, "head")
    return engine, config


def test_department_allowance_migration_creates_every_table(tmp_path, monkeypatch):
    engine, _ = migrated_engine(tmp_path, monkeypatch)

    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())

    columns = {column["name"] for column in inspect(engine).get_columns("departments")}
    assert "allowance_kind" in columns
