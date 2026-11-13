import os
from pathlib import Path
import subprocess

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import (
    CheckConstraint, Column, Integer, JSON, MetaData, String, Table,
    create_engine, text,
)
from sqlalchemy.exc import IntegrityError


ROOT = Path(__file__).resolve().parents[2]
REVISION = "20261113_114_club_niuniu"
PREVIOUS_REVISION = "20261113_113_season_rake"


def test_club_niuniu_economy_migration_generates_postgresql_sql():
    environment = {
        **os.environ,
        "DZMM_DATABASE_URL": "postgresql+psycopg://user:pass@localhost/database",
    }
    result = subprocess.run(
        [
            str(ROOT / ".venv/bin/alembic"),
            "upgrade",
            f"{PREVIOUS_REVISION}:{REVISION}",
            "--sql",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "DROP CONSTRAINT ck_club_game_economy_settings_game" in result.stdout
    assert "'blackjack', 'niuniu'" in result.stdout
    assert "VALUES ('niuniu', '[5, 10, 20]', 20)" in result.stdout


def test_club_niuniu_economy_migration_round_trips(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'club-niuniu.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    engine = create_engine(database_url)
    metadata = MetaData()
    Table(
        "club_game_economy_settings",
        metadata,
        Column("game", String(16), primary_key=True),
        Column("coin_stakes", JSON, nullable=False),
        Column("rake_percent", Integer, nullable=False),
        CheckConstraint(
            "game IN ('mahjong', 'chess', 'doudizhu', 'drawguess', "
            "'texas', 'zhajinhua', 'blackjack')",
            name="ck_club_game_economy_settings_game",
        ),
    )
    metadata.create_all(engine)
    config = Config(str(ROOT / "alembic.ini"))
    command.stamp(config, PREVIOUS_REVISION)

    command.upgrade(config, REVISION)

    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT game, coin_stakes, rake_percent "
            "FROM club_game_economy_settings WHERE game = 'niuniu'"
        )).one() == ("niuniu", "[5, 10, 20]", 20)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO club_game_economy_settings "
            "(game, coin_stakes, rake_percent) VALUES ('unknown', '[5]', 20)"
        ))

    command.downgrade(config, PREVIOUS_REVISION)

    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT COUNT(*) FROM club_game_economy_settings "
            "WHERE game = 'niuniu'"
        )).scalar_one() == 0
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO club_game_economy_settings "
            "(game, coin_stakes, rake_percent) VALUES ('niuniu', '[5]', 20)"
        ))
