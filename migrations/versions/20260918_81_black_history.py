"""Add employee black history entries."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260918_81"
down_revision: str | None = "20260917_80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "black_history_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("subject_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recorder_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("group_chat_id", sa.Uuid(), sa.ForeignKey("group_chats.id"), nullable=False),
        sa.Column("source_platform_message_id", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=16), nullable=False),
        sa.Column("text_content", sa.Text()),
        sa.Column("image_url", sa.Text()),
        sa.Column("image_alt", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("group_chat_id", "source_platform_message_id"),
    )
    op.create_index(
        "ix_black_history_entries_subject_id", "black_history_entries",
        ["subject_user_id", "id"],
    )
def downgrade() -> None:
    op.drop_index("ix_black_history_entries_subject_id", table_name="black_history_entries")
    op.drop_table("black_history_entries")
