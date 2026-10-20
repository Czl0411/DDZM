"""Durable whole-match balance samples, separate from ranked points."""
from alembic import op
import sqlalchemy as sa

revision = '20261018_121'
down_revision = '20261016_120'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('mistrealm_balance_matches',
        sa.Column('match_id',sa.Uuid(),primary_key=True),
        sa.Column('room_id',sa.Uuid(),nullable=False),
        sa.Column('finished_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('rules_revision',sa.String(40),nullable=False),
        sa.Column('mode',sa.String(16),nullable=False),
        sa.Column('population',sa.String(16),nullable=False),
        sa.Column('first_seat',sa.Integer()),sa.Column('winner',sa.Integer()),
        sa.Column('end_reason',sa.String(16),nullable=False),
        sa.Column('rounds',sa.Integer(),nullable=False),sa.Column('participants',sa.JSON(),nullable=False))
    op.create_index('ix_mistrealm_balance_matches_finished_at','mistrealm_balance_matches',['finished_at'])


def downgrade():
    op.drop_table('mistrealm_balance_matches')
