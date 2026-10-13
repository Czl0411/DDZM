from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


ROOT = Path(__file__).resolve().parents[2]


def test_chess_migration_creates_tables(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'chess.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", url)
    config = Config(str(ROOT / "alembic.ini"))
    command.stamp(config, "20261009_101")
    command.upgrade(config, "head")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"chess_games", "chess_moves", "chess_messages"} <= tables
