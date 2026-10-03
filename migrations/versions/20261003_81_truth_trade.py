"""truth trade group game tables

Revision ID: 20261003_81
Revises: 20261003_80
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_81"
down_revision: str | None = "20261003_80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "truth_trade_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_chat_id", sa.Uuid(), nullable=False),
        sa.Column("question_timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("answer_timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("min_players", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["group_chat_id"], ["group_chats.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_chat_id"),
    )
    op.create_table(
        "truth_trade_games",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_chat_id", sa.Uuid(), nullable=False),
        sa.Column("host_user_id", sa.Uuid(), nullable=False),
        sa.Column("active_key", sa.String(length=32)),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("settled_rounds", sa.Integer(), nullable=False),
        sa.Column("current_position", sa.Integer(), nullable=False),
        sa.Column("phase_deadline", sa.DateTime(timezone=True)),
        sa.Column("signup_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("finish_reason", sa.String(length=64)),
        sa.ForeignKeyConstraint(["group_chat_id"], ["group_chats.id"]),
        sa.ForeignKeyConstraint(["host_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "state IN ('signup', 'asking', 'answering', 'round_complete', "
            "'finished', 'cancelled')",
            name="ck_truth_trade_game_state",
        ),
    )
    op.create_index(
        "ux_truth_trade_one_active",
        "truth_trade_games",
        ["group_chat_id"],
        unique=True,
        postgresql_where=sa.text("active_key IS NOT NULL"),
        sqlite_where=sa.text("active_key IS NOT NULL"),
    )
    op.create_table(
        "truth_trade_players",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["game_id"], ["truth_trade_games.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "user_id", name="uq_truth_trade_player_user"),
        sa.UniqueConstraint(
            "game_id", "position", name="uq_truth_trade_player_position"
        ),
        sa.CheckConstraint(
            "state IN ('active', 'withdrawn')",
            name="ck_truth_trade_player_state",
        ),
    )
    op.create_table(
        "truth_trade_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("asker_player_id", sa.Uuid(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text()),
        sa.Column("required_player_count", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["game_id"], ["truth_trade_games.id"]),
        sa.ForeignKeyConstraint(
            ["asker_player_id"], ["truth_trade_players.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "game_id", "round_number", "position", name="uq_truth_trade_question_slot"
        ),
        sa.CheckConstraint(
            "state IN ('open', 'collected', 'skipped')",
            name="ck_truth_trade_question_state",
        ),
    )
    op.create_table(
        "truth_trade_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text()),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["question_id"], ["truth_trade_questions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", "user_id", name="uq_truth_trade_answer"),
        sa.CheckConstraint(
            "state IN ('answered', 'declined', 'timed_out', 'left')",
            name="ck_truth_trade_answer_state",
        ),
    )


def downgrade() -> None:
    op.drop_table("truth_trade_answers")
    op.drop_table("truth_trade_questions")
    op.drop_table("truth_trade_players")
    op.drop_index("ux_truth_trade_one_active", table_name="truth_trade_games")
    op.drop_table("truth_trade_games")
    op.drop_table("truth_trade_settings")
