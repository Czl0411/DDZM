from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[2]


def test_dice_truth_controls_migration_preserves_existing_settings(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'controls.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE liar_dice_settings (id INTEGER PRIMARY KEY, turn_seconds INTEGER NOT NULL)"))
        connection.execute(sa.text("CREATE TABLE truth_trade_settings (id INTEGER PRIMARY KEY, min_players INTEGER NOT NULL, question_timeout_seconds INTEGER NOT NULL, answer_timeout_seconds INTEGER NOT NULL)"))
        connection.execute(sa.text("INSERT INTO liar_dice_settings VALUES (1, 180)"))
        connection.execute(sa.text("INSERT INTO truth_trade_settings VALUES (1, 4, 90, 240)"))
    config = Config(str(ROOT / "alembic.ini"))
    command.stamp(config, "20261005_99")
    command.upgrade(config, "20261006_100")
    with engine.connect() as connection:
        dice = connection.execute(sa.text("SELECT * FROM liar_dice_settings")).mappings().one()
        truth = connection.execute(sa.text("SELECT * FROM truth_trade_settings")).mappings().one()
        assert dict(dice) == {"id": 1, "turn_seconds": 180, "enabled": 1, "min_players": 2}
        assert dict(truth) == {"id": 1, "min_players": 4, "question_timeout_seconds": 90, "answer_timeout_seconds": 240, "enabled": 1}
    command.downgrade(config, "20261005_99")
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT turn_seconds FROM liar_dice_settings")).scalar_one() == 180
        assert connection.execute(sa.text("SELECT min_players FROM truth_trade_settings")).scalar_one() == 4
    assert "enabled" not in {column["name"] for column in sa.inspect(engine).get_columns("truth_trade_settings")}
    command.upgrade(config, "20261006_100")
    engine.dispose()


def test_dice_truth_controls_migration_generates_postgresql_sql(monkeypatch):
    monkeypatch.setenv("DZMM_DATABASE_URL", "postgresql+psycopg://localhost/dice_truth_test")
    output = StringIO()
    config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "20261005_99:20261006_100", sql=True)
    sql = output.getvalue()
    assert "ALTER TABLE liar_dice_settings ADD COLUMN enabled BOOLEAN DEFAULT true NOT NULL" in sql
    assert "ALTER TABLE liar_dice_settings ADD COLUMN min_players INTEGER DEFAULT '2' NOT NULL" in sql
    assert "ALTER TABLE truth_trade_settings ADD COLUMN enabled BOOLEAN DEFAULT true NOT NULL" in sql
