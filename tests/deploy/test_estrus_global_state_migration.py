from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[2]


def test_estrus_global_state_migration_merges_legacy_group_rows(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'estrus-global-state.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    engine = sa.create_engine(database_url)
    metadata = sa.MetaData()
    states = sa.Table(
        "estrus_states",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("group_chat_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("heat", sa.Integer(), nullable=False),
        sa.Column("chopped_count", sa.Integer(), nullable=False),
        sa.Column("total_climaxes", sa.Integer(), nullable=False),
        sa.Column("today_climaxes", sa.Integer(), nullable=False),
        sa.Column("last_active_date", sa.Date()),
        sa.Column("opted_out", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("group_chat_id", "user_id"),
    )
    sa.Table("liar_dice_settings", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    sa.Table("liar_dice_games", metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    metadata.create_all(engine)
    user_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            states.insert(),
            [
                {
                    "id": uuid4(),
                    "group_chat_id": uuid4(),
                    "user_id": user_id,
                    "heat": 2,
                    "chopped_count": 3,
                    "total_climaxes": 1,
                    "today_climaxes": 1,
                    "last_active_date": date(2026, 10, 3),
                    "opted_out": False,
                    "created_at": datetime(2026, 10, 3, 10),
                    "updated_at": datetime(2026, 10, 3, 10),
                },
                {
                    "id": uuid4(),
                    "group_chat_id": uuid4(),
                    "user_id": user_id,
                    "heat": 5,
                    "chopped_count": 4,
                    "total_climaxes": 2,
                    "today_climaxes": 2,
                    "last_active_date": date(2026, 10, 3),
                    "opted_out": True,
                    "created_at": datetime(2026, 10, 3, 11),
                    "updated_at": datetime(2026, 10, 3, 11),
                },
            ],
        )

    config = Config(str(ROOT / "alembic.ini"))
    command.stamp(config, "20261012_105")
    command.upgrade(config, "20261013_106")

    with engine.connect() as connection:
        row = connection.execute(
            sa.select(states).where(states.c.user_id == user_id)
        ).mappings().one()
        assert (row["heat"], row["chopped_count"], row["total_climaxes"]) == (7, 7, 3)
        assert row["opted_out"] is True
        assert connection.scalar(
            sa.select(sa.func.count()).select_from(states).where(states.c.user_id == user_id)
        ) == 1

    names = {
        constraint["name"]
        for constraint in sa.inspect(engine).get_unique_constraints("estrus_states")
    }
    assert "ux_estrus_state_user" in names
    assert {"signup_timeout_minutes", "continue_timeout_minutes", "deal_timeout_seconds"} <= {
        column["name"] for column in sa.inspect(engine).get_columns("liar_dice_settings")
    }
    assert {"round_end_deadline", "dealing_deadline"} <= {
        column["name"] for column in sa.inspect(engine).get_columns("liar_dice_games")
    }

    with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
        connection.execute(
            states.insert().values(
                id=uuid4(),
                group_chat_id=uuid4(),
                user_id=user_id,
                heat=0,
                chopped_count=0,
                total_climaxes=0,
                today_climaxes=0,
                opted_out=False,
                created_at=datetime(2026, 10, 3, 12),
                updated_at=datetime(2026, 10, 3, 12),
            )
        )
    engine.dispose()
