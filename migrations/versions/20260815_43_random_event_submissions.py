"""Add guided random event submissions and review settings."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260815_43"
down_revision: str | None = "20260815_42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("random_event_settings") as batch_op:
        batch_op.add_column(
            sa.Column("submission_enabled", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(
            sa.Column("submission_draft_timeout_minutes", sa.Integer(), nullable=False, server_default="30")
        )
        batch_op.add_column(
            sa.Column("submission_max_participants", sa.Integer(), nullable=False, server_default="99")
        )
        batch_op.add_column(
            sa.Column("submission_default_target_rounds", sa.Integer(), nullable=False, server_default="10")
        )
        batch_op.add_column(
            sa.Column("submission_default_event_reward", sa.Integer(), nullable=False, server_default="6")
        )
        batch_op.add_column(
            sa.Column("submission_approval_reward", sa.Integer(), nullable=False, server_default="10")
        )
    op.create_table(
        "random_event_submission_counters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        sa.table(
            "random_event_submission_counters",
            sa.column("id", sa.Integer()),
            sa.column("next_number", sa.Integer()),
        ),
        [{"id": 1, "next_number": 1}],
    )
    op.create_table(
        "random_event_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_step", sa.String(64), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("target_rounds", sa.Integer(), nullable=True),
        sa.Column("event_reward", sa.Integer(), nullable=True),
        sa.Column("approval_reward", sa.Integer(), nullable=True),
        sa.Column("reviewer", sa.String(255), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("scene_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reward_granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["scene_id"], ["random_event_scenes.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number"),
    )
    op.create_index(
        "ix_random_event_submissions_status_number",
        "random_event_submissions",
        ["status", "number"],
    )
    op.create_index(
        "ux_random_event_submissions_one_draft",
        "random_event_submissions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'draft'"),
        sqlite_where=sa.text("status = 'draft'"),
    )
    op.create_index(
        "ux_random_event_submissions_one_pending",
        "random_event_submissions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ux_random_event_submissions_one_pending", table_name="random_event_submissions")
    op.drop_index("ux_random_event_submissions_one_draft", table_name="random_event_submissions")
    op.drop_index("ix_random_event_submissions_status_number", table_name="random_event_submissions")
    op.drop_table("random_event_submissions")
    op.drop_table("random_event_submission_counters")
    with op.batch_alter_table("random_event_settings") as batch_op:
        batch_op.drop_column("submission_approval_reward")
        batch_op.drop_column("submission_default_event_reward")
        batch_op.drop_column("submission_default_target_rounds")
        batch_op.drop_column("submission_max_participants")
        batch_op.drop_column("submission_draft_timeout_minutes")
        batch_op.drop_column("submission_enabled")
