"""Separate v3 decks while preserving saved Classic decks and active rooms."""
from alembic import op
import sqlalchemy as sa

revision = '20261015_115'
down_revision = '20261015_114'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('mistrealm_decks',sa.Column('rules_version',sa.Integer(),nullable=False,server_default='2'))


def downgrade():
    # V3 decks cannot be interpreted under v2 copy and construction rules.
    op.execute('DELETE FROM mistrealm_decks WHERE rules_version=3')
    op.drop_column('mistrealm_decks','rules_version')
