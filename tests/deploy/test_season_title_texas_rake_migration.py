from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Uuid,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.exc import IntegrityError


ROOT = Path(__file__).resolve().parents[2]
REVISION = "20261113_113_season_rake"
PREVIOUS_REVISION = "20261111_112_company_seasons"


def _create_previous_revision_tables(database_url: str) -> None:
    engine = create_engine(database_url)
    metadata = MetaData()
    Table(
        "texas_holdem_settings",
        metadata,
        Column("id", Integer, primary_key=True),
    )
    Table(
        "texas_holdem_games",
        metadata,
        Column("id", Uuid, primary_key=True),
    )
    Table(
        "club_card_hands",
        metadata,
        Column("id", Uuid, primary_key=True),
    )
    Table(
        "game_settings",
        metadata,
        Column("id", Integer, primary_key=True),
    )
    Table(
        "company_seasons",
        metadata,
        Column("code", String(16), primary_key=True),
    )
    Table("users", metadata, Column("id", Uuid, primary_key=True))
    metadata.create_all(engine)

    user_id = uuid4()
    hand_id = uuid4()
    game_id = uuid4()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO texas_holdem_settings (id) VALUES (1)"))
        connection.execute(
            text("INSERT INTO texas_holdem_games (id) VALUES (:id)"),
            {"id": game_id.hex},
        )
        connection.execute(
            text("INSERT INTO club_card_hands (id) VALUES (:id)"),
            {"id": hand_id.hex},
        )
        connection.execute(text("INSERT INTO game_settings (id) VALUES (1)"))
        connection.execute(text("INSERT INTO company_seasons (code) VALUES ('S2')"))
        connection.execute(
            text("INSERT INTO users (id) VALUES (:id)"), {"id": user_id.hex}
        )


def _assert_rejected(engine, sql: str) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(sql))


def test_season_title_texas_rake_migration_round_trips_with_constraints(
    tmp_path, monkeypatch
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'season-title-rake.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    _create_previous_revision_tables(database_url)
    config = Config(str(ROOT / "alembic.ini"))
    command.stamp(config, PREVIOUS_REVISION)

    command.upgrade(config, REVISION)

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "company_season_titles" in inspector.get_table_names()
    assert "club_game_economy_settings" in inspector.get_table_names()
    assert "rake_percent" not in {
        column["name"] for column in inspector.get_columns("texas_holdem_settings")
    }
    assert {"rake_percent", "rake_amount"} <= {
        column["name"] for column in inspector.get_columns("club_card_hands")
    }
    assert {"rake_percent_snapshot", "rake_amount"} <= {
        column["name"] for column in inspector.get_columns("texas_holdem_games")
    }
    assert {
        "season_title_minimum_rank_order",
        "season_title_daily_reward",
    } <= {column["name"] for column in inspector.get_columns("game_settings")}

    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT game, coin_stakes, rake_percent "
                "FROM club_game_economy_settings ORDER BY game"
            )
        ).all() == [
            ("blackjack", "[5, 10, 20]", 20),
            ("chess", "[5, 10, 20]", 20),
            ("doudizhu", "[5, 10, 20]", 20),
            ("drawguess", "[5, 10, 20]", 20),
            ("mahjong", "[5, 10, 20]", 20),
            ("texas", "[5, 10, 20]", 20),
            ("zhajinhua", "[5, 10, 20]", 20),
        ]
        assert tuple(
            connection.execute(
                text("SELECT rake_percent, rake_amount FROM club_card_hands")
            ).one()
        ) == (0, 0)
        assert tuple(
            connection.execute(
                text(
                    "SELECT rake_percent_snapshot, rake_amount "
                    "FROM texas_holdem_games"
                )
            ).one()
        ) == (0, 0)
        assert tuple(
            connection.execute(
                text(
                    "SELECT season_title_minimum_rank_order, "
                    "season_title_daily_reward FROM game_settings WHERE id = 1"
                )
            ).one()
        ) == (8, 5)
        user_id = connection.execute(text("SELECT id FROM users")).scalar_one()

    _assert_rejected(
        engine,
        "UPDATE club_game_economy_settings SET rake_percent = 101 "
        "WHERE game = 'texas'",
    )
    _assert_rejected(
        engine,
        "INSERT INTO club_game_economy_settings "
        "(game, coin_stakes, rake_percent) VALUES ('unknown', '[5]', 20)",
    )
    _assert_rejected(
        engine, "UPDATE club_card_hands SET rake_percent = -1"
    )
    _assert_rejected(engine, "UPDATE club_card_hands SET rake_amount = -1")
    _assert_rejected(
        engine, "UPDATE texas_holdem_games SET rake_percent_snapshot = 101"
    )
    _assert_rejected(engine, "UPDATE texas_holdem_games SET rake_amount = -1")
    _assert_rejected(
        engine,
        "UPDATE game_settings SET season_title_minimum_rank_order = 0 WHERE id = 1",
    )
    _assert_rejected(
        engine,
        "UPDATE game_settings SET season_title_minimum_rank_order = 1001 WHERE id = 1",
    )
    _assert_rejected(
        engine,
        "UPDATE game_settings SET season_title_daily_reward = -1 WHERE id = 1",
    )
    _assert_rejected(
        engine,
        "UPDATE game_settings SET season_title_daily_reward = 1000 WHERE id = 1",
    )

    now = datetime.now(UTC)
    title_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO company_season_titles "
                "(id, season_code, user_id, title_name, defined_at, updated_at) "
                "VALUES (:id, 'S2', :user_id, '摸鱼王', :now, :now)"
            ),
            {"id": title_id.hex, "user_id": user_id, "now": now.isoformat()},
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO company_season_titles "
                "(id, season_code, user_id, title_name, defined_at, updated_at) "
                "VALUES (:id, 'S2', :user_id, '第二称号', :now, :now)"
            ),
            {"id": uuid4().hex, "user_id": user_id, "now": now.isoformat()},
        )

    command.downgrade(config, PREVIOUS_REVISION)

    inspector = inspect(engine)
    assert "company_season_titles" not in inspector.get_table_names()
    assert "club_game_economy_settings" not in inspector.get_table_names()
    assert "rake_percent" not in {
        column["name"] for column in inspector.get_columns("texas_holdem_settings")
    }
    assert not {"rake_percent", "rake_amount"} & {
        column["name"] for column in inspector.get_columns("club_card_hands")
    }
    assert not {"rake_percent_snapshot", "rake_amount"} & {
        column["name"] for column in inspector.get_columns("texas_holdem_games")
    }
    assert not {
        "season_title_minimum_rank_order",
        "season_title_daily_reward",
    } & {column["name"] for column in inspector.get_columns("game_settings")}
