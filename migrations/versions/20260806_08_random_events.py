"""Add company random event tables."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260806_08"
down_revision: str | None = "20260805_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "random_event_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.String(length=5), nullable=False),
        sa.Column("end_time", sa.String(length=5), nullable=False),
        sa.Column("events_per_day", sa.Integer(), nullable=False),
        sa.Column("minimum_interval_minutes", sa.Integer(), nullable=False),
        sa.Column("signup_timeout_minutes", sa.Integer(), nullable=False),
        sa.Column("reminder_interval_minutes", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "random_event_scenes",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("opening_text", sa.Text(), nullable=False),
        sa.Column("reward", sa.Integer(), nullable=False),
        sa.Column("target_rounds", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "random_event_scene_seats",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("scene_id", uuid_type, nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["scene_id"], ["random_event_scenes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scene_id", "role"),
    )
    op.create_table(
        "random_event_schedules",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_date", "scheduled_at"),
    )
    op.create_table(
        "random_events",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("schedule_id", uuid_type, nullable=False),
        sa.Column("group_key", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("scene_name", sa.String(length=64), nullable=False),
        sa.Column("opening_text", sa.Text(), nullable=False),
        sa.Column("reward", sa.Integer(), nullable=False),
        sa.Column("target_rounds", sa.Integer(), nullable=False),
        sa.Column("signup_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["schedule_id"], ["random_event_schedules.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("schedule_id"),
    )
    op.create_table(
        "random_event_seats",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("event_id", uuid_type, nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["random_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "role"),
    )
    op.create_index(
        "ux_random_events_one_active_group",
        "random_events",
        ["group_key"],
        unique=True,
        postgresql_where=sa.text("state IN ('signup', 'in_progress')"),
    )
    op.create_table(
        "random_event_participants",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("event_id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("rounds", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rewarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["random_events.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("random_event_participants")
    op.drop_table("random_event_seats")
    op.drop_index("ux_random_events_one_active_group", table_name="random_events")
    op.drop_table("random_events")
    op.drop_table("random_event_schedules")
    op.drop_table("random_event_scene_seats")
    op.drop_table("random_event_scenes")
    op.drop_table("random_event_settings")
