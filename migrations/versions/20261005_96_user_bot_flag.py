"""user bot flag - mark which employees are bot accounts

Revision ID: 20261005_96
Revises: 20261005_95
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_96"
down_revision: str | None = "20261005_95"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_bot",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_bot")
