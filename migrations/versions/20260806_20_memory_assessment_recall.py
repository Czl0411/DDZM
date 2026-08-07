"""Persist memory assessment answer retractions."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260806_20"
down_revision: str | None = "20260806_19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    with op.batch_alter_table("memory_assessment_daily_plays") as batch:
        batch.add_column(
            sa.Column("count", sa.Integer(), nullable=False, server_default="0")
        )
    with op.batch_alter_table("outbound_messages") as batch:
        batch.add_column(sa.Column("recall_after_seconds", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("recall_due_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("recall_status", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("recall_lease_worker_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("recall_lease_token", uuid_type, nullable=True))
        batch.add_column(sa.Column("recall_lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("recall_attempt_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("recalled_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("memory_assessment_rounds") as batch:
        batch.add_column(sa.Column("outbound_message_id", uuid_type, nullable=True))
        batch.create_unique_constraint(
            "uq_memory_assessment_rounds_outbound_message_id", ["outbound_message_id"]
        )
        batch.create_foreign_key(
            "fk_memory_assessment_rounds_outbound_message_id",
            "outbound_messages",
            ["outbound_message_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("memory_assessment_daily_plays") as batch:
        batch.drop_column("count")
    with op.batch_alter_table("memory_assessment_rounds") as batch:
        batch.drop_constraint("fk_memory_assessment_rounds_outbound_message_id", type_="foreignkey")
        batch.drop_constraint("uq_memory_assessment_rounds_outbound_message_id", type_="unique")
        batch.drop_column("outbound_message_id")
    with op.batch_alter_table("outbound_messages") as batch:
        batch.drop_column("recalled_at")
        batch.drop_column("recall_attempt_count")
        batch.drop_column("recall_lease_expires_at")
        batch.drop_column("recall_lease_token")
        batch.drop_column("recall_lease_worker_id")
        batch.drop_column("recall_status")
        batch.drop_column("recall_due_at")
        batch.drop_column("recall_after_seconds")
