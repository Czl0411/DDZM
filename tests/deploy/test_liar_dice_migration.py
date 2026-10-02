import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    JSON,
    Column,
    MetaData,
    Table,
    Uuid,
    create_engine,
    inspect,
    select,
)


ROOT = Path(__file__).resolve().parents[2]

EXPECTED_TABLES = {
    "liar_dice_games",
    "liar_dice_players",
    "liar_dice_rounds",
}

BASE_REVISION = "20260917_76"


def migrated_engine(tmp_path, monkeypatch, *, existing_group_id=None, existing_types=None):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'liar_dice.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    engine = create_engine(database_url)
    metadata = MetaData()
    Table(
        "group_chats",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("enabled_game_types", JSON),
    )
    Table("users", metadata, Column("id", Uuid, primary_key=True))
    metadata.create_all(engine)
    if existing_group_id is not None:
        groups = Table("group_chats", MetaData(), autoload_with=engine)
        with engine.begin() as connection:
            connection.execute(
                groups.insert().values(
                    id=existing_group_id,
                    enabled_game_types=existing_types,
                )
            )

    config = Config(str(ROOT / "alembic.ini"))
    command.stamp(config, BASE_REVISION)
    command.upgrade(config, "head")
    return engine, config


def test_liar_dice_migration_creates_every_table(tmp_path, monkeypatch):
    engine, _ = migrated_engine(tmp_path, monkeypatch)

    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


def test_liar_dice_migration_enables_game_for_existing_groups(
    tmp_path, monkeypatch
):
    """已有群必须被补上 liar_dice，否则升级后该群无法开局。"""
    group_id = "00000000-0000-0000-0000-0000000000aa"
    engine, _ = migrated_engine(
        tmp_path,
        monkeypatch,
        existing_group_id=group_id,
        existing_types=["king_game", "texas_holdem"],
    )

    groups = Table("group_chats", MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        row = connection.execute(select(groups)).mappings().one()

    value = row["enabled_game_types"]
    types = json.loads(value) if isinstance(value, str) else list(value)
    assert "liar_dice" in types
    assert "king_game" in types and "texas_holdem" in types


def test_liar_dice_migration_does_not_duplicate_the_type(tmp_path, monkeypatch):
    group_id = "00000000-0000-0000-0000-0000000000ab"
    engine, _ = migrated_engine(
        tmp_path,
        monkeypatch,
        existing_group_id=group_id,
        existing_types=["liar_dice"],
    )

    groups = Table("group_chats", MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        row = connection.execute(select(groups)).mappings().one()

    value = row["enabled_game_types"]
    types = json.loads(value) if isinstance(value, str) else list(value)
    assert types == ["liar_dice"]
