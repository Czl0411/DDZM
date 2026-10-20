"""Remember the player's selected V3 deck across sessions and devices."""
from alembic import op
import sqlalchemy as sa

revision = '20261016_120'
down_revision = '20261016_119'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('mistrealm_players',sa.Column('selected_v3_deck_id',sa.Uuid(),nullable=True))


def downgrade():
    op.drop_column('mistrealm_players','selected_v3_deck_id')
