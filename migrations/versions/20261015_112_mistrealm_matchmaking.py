"""Leased quick-match queue for independent Mistrealm players."""
from alembic import op
import sqlalchemy as sa

revision = "20261015_112"
down_revision = "20261015_111"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mistrealm_players", sa.Column("queue_ticket", sa.Uuid(), nullable=True))
    op.add_column("mistrealm_players", sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("mistrealm_players", sa.Column("queue_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_mistrealm_players_queue_expires_at", "mistrealm_players", ["queue_expires_at"])


def downgrade():
    op.drop_index("ix_mistrealm_players_queue_expires_at", table_name="mistrealm_players")
    op.drop_column("mistrealm_players", "queue_expires_at")
    op.drop_column("mistrealm_players", "queued_at")
    op.drop_column("mistrealm_players", "queue_ticket")
