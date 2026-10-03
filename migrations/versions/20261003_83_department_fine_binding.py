"""department fine enforcement binding

Revision ID: 20261003_83
Revises: 20261003_82
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_83"
down_revision: str | None = "20261003_82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("departments") as batch:
        batch.add_column(
            sa.Column(
                "fine_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("departments") as batch:
        batch.drop_column("fine_enabled")
