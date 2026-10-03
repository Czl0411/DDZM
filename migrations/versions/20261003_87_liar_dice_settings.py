"""liar dice settings table

Revision ID: 20261003_87
Revises: 20261003_86
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_87"
down_revision: str | None = "20261003_86"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "liar_dice_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_chat_id", sa.Uuid(), nullable=False),
        sa.Column(
            "turn_seconds", sa.Integer(), nullable=False, server_default="120"
        ),
        sa.ForeignKeyConstraint(["group_chat_id"], ["group_chats.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_chat_id"),
    )


def downgrade() -> None:
    op.drop_table("liar_dice_settings")
