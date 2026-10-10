import importlib.util
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/versions/20261009_101_merge_feature_test.py"


def test_merge_migration_preserves_saved_scratch_ranges_and_ad_slot_limit(monkeypatch):
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    items = sa.Table(
        "items", metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("system_key", sa.String()),
        sa.Column("scratch_reward_min", sa.Integer()),
        sa.Column("scratch_reward_max", sa.Integer()),
        sa.Column("effect_config", sa.JSON()),
        sa.Column("category", sa.String()),
        sa.Column("daily_purchase_limit", sa.Integer()),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(items.insert(), [
            {"id": uuid4(), "system_key": "scratch_a", "scratch_reward_min": 7,
             "scratch_reward_max": 9, "effect_config": {"reward_min": 1, "reward_max": 10}},
            {"id": uuid4(), "system_key": "scratch_b", "scratch_reward_min": 5,
             "scratch_reward_max": 15, "effect_config": {"reward_min": 6, "reward_max": 12}},
            {"id": uuid4(), "system_key": "event_ad_slot", "scratch_reward_min": None,
             "scratch_reward_max": None, "effect_config": None},
        ])
        spec = importlib.util.spec_from_file_location("feature_test_merge", MIGRATION)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setattr(module.op, "get_bind", lambda: connection)
        module.upgrade()
        rows = {
            row["system_key"]: row
            for row in connection.execute(sa.select(items)).mappings()
        }
    assert rows["scratch_a"]["effect_config"] == {"reward_min": 7, "reward_max": 9}
    assert (rows["scratch_b"]["scratch_reward_min"], rows["scratch_b"]["scratch_reward_max"]) == (6, 12)
    assert rows["event_ad_slot"]["category"] == "event_ad_slot"
    assert rows["event_ad_slot"]["daily_purchase_limit"] == 1


def test_department_cooldown_migration_upgrades_current_main_head(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.stamp(config, "20261009_101")
    command.upgrade(config, "head")

    assert "last_department_changed_at" in {
        column["name"] for column in sa.inspect(engine).get_columns("users")
    }


def test_department_cooldown_migration_preserves_timezone(monkeypatch, capsys):
    monkeypatch.setenv("DZMM_DATABASE_URL", "postgresql+psycopg://localhost/dzmm")
    command.upgrade(Config(str(ROOT / "alembic.ini")), "20261009_101:head", sql=True)

    assert "ADD COLUMN last_department_changed_at TIMESTAMP WITH TIME ZONE" in capsys.readouterr().out
