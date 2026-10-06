"""Weekly honors, configuration snapshots and equipment.

Revision ID: 20261005_96
Revises: 20261005_95
"""

from alembic import op
import sqlalchemy as sa


revision = "20261005_96"
down_revision = "20261005_95"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("honor_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("next_week", sa.Date(), nullable=False))
    op.create_table("honor_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column("effective_week", sa.Date(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_honor_configs_effective_week", "honor_configs", ["effective_week"])
    op.create_table("honor_periods",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("week_start", sa.Date(), nullable=False, unique=True),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("announced_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer(), nullable=False))
    op.create_table("honor_awards",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("period_id", sa.Uuid(), sa.ForeignKey("honor_periods.id"), nullable=False),
        sa.Column("title_key", sa.String(64), nullable=False),
        sa.Column("title_name", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("winner_name", sa.String(64)),
        sa.Column("score", sa.Integer()),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("public_score", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("period_id", "title_key"))
    op.create_index("ix_honor_awards_user_id", "honor_awards", ["user_id"])
    op.create_index("ix_honor_awards_expires_at", "honor_awards", ["expires_at"])
    op.create_table("honor_wear",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("award_id", sa.Uuid(), sa.ForeignKey("honor_awards.id"), nullable=False))


def downgrade():
    for table in ("honor_wear", "honor_awards", "honor_periods", "honor_configs", "honor_state"):
        op.drop_table(table)
