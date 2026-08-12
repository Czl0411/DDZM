from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Uuid,
    create_engine,
    inspect,
    text,
)


ROOT = Path(__file__).resolve().parents[2]


def test_undercover_state_machine_migration_backfills_and_downgrades(
    tmp_path, monkeypatch
):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'undercover-state.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(database_url)
    metadata = MetaData()
    users = Table(
        "users",
        metadata,
        Column("id", Uuid, primary_key=True),
    )
    settings = Table(
        "undercover_settings",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("vote_seconds", Integer, nullable=False),
        Column("whiteboard_win_remaining", Integer, nullable=False),
    )
    sessions = Table(
        "undercover_sessions",
        metadata,
        Column("id", Uuid, primary_key=True),
    )
    games = Table(
        "undercover_games",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("session_id", Uuid, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    members = Table(
        "undercover_session_members",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("session_id", Uuid, nullable=False),
        Column("user_id", Uuid, nullable=False),
        Column("state", String(32), nullable=False),
        Column("is_original", Boolean, nullable=False),
        Column("joined_at", DateTime(timezone=True), nullable=False),
    )
    templates = Table(
        "command_reply_templates",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("command", String(32), nullable=False),
        Column("scenario", String(64), nullable=False),
        Column("template", String, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    now = datetime(2026, 8, 11, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            settings.insert(),
            {"id": 1, "vote_seconds": 90, "whiteboard_win_remaining": 4},
        )
        connection.execute(users.insert(), {"id": UUID(int=1)})
        connection.execute(sessions.insert(), {"id": UUID(int=2)})
        connection.execute(
            games.insert(),
            {"id": UUID(int=3), "session_id": UUID(int=2), "created_at": now},
        )
        connection.execute(
            members.insert(),
            {
                "id": UUID(int=4),
                "session_id": UUID(int=2),
                "user_id": UUID(int=1),
                "state": "joined",
                "is_original": True,
                "joined_at": now,
            },
        )
        connection.execute(
            templates.insert(),
            [
                {
                    "id": UUID(int=5),
                    "command": "/投票",
                    "scenario": "recorded",
                    "template": "投票已记录，等待其他存活玩家投票。",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": UUID(int=6),
                    "command": "/投票",
                    "scenario": "settled",
                    "template": "管理员自定义结算文案",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
    command.stamp(config, "20260811_37")

    command.upgrade(config, "head")

    inspector = inspect(engine)
    assert "undercover_abstentions" in inspector.get_table_names()
    game_columns = {column["name"]: column for column in inspector.get_columns("undercover_games")}
    member_columns = {
        column["name"]: column
        for column in inspector.get_columns("undercover_session_members")
    }
    assert game_columns["vote_seconds_snapshot"]["nullable"] is False
    assert game_columns["whiteboard_win_remaining_snapshot"]["nullable"] is False
    assert member_columns["leave_after_round"]["nullable"] is False
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT vote_seconds_snapshot, whiteboard_win_remaining_snapshot "
                "FROM undercover_games"
            )
        ).one() == (90, 4)
        assert connection.execute(
            text("SELECT leave_after_round FROM undercover_session_members")
        ).scalar_one() in (False, 0)
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20260811_38"
        assert connection.execute(
            text(
                "SELECT template FROM command_reply_templates "
                "WHERE command = '/投票' AND scenario = 'recorded'"
            )
        ).scalar_one() == (
            "【谁是卧底】{编号}号 {玩家名称} 已投票"
            "（{已完成人数}/{存活人数}）。"
        )
        assert connection.execute(
            text(
                "SELECT template FROM command_reply_templates "
                "WHERE command = '/投票' AND scenario = 'settled'"
            )
        ).scalar_one() == "管理员自定义结算文案"
        assert connection.execute(
            text(
                "SELECT template FROM command_reply_templates "
                "WHERE command = '/跳过' "
                "AND scenario = 'undercover_abstained'"
            )
        ).scalar_one().startswith("【谁是卧底】{编号}号")
        connection.execute(
            text(
                "UPDATE command_reply_templates "
                "SET template = '管理员自定义弃票文案' "
                "WHERE command = '/跳过' "
                "AND scenario = 'undercover_abstained'"
            )
        )
        connection.commit()

    command.downgrade(config, "20260811_37")

    inspector = inspect(engine)
    assert "undercover_abstentions" not in inspector.get_table_names()
    assert "vote_seconds_snapshot" not in {
        column["name"] for column in inspector.get_columns("undercover_games")
    }
    assert "leave_after_round" not in {
        column["name"]
        for column in inspector.get_columns("undercover_session_members")
    }
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT template FROM command_reply_templates "
                "WHERE command = '/投票' AND scenario = 'recorded'"
            )
        ).scalar_one() == "投票已记录，等待其他存活玩家投票。"
        assert connection.execute(
            text(
                "SELECT template FROM command_reply_templates "
                "WHERE command = '/投票' AND scenario = 'settled'"
            )
        ).scalar_one() == "管理员自定义结算文案"
        assert connection.execute(
            text(
                "SELECT template FROM command_reply_templates "
                "WHERE command = '/跳过' "
                "AND scenario = 'undercover_abstained'"
            )
        ).scalar_one() == "管理员自定义弃票文案"
