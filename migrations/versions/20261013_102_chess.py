"""Add independent Chinese chess games."""

from alembic import op
import sqlalchemy as sa


revision = "20261013_102"
down_revision = "20261009_101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chess_games",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("group_chat_id", sa.Uuid(), sa.ForeignKey("group_chats.id"), nullable=False),
        sa.Column("inbound_message_id", sa.Uuid(), sa.ForeignKey("inbound_messages.id"), nullable=False),
        sa.Column("creator_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("opponent_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("red_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("black_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("code", sa.String(4), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claim_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position", sa.JSON()),
        sa.Column("red_remaining_ms", sa.Integer(), nullable=False),
        sa.Column("black_remaining_ms", sa.Integer(), nullable=False),
        sa.Column("turn_started_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("result", sa.String(64)),
        sa.Column("pending_offer", sa.String(16)),
        sa.Column("offer_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_chess_games_status_deadline", "chess_games", ["status", "claim_deadline"])
    op.create_table(
        "chess_moves",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("game_id", sa.Uuid(), sa.ForeignKey("chess_games.id"), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=False),
        sa.Column("from_x", sa.Integer(), nullable=False),
        sa.Column("from_y", sa.Integer(), nullable=False),
        sa.Column("to_x", sa.Integer(), nullable=False),
        sa.Column("to_y", sa.Integer(), nullable=False),
        sa.Column("position_before", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("game_id", "ply"),
    )
    op.create_table(
        "chess_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("game_id", sa.Uuid(), sa.ForeignKey("chess_games.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("chess_messages")
    op.drop_table("chess_moves")
    op.drop_index("ix_chess_games_status_deadline", table_name="chess_games")
    op.drop_table("chess_games")
