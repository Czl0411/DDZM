"""add per-group member removal operators

Revision ID: 20261010_102
Revises: 20261010_101
"""

import sqlalchemy as sa
from alembic import op

revision = "20261010_102"
down_revision = "20261010_101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "group_chats",
        sa.Column("ban_operator_platform_ids", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("group_chats", "ban_operator_platform_ids")
