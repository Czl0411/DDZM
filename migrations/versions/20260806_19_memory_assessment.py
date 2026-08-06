"""Add memory assessment game tables."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260806_19"
down_revision: str | None = "20260806_18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DEFAULT_CHARACTER_SET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%&*_ -".replace(" ", "")
_DEFAULT_LEVELS = ((1, 5, 1), (2, 7, 2), (3, 9, 3), (4, 11, 4), (5, 13, 5))


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "memory_assessment_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("single_daily_limit", sa.Integer(), nullable=False),
        sa.Column("single_recall_seconds", sa.Integer(), nullable=False),
        sa.Column("duel_recall_seconds", sa.Integer(), nullable=False),
        sa.Column("duel_difficulty_level", sa.Integer(), nullable=False),
        sa.Column("duel_base_pool", sa.Integer(), nullable=False),
        sa.Column("duel_wrong_freeze", sa.Integer(), nullable=False),
        sa.Column("duel_wrong_limit", sa.Integer(), nullable=False),
        sa.Column("duel_answer_timeout_minutes", sa.Integer(), nullable=False),
        sa.Column("character_set", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "memory_assessment_level_rules",
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("answer_length", sa.Integer(), nullable=False),
        sa.Column("reward", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("level"),
    )
    op.create_table(
        "memory_assessment_daily_plays",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("play_date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "play_date"),
    )
    op.create_table(
        "memory_assessment_games",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("active_key", sa.String(length=32), nullable=True),
        sa.Column("play_date", sa.Date(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=True),
        sa.Column("reward", sa.Integer(), nullable=False),
        sa.Column("base_pool", sa.Integer(), nullable=False),
        sa.Column("answer_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("winner_user_id", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["winner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_memory_assessment_one_active_game",
        "memory_assessment_games",
        ["active_key"],
        unique=True,
        postgresql_where=sa.text("active_key IS NOT NULL"),
        sqlite_where=sa.text("active_key IS NOT NULL"),
    )
    op.create_table(
        "memory_assessment_participants",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("game_id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("wrong_count", sa.Integer(), nullable=False),
        sa.Column("frozen_amount", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["memory_assessment_games.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "user_id"),
    )
    op.create_table(
        "memory_assessment_rounds",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("game_id", uuid_type, nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("display_seconds", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["memory_assessment_games.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "sequence"),
    )
    settings = sa.table(
        "memory_assessment_settings",
        sa.column("id", sa.Integer()),
        sa.column("enabled", sa.Boolean()),
        sa.column("single_daily_limit", sa.Integer()),
        sa.column("single_recall_seconds", sa.Integer()),
        sa.column("duel_recall_seconds", sa.Integer()),
        sa.column("duel_difficulty_level", sa.Integer()),
        sa.column("duel_base_pool", sa.Integer()),
        sa.column("duel_wrong_freeze", sa.Integer()),
        sa.column("duel_wrong_limit", sa.Integer()),
        sa.column("duel_answer_timeout_minutes", sa.Integer()),
        sa.column("character_set", sa.Text()),
    )
    op.bulk_insert(
        settings,
        [
            {
                "id": 1,
                "enabled": True,
                "single_daily_limit": 1,
                "single_recall_seconds": 3,
                "duel_recall_seconds": 3,
                "duel_difficulty_level": 5,
                "duel_base_pool": 5,
                "duel_wrong_freeze": 1,
                "duel_wrong_limit": 10,
                "duel_answer_timeout_minutes": 10,
                "character_set": _DEFAULT_CHARACTER_SET,
            }
        ],
    )
    rules = sa.table(
        "memory_assessment_level_rules",
        sa.column("level", sa.Integer()),
        sa.column("answer_length", sa.Integer()),
        sa.column("reward", sa.Integer()),
    )
    op.bulk_insert(
        rules,
        [
            {"level": level, "answer_length": answer_length, "reward": reward}
            for level, answer_length, reward in _DEFAULT_LEVELS
        ],
    )


def downgrade() -> None:
    op.drop_table("memory_assessment_rounds")
    op.drop_table("memory_assessment_participants")
    op.drop_index(
        "ux_memory_assessment_one_active_game", table_name="memory_assessment_games"
    )
    op.drop_table("memory_assessment_games")
    op.drop_table("memory_assessment_daily_plays")
    op.drop_table("memory_assessment_level_rules")
    op.drop_table("memory_assessment_settings")
