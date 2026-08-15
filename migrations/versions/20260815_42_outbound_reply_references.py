"""Add outbound delivery keys and reply reference snapshots."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260815_42"
down_revision: str | None = "20260813_41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("outbound_messages") as batch_op:
        batch_op.add_column(sa.Column("delivery_key", sa.String(255), nullable=True))
        batch_op.add_column(
            sa.Column("reference_message_id", sa.String(255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("reference_sender_platform_id", sa.String(255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("reference_content_type", sa.String(32), nullable=True)
        )
        batch_op.add_column(sa.Column("reference_text", sa.Text(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE outbound_messages "
            "SET delivery_key = COALESCE(destination_chatroom_id, '__group__')"
        )
    )
    with op.batch_alter_table("outbound_messages") as batch_op:
        batch_op.alter_column(
            "delivery_key",
            existing_type=sa.String(255),
            nullable=False,
            server_default="__group__",
        )
        batch_op.create_index(
            "ix_outbound_messages_delivery_order",
            ["delivery_key", "status", "created_at", "reply_index", "id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("outbound_messages") as batch_op:
        batch_op.drop_index("ix_outbound_messages_delivery_order")
        batch_op.drop_column("reference_text")
        batch_op.drop_column("reference_content_type")
        batch_op.drop_column("reference_sender_platform_id")
        batch_op.drop_column("reference_message_id")
        batch_op.drop_column("delivery_key")
