"""Create runtime reliability tables."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260804_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    json_type = postgresql.JSONB(astext_type=sa.Text())

    op.create_table(
        "inbound_messages",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("platform_message_id", sa.String(length=255), nullable=False),
        sa.Column("sender_platform_id", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_inbound_messages_platform_message_id",
        "inbound_messages",
        ["platform_message_id"],
        unique=True,
    )

    op.create_table(
        "outbound_messages",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("inbound_message_id", uuid_type, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lease_worker_id", sa.String(length=255), nullable=True),
        sa.Column("lease_token", uuid_type, nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("platform_sent_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["inbound_message_id"], ["inbound_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inbound_message_id"),
    )
    op.create_index(
        "ix_outbound_messages_claim",
        "outbound_messages",
        ["status", "lease_expires_at", "created_at"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'leased')"),
    )

    op.create_table(
        "worker_instances",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("worker_id", sa.String(length=255), nullable=False),
        sa.Column("login_state", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=True),
        sa.Column("browser_state", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("worker_id"),
    )

    op.create_table(
        "worker_commands",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("command", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lease_worker_id", sa.String(length=255), nullable=True),
        sa.Column("lease_token", uuid_type, nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_worker_commands_claim",
        "worker_commands",
        ["status", "lease_expires_at", "created_at"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'leased')"),
    )

    op.create_table(
        "login_sessions",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("login_sessions")
    op.drop_index("ix_worker_commands_claim", table_name="worker_commands")
    op.drop_table("worker_commands")
    op.drop_table("worker_instances")
    op.drop_index("ix_outbound_messages_claim", table_name="outbound_messages")
    op.drop_table("outbound_messages")
    op.drop_index(
        "ux_inbound_messages_platform_message_id", table_name="inbound_messages"
    )
    op.drop_table("inbound_messages")
