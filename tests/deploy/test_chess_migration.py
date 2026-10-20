from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[2]


def test_chess_migration_creates_tables(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'chess.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", url)
    config = Config(str(ROOT / "alembic.ini"))
    command.stamp(config, "20261009_101")
    command.upgrade(config, "20261013_102")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"chess_games", "chess_moves", "chess_messages"} <= tables


def test_chess_event_migration_preserves_old_games(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'events.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", url)
    config = Config(str(ROOT / "alembic.ini"))
    command.stamp(config, "20261013_106")
    command.upgrade(config, "20261013_107")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO chess_games (id,group_chat_id,inbound_message_id,creator_user_id,code,status,created_at,claim_deadline,red_remaining_ms,black_remaining_ms,version) VALUES ('old','group','inbound','user','1234','waiting','2026-10-13','2026-10-13',900000,900000,0)"))
    command.upgrade(config, "head")
    assert "events" in {column["name"] for column in inspect(create_engine(url)).get_columns("chess_games")}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT events FROM chess_games WHERE id='old'")).scalar_one() == "[]"


def test_chess_migration_upgrades_production_revision(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'chess-production.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", url)
    config = Config(str(ROOT / "alembic.ini"))
    command.stamp(config, "20261013_106")

    command.upgrade(config, "head")

    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"chess_games", "chess_moves", "chess_messages"} <= tables
