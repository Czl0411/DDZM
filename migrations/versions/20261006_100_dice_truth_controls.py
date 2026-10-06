"""Add enable controls and minimum players for dice and truth games."""

import sqlalchemy as sa
from alembic import op


revision = "20261006_100"
down_revision = "20261005_99"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("liar_dice_settings", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("liar_dice_settings", sa.Column("min_players", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("truth_trade_settings", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column("truth_trade_settings", "enabled")
    op.drop_column("liar_dice_settings", "min_players")
    op.drop_column("liar_dice_settings", "enabled")
