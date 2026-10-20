"""Committed change counters for shared social event streams."""
from alembic import op
import sqlalchemy as sa

revision = '20261016_118'
down_revision = '20261016_117'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('mistrealm_social_revisions',
        sa.Column('scope', sa.String(64), primary_key=True),
        sa.Column('version', sa.BigInteger(), nullable=False))


def downgrade():
    op.drop_table('mistrealm_social_revisions')
