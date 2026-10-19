"""store confirmed group member removal requests

Revision ID: 20261010_103
Revises: 20261010_102
"""

import sqlalchemy as sa
from alembic import op

revision = "20261010_103"
down_revision = "20261010_102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_ban_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("group_chat_id", sa.Uuid(), sa.ForeignKey("group_chats.id"), nullable=False),
        sa.Column("actor_platform_id", sa.String(255), nullable=False),
        sa.Column("target_platform_id", sa.String(255), nullable=False),
        sa.Column("target_message_id", sa.String(255), nullable=False),
        sa.Column("source_inbound_message_id", sa.Uuid(), sa.ForeignKey("inbound_messages.id"), nullable=False),
        sa.Column("confirmation_inbound_message_id", sa.Uuid(), sa.ForeignKey("inbound_messages.id")),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("message_excerpt", sa.String(120), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("detail", sa.Text()),
    )
    op.create_index(
        "ix_group_ban_requests_pending", "group_ban_requests",
        ["group_chat_id", "actor_platform_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_group_ban_requests_pending", table_name="group_ban_requests")
    op.drop_table("group_ban_requests")
