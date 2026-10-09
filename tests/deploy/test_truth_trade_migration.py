from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


ROOT = Path(__file__).resolve().parents[2]

TRUTH_TABLES = (
    "truth_trade_settings",
    "truth_trade_games",
    "truth_trade_players",
    "truth_trade_questions",
    "truth_trade_answers",
)


def test_truth_trade_migration_creates_and_drops_tables(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'truth-trade.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(database_url)
    command.stamp(config, "20261003_80")

    command.upgrade(config, "20261003_81")

    tables = set(inspect(engine).get_table_names())
    assert all(table in tables for table in TRUTH_TABLES)
    game_columns = {
        column["name"] for column in inspect(engine).get_columns("truth_trade_games")
    }
    assert {"state", "round_number", "settled_rounds", "current_position"} <= game_columns

    command.downgrade(config, "20261003_80")

    tables = set(inspect(engine).get_table_names())
    assert all(table not in tables for table in TRUTH_TABLES)
