"""Add an optimistic revision for shared game configuration."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260805_07"
down_revision: str | None = "20260805_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_config_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        sa.table(
            "admin_config_revisions",
            sa.column("id", sa.Integer()),
            sa.column("version", sa.Integer()),
        ),
        [{"id": 1, "version": 0}],
    )


def downgrade() -> None:
    op.drop_table("admin_config_revisions")
