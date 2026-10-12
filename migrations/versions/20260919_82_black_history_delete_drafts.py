"""Add black history delete pagination drafts."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260919_82"
down_revision: str | None = "20260918_81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "black_history_delete_drafts",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("black_history_delete_drafts")
