"""Persist chess move and negotiation events."""
from alembic import op
import sqlalchemy as sa

revision = "20261013_108"
down_revision = "20261013_107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chess_games", sa.Column("events", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("chess_games", "events")
