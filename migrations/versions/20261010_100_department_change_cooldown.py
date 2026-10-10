"""department change cooldown - track last department change time

Revision ID: 20261010_100
Revises: 20261005_99
Create Date: 2026-10-10
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261010_100"
down_revision: str | None = "20261005_99"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_department_changed_at", sa.DateTime()))


def downgrade() -> None:
    op.drop_column("users", "last_department_changed_at")
