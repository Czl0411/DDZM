"""Allow ordered multiple replies for one inbound message."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260806_17"
down_revision: str | None = "20260806_16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "outbound_messages_inbound_message_id_key",
        "outbound_messages",
        type_="unique",
    )
    op.add_column(
        "outbound_messages",
        sa.Column("reply_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.drop_index("ix_outbound_messages_claim", table_name="outbound_messages")
    op.create_index(
        "ix_outbound_messages_claim",
        "outbound_messages",
        ["status", "lease_expires_at", "created_at", "reply_index"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'leased')"),
    )


def downgrade() -> None:
    op.drop_index("ix_outbound_messages_claim", table_name="outbound_messages")
    op.create_index(
        "ix_outbound_messages_claim",
        "outbound_messages",
        ["status", "lease_expires_at", "created_at"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'leased')"),
    )
    op.drop_column("outbound_messages", "reply_index")
    op.create_unique_constraint(
        "outbound_messages_inbound_message_id_key",
        "outbound_messages",
        ["inbound_message_id"],
    )
