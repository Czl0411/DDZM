from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


TABLES = {"mahjong_rooms", "mahjong_requests", "mahjong_messages"}


def test_upgrade_downgrade_and_constraints(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'mahjong-migration.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", url)
    engine = create_engine(url)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.stamp(config, "20261014_110")
    command.upgrade(config, "head")

    inspector = inspect(engine)
    assert TABLES <= set(inspector.get_table_names())
    room_uniques = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("mahjong_rooms")}
    request_uniques = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("mahjong_requests")}
    message_uniques = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("mahjong_messages")}
    assert ("creator_id", "create_request_id") in room_uniques
    assert ("inbound_id",) in room_uniques
    assert ("room_id", "user_id", "request_id") in request_uniques
    assert ("room_id", "user_id", "request_id") in message_uniques

    command.downgrade(config, "20261014_110")
    assert not (TABLES & set(inspect(engine).get_table_names()))
