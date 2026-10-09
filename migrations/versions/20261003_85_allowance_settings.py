"""department allowance settings table

Revision ID: 20261003_85
Revises: 20261003_84
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_85"
down_revision: str | None = "20261003_84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "department_allowance_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("checkin_amount", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("event_amount", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("game_host_amount", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("game_play_amount", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("game_play_step", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("submission_amount", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("chat_drop_percent", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("chat_drop_amount", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("referral_amount", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("daily_cap", sa.Integer(), nullable=False, server_default="5"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("department_allowance_settings")
