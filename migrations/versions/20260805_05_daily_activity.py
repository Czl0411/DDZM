"""Add daily activity gameplay records."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260805_05"
down_revision: str | None = "20260805_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DEFAULT_RULES = (
    (1, 10, 1),
    (2, 25, 2),
    (3, 60, 3),
    (4, 90, 4),
    (5, 140, 5),
    (6, 190, 6),
    (7, 250, 7),
    (8, 330, 8),
    (9, 410, 9),
    (10, 500, 10),
)
_DEFAULT_REPORT_TIMES = ("12:00", "16:00", "20:00", "23:59")


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)

    op.create_table(
        "activity_level_rules",
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("character_threshold", sa.Integer(), nullable=False),
        sa.Column("reward", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("level"),
    )
    op.bulk_insert(
        sa.table(
            "activity_level_rules",
            sa.column("level", sa.Integer()),
            sa.column("character_threshold", sa.Integer()),
            sa.column("reward", sa.Integer()),
        ),
        [
            {
                "level": level,
                "character_threshold": character_threshold,
                "reward": reward,
            }
            for level, character_threshold, reward in _DEFAULT_RULES
        ],
    )
    op.create_table(
        "income_report_schedules",
        sa.Column("report_time", sa.String(length=5), nullable=False),
        sa.PrimaryKeyConstraint("report_time"),
    )
    op.bulk_insert(
        sa.table(
            "income_report_schedules",
            sa.column("report_time", sa.String()),
        ),
        [{"report_time": report_time} for report_time in _DEFAULT_REPORT_TIMES],
    )
    op.create_table(
        "daily_activities",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "activity_date"),
    )
    op.create_table(
        "activity_reward_settlements",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("reward", sa.Integer(), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "activity_date"),
    )
    op.create_table(
        "balance_transactions",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_balance_transactions_user_occurred",
        "balance_transactions",
        ["user_id", "occurred_at"],
        unique=False,
    )
    op.alter_column("outbound_messages", "inbound_message_id", nullable=True)
    op.create_table(
        "income_report_deliveries",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("report_time", sa.String(length=5), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("outbound_message_id", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["outbound_message_id"], ["outbound_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_date", "report_time"),
        sa.UniqueConstraint("outbound_message_id"),
    )


def downgrade() -> None:
    op.drop_table("income_report_deliveries")
    op.execute("DELETE FROM outbound_messages WHERE inbound_message_id IS NULL")
    op.alter_column("outbound_messages", "inbound_message_id", nullable=False)
    op.drop_index(
        "ix_balance_transactions_user_occurred", table_name="balance_transactions"
    )
    op.drop_table("balance_transactions")
    op.drop_table("activity_reward_settlements")
    op.drop_table("daily_activities")
    op.drop_table("income_report_schedules")
    op.drop_table("activity_level_rules")
