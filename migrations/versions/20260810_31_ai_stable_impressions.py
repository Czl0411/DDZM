"""Persist stable AI impressions and compact activity facts."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260810_31"
down_revision: str | None = "20260810_30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inbound_messages",
        sa.Column(
            "ai_memory_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "ai_memory_settings",
        sa.Column(
            "batch_message_threshold",
            sa.Integer(),
            nullable=False,
            server_default="20",
        ),
    )
    op.add_column(
        "ai_memory_settings",
        sa.Column(
            "max_entries_per_category",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )
    op.add_column(
        "ai_memory_settings",
        sa.Column(
            "candidate_expiry_days",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
    )
    op.add_column(
        "ai_player_memories",
        sa.Column(
            "pending_message_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "ai_memory_jobs",
        sa.Column(
            "target_message_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "ai_memory_jobs",
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_table(
        "ai_player_impressions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("content", sa.String(length=240), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("contradiction_batches", sa.Integer(), nullable=False),
        sa.Column("last_supported_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_player_impressions_user_category",
        "ai_player_impressions",
        ["user_id", "category"],
    )
    op.create_table(
        "ai_impression_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("content", sa.String(length=240), nullable=False),
        sa.Column("support_batches", sa.Integer(), nullable=False),
        sa.Column("conflict_entry_id", sa.Uuid()),
        sa.Column("last_supported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conflict_entry_id"], ["ai_player_impressions.id"]
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "category", "content", "conflict_entry_id"
        ),
    )
    op.create_index(
        "ix_ai_impression_candidates_user_category",
        "ai_impression_candidates",
        ["user_id", "category"],
    )
    op.create_table(
        "ai_activity_facts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("activity_type", sa.String(length=48), nullable=False),
        sa.Column("participation_count", sa.Integer(), nullable=False),
        sa.Column("win_count", sa.Integer(), nullable=False),
        sa.Column("loss_count", sa.Integer(), nullable=False),
        sa.Column("last_result", sa.String(length=32), nullable=False),
        sa.Column("last_result_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id", "activity_type"),
    )
    op.create_table(
        "ai_activity_events",
        sa.Column("event_key", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("activity_type", sa.String(length=48), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("event_key"),
    )


def downgrade() -> None:
    op.drop_table("ai_activity_events")
    op.drop_table("ai_activity_facts")
    op.drop_index(
        "ix_ai_impression_candidates_user_category",
        table_name="ai_impression_candidates",
    )
    op.drop_table("ai_impression_candidates")
    op.drop_index(
        "ix_ai_player_impressions_user_category",
        table_name="ai_player_impressions",
    )
    op.drop_table("ai_player_impressions")
    op.drop_column("ai_memory_jobs", "available_at")
    op.drop_column("ai_memory_jobs", "target_message_count")
    op.drop_column("ai_player_memories", "pending_message_count")
    op.drop_column("ai_memory_settings", "candidate_expiry_days")
    op.drop_column("ai_memory_settings", "max_entries_per_category")
    op.drop_column("ai_memory_settings", "batch_message_threshold")
    op.drop_column("inbound_messages", "ai_memory_eligible")
