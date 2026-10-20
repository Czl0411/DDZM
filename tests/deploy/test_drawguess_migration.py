from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


TABLES = {"drawguess_rooms", "drawguess_events", "drawguess_requests", "drawguess_messages"}


def test_upgrade_downgrade_and_constraints(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'drawguess-migration.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", url)
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE keep_existing (value INTEGER)"))
        connection.execute(text("INSERT INTO keep_existing VALUES (42)"))
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.stamp(config, "20261013_109")
    command.upgrade(config, "head")

    inspector = inspect(engine)
    assert TABLES <= set(inspector.get_table_names())
    room_uniques = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("drawguess_rooms")}
    event_uniques = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("drawguess_events")}
    request_uniques = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("drawguess_requests")}
    assert ("inbound_id",) in room_uniques
    assert ("active_code",) in room_uniques
    assert ("room_id", "seq") in event_uniques
    assert ("room_id", "user_id", "request_id") in request_uniques
    assert {foreign["referred_table"] for foreign in inspector.get_foreign_keys("drawguess_events")} == {"drawguess_rooms"}

    command.downgrade(config, "20261013_109")
    assert not (TABLES & set(inspect(engine).get_table_names()))
    with engine.connect() as connection:
        assert connection.execute(text("SELECT value FROM keep_existing")).scalar_one() == 42
