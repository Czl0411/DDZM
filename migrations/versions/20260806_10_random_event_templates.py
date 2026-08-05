"""Add random event template names and runtime details."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260806_10"
down_revision: str | None = "20260806_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.add_column(
        "random_event_scene_openings",
        sa.Column("name", sa.String(length=64), nullable=False, server_default="未命名事件"),
    )
    op.add_column("random_events", sa.Column("event_name", sa.String(length=64)))
    for column in (
        sa.Column("scene_name", sa.String(length=64)),
        sa.Column("event_name", sa.String(length=64)),
        sa.Column("signup_text", sa.Text()),
        sa.Column("formal_opening_text", sa.Text()),
        sa.Column("reward", sa.Integer()),
        sa.Column("target_rounds", sa.Integer()),
        sa.Column("seats", sa.JSON()),
    ):
        op.add_column("random_event_schedules", column)
    op.create_table(
        "random_event_details",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("event_id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["random_events.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "position"),
    )


def downgrade() -> None:
    op.drop_table("random_event_details")
    for name in ("target_rounds", "reward", "formal_opening_text", "signup_text", "event_name", "scene_name"):
        op.drop_column("random_event_schedules", name)
    op.drop_column("random_events", "event_name")
    op.drop_column("random_event_scene_openings", "name")
