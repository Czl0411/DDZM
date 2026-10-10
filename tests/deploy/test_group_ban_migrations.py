from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import Column, MetaData, String, Table, Uuid, create_engine, inspect, select


ROOT = Path(__file__).resolve().parents[2]


def test_group_ban_migrations_upgrade_and_downgrade(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'group-ban.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    engine = create_engine(database_url)
    metadata = MetaData()
    groups = Table("group_chats", metadata, Column("id", Uuid, primary_key=True))
    Table("inbound_messages", metadata, Column("id", Uuid, primary_key=True))
    metadata.create_all(engine)
    config = Config(str(ROOT / "alembic.ini"))
    command.stamp(config, "20261010_101")

    command.upgrade(config, "20261010_103")

    columns = {column["name"] for column in inspect(engine).get_columns("group_chats")}
    assert "ban_operator_platform_ids" in columns
    assert "group_ban_requests" in inspect(engine).get_table_names()
    with engine.begin() as connection:
        connection.execute(groups.insert().values(id=UUID(int=1)))
        saved = connection.scalar(select(Table("group_chats", MetaData(), autoload_with=engine).c.ban_operator_platform_ids))
    assert saved == []

    command.downgrade(config, "20261010_101")
    assert "group_ban_requests" not in inspect(engine).get_table_names()
    assert "ban_operator_platform_ids" not in {
        column["name"] for column in inspect(engine).get_columns("group_chats")
    }
