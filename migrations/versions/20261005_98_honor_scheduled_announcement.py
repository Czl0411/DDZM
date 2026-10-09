"""Track the second weekly honor announcement separately.

Revision ID: 20261005_98
Revises: 20261005_97
"""

from alembic import op
import sqlalchemy as sa


revision = "20261005_98"
down_revision = "20261005_97"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("honor_periods", sa.Column("scheduled_announced_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("honor_periods") as batch:
        batch.drop_column("scheduled_announced_at")
