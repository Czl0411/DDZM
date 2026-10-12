from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Column, MetaData, Table, Uuid, create_engine, inspect


ROOT = Path(__file__).resolve().parents[2]


def test_delete_draft_migration_upgrades_database_already_at_revision_81(
    tmp_path, monkeypatch
):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'black-history.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    engine = create_engine(database_url)
    metadata = MetaData()
    Table("users", metadata, Column("id", Uuid, primary_key=True))
    metadata.create_all(engine)
    config = Config(str(ROOT / "alembic.ini"))
    command.stamp(config, "20260918_81")

    command.upgrade(config, "head")

    assert "black_history_delete_drafts" in inspect(engine).get_table_names()

    command.downgrade(config, "20260918_81")

    assert "black_history_delete_drafts" not in inspect(engine).get_table_names()
