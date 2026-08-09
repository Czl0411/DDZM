"""Persist desired and actual Browser Worker listener state."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260809_29"
down_revision: str | None = "20260808_28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "worker_instances",
        sa.Column(
            "listening",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.add_column(
        "worker_instances",
        sa.Column(
            "listening_desired",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("worker_instances", "listening_desired")
    op.drop_column("worker_instances", "listening")
