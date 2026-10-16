from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Column, Integer, MetaData, Table, Uuid, create_engine, inspect, text


def test_equipment_migration_roundtrip_preserves_existing_shop(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'equipment.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    engine = create_engine(database_url)
    metadata = MetaData()
    for name in ("users", "group_chats", "inbound_messages"):
        Table(name, metadata, Column("id", Uuid, primary_key=True))
    Table("items", metadata, Column("public_number", Integer, primary_key=True), Column("price", Integer))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO items (public_number, price) VALUES (1, 99)"))
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.stamp(config, "20261012_103")
    command.upgrade(config, "head")
    expected = {"equipment_items", "equipment_ownerships", "equipment_purchases"}
    assert expected <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM equipment_items")) == 10
        assert connection.scalar(text("SELECT price FROM items WHERE public_number = 1")) == 99
        assert connection.scalar(text("SELECT daily_income FROM equipment_items WHERE public_number = 1")) == 2
    command.downgrade(config, "20261012_103")
    assert not expected & set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT price FROM items WHERE public_number = 1")) == 99
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM equipment_items")) == 10
    engine.dispose()
