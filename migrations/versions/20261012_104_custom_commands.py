"""Add custom fixed-response commands and image upload tasks.

Revision ID: 20261012_104
Revises: 20261010_103
"""

import sqlalchemy as sa
from alembic import op

revision = "20261012_104"
down_revision = "20261010_103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "command_definitions",
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("command_definitions", sa.Column("reply_type", sa.String(32)))
    op.add_column("command_definitions", sa.Column("reply_value", sa.Text()))
    op.create_table(
        "custom_command_image_uploads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("temp_path", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("lease_worker_id", sa.String(255)),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("result_url", sa.Text()),
        sa.Column("failure_summary", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_custom_command_image_uploads_claim", "custom_command_image_uploads",
        ["status", "lease_expires_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_custom_command_image_uploads_claim", table_name="custom_command_image_uploads")
    op.drop_table("custom_command_image_uploads")
    op.drop_column("command_definitions", "reply_value")
    op.drop_column("command_definitions", "reply_type")
    op.drop_column("command_definitions", "is_custom")
