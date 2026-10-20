"""Personal preferences and permanent whole-match history."""
from alembic import op
import sqlalchemy as sa

revision = '20261019_122'
down_revision = '20261018_121'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('mistrealm_players',sa.Column('preferences',sa.JSON(),nullable=False,server_default='{}'))
    op.create_table('mistrealm_history',
        sa.Column('match_id',sa.Uuid(),primary_key=True),
        sa.Column('player_id',sa.Uuid(),sa.ForeignKey('mistrealm_players.id'),primary_key=True),
        sa.Column('finished_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('seat',sa.Integer(),nullable=False),
        sa.Column('summary',sa.JSON(),nullable=False),sa.Column('actions',sa.JSON(),nullable=False))
    op.create_index('ix_mistrealm_history_player_time','mistrealm_history',['player_id','finished_at'])


def downgrade():
    op.drop_table('mistrealm_history')
    op.drop_column('mistrealm_players','preferences')
