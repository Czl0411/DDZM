"""estrus chop deductions, linked/fixed coin settings and daily target limit

Revision ID: 20261004_93
Revises: 20261004_92
Create Date: 2026-10-04
"""

import sqlalchemy as sa
from alembic import op


revision: str = "20261004_93"
down_revision: str | None = "20261004_92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, default in (
        ("chopper_coin_p0", "50"),
        ("chopper_coin_p1", "30"),
        ("chopper_coin_p2", "20"),
        ("target_daily_limit", "0"),
    ):
        op.add_column(
            "estrus_settings",
            sa.Column(name, sa.Integer(), nullable=False, server_default=default),
        )
    op.add_column(
        "estrus_settings",
        sa.Column("coins_linked", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    for name in ("chopper_fixed_coins", "target_fixed_coins"):
        op.add_column("estrus_settings", sa.Column(name, sa.Integer(), nullable=True))
    op.execute(
        "UPDATE estrus_settings SET chopper_coin_p0 = coin_p0, "
        "chopper_coin_p1 = coin_p1, chopper_coin_p2 = coin_p2"
    )
    op.add_column(
        "estrus_chops",
        sa.Column("coins_deducted", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_estrus_chops_group_target_created",
        "estrus_chops",
        ["group_chat_id", "target_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_estrus_chops_group_target_created", table_name="estrus_chops")
    op.drop_column("estrus_chops", "coins_deducted")
    for name in (
        "target_fixed_coins",
        "chopper_fixed_coins",
        "coins_linked",
        "target_daily_limit",
        "chopper_coin_p2",
        "chopper_coin_p1",
        "chopper_coin_p0",
    ):
        op.drop_column("estrus_settings", name)
