"""estrus combo chop, g-spot bonus and per-rank chopper quotas

Revision ID: 20261005_95
Revises: 20261004_94
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_95"
down_revision: str | None = "20261004_94"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "estrus_settings",
        sa.Column(
            "combo_chop_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "estrus_settings",
        sa.Column(
            "g_spot_percent", sa.Integer(), nullable=False, server_default="10"
        ),
    )
    op.add_column(
        "estrus_settings",
        sa.Column(
            "g_spot_heat_bonus",
            sa.Integer(),
            nullable=False,
            server_default="10",
        ),
    )
    op.add_column("estrus_settings", sa.Column("chopper_rank_quotas", sa.JSON()))
    op.drop_column("estrus_settings", "chopper_daily_limit")


def downgrade() -> None:
    op.add_column(
        "estrus_settings",
        sa.Column(
            "chopper_daily_limit",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.drop_column("estrus_settings", "chopper_rank_quotas")
    op.drop_column("estrus_settings", "g_spot_heat_bonus")
    op.drop_column("estrus_settings", "g_spot_percent")
    op.drop_column("estrus_settings", "combo_chop_enabled")
