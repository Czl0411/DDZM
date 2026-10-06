"""Store completed game participation once per player and game.

Revision ID: 20261005_97
Revises: 20261005_96
"""

from alembic import op
import sqlalchemy as sa


revision = "20261005_97"
down_revision = "20261005_96"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("game_participations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("game_type", sa.String(32), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("group_chat_id", sa.Uuid(), sa.ForeignKey("group_chats.id"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("game_type", "game_id", "user_id"))
    op.create_index("ix_game_participations_group_completed", "game_participations", ["group_chat_id", "completed_at"])
    op.create_index("ix_game_participations_user_completed", "game_participations", ["user_id", "completed_at"])


def downgrade():
    op.drop_table("game_participations")
