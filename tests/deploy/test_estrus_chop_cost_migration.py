from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("coin_probabilities", [(50, 30, 20), (10, 20, 70)])
def test_estrus_chop_cost_migration_preserves_settings_and_history(tmp_path, monkeypatch, coin_probabilities):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'estrus-chop.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    engine = sa.create_engine(database_url)
    metadata = sa.MetaData()
    settings = sa.Table(
        "estrus_settings",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("coin_p0", sa.Integer(), nullable=False),
        sa.Column("coin_p1", sa.Integer(), nullable=False),
        sa.Column("coin_p2", sa.Integer(), nullable=False),
    )
    chops = sa.Table(
        "estrus_chops",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("group_chat_id", sa.Uuid(), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("coins", sa.Integer(), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(settings.insert().values(
            id=1,
            enabled=False,
            coin_p0=coin_probabilities[0],
            coin_p1=coin_probabilities[1],
            coin_p2=coin_probabilities[2],
        ))
        connection.execute(chops.insert().values(
            id=uuid4(),
            group_chat_id=uuid4(),
            target_user_id=uuid4(),
            created_at=datetime(2026, 10, 3, 15, 0),
            coins=2,
        ))
    config = Config(str(ROOT / "alembic.ini"))
    command.stamp(config, "20261004_92")

    command.upgrade(config, "20261004_93")

    with engine.connect() as connection:
        row = connection.execute(sa.text("SELECT * FROM estrus_settings")).mappings().one()
        assert row["enabled"] == 0
        assert row["coins_linked"] == 1
        assert row["target_daily_limit"] == 0
        assert row["chopper_fixed_coins"] is None
        assert row["target_fixed_coins"] is None
        assert (row["coin_p0"], row["coin_p1"], row["coin_p2"]) == coin_probabilities
        assert (row["chopper_coin_p0"], row["chopper_coin_p1"], row["chopper_coin_p2"]) == coin_probabilities
        chop = connection.execute(sa.text("SELECT coins, coins_deducted FROM estrus_chops")).one()
        assert tuple(chop) == (2, 0)
    index = next(
        entry for entry in sa.inspect(engine).get_indexes("estrus_chops")
        if entry["name"] == "ix_estrus_chops_group_target_created"
    )
    assert index["column_names"] == ["group_chat_id", "target_user_id", "created_at"]

    command.downgrade(config, "20261004_92")

    columns = {column["name"] for column in sa.inspect(engine).get_columns("estrus_settings")}
    assert columns == {"id", "enabled", "coin_p0", "coin_p1", "coin_p2"}
    assert "coins_deducted" not in {
        column["name"] for column in sa.inspect(engine).get_columns("estrus_chops")
    }
    assert not sa.inspect(engine).get_indexes("estrus_chops")
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT coins FROM estrus_chops")) == 2
    engine.dispose()
