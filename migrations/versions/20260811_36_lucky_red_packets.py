"""Add persistent lucky red packets."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260811_36"
down_revision: str | None = "20260811_35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "red_packet_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("expiry_minutes", sa.Integer(), nullable=False),
        sa.Column("empty_probability_percent", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    settings = sa.table(
        "red_packet_settings",
        sa.column("id", sa.Integer()),
        sa.column("expiry_minutes", sa.Integer()),
        sa.column("empty_probability_percent", sa.Integer()),
    )
    op.bulk_insert(
        settings,
        [{"id": 1, "expiry_minutes": 10, "empty_probability_percent": 5}],
    )

    op.create_table(
        "red_packets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("active_key", sa.String(length=32), nullable=True),
        sa.Column("issuer_user_id", sa.Uuid(), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("has_empty", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "refunded_amount", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.ForeignKeyConstraint(["issuer_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_red_packet_one_active",
        "red_packets",
        ["active_key"],
        unique=True,
        sqlite_where=sa.text("active_key IS NOT NULL"),
        postgresql_where=sa.text("active_key IS NOT NULL"),
    )
    op.create_table(
        "red_packet_shares",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("packet_id", sa.Uuid(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("claimant_user_id", sa.Uuid(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["claimant_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["packet_id"], ["red_packets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("packet_id", "claimant_user_id"),
        sa.UniqueConstraint("packet_id", "display_order"),
    )
    op.create_table(
        "red_packet_daily_starts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("play_date", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "play_date"),
    )


def downgrade() -> None:
    op.drop_table("red_packet_daily_starts")
    op.drop_table("red_packet_shares")
    op.drop_index("ux_red_packet_one_active", table_name="red_packets")
    op.drop_table("red_packets")
    op.drop_table("red_packet_settings")
