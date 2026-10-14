"""Classic saved decks and versioned immutable matchmaking snapshots."""
from alembic import op
import sqlalchemy as sa

revision = '20261015_113'
down_revision = '20261015_112'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('mistrealm_decks',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('player_id',sa.Uuid(),sa.ForeignKey('mistrealm_players.id'),nullable=False),
        sa.Column('name',sa.String(40),nullable=False),
        sa.Column('faction',sa.String(20),nullable=False),
        sa.Column('leader',sa.String(4),nullable=False),
        sa.Column('counts',sa.JSON(),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_mistrealm_decks_player_id','mistrealm_decks',['player_id'])
    op.add_column('mistrealm_players',sa.Column('queue_rules_version',sa.Integer(),nullable=False,server_default='1'))
    op.add_column('mistrealm_players',sa.Column('queue_snapshot',sa.JSON(),nullable=True))


def downgrade():
    op.execute("UPDATE mistrealm_players SET queue_ticket=NULL, queued_at=NULL, queue_expires_at=NULL WHERE queue_rules_version=2")
    op.drop_column('mistrealm_players','queue_snapshot')
    op.drop_column('mistrealm_players','queue_rules_version')
    op.drop_index('ix_mistrealm_decks_player_id',table_name='mistrealm_decks')
    op.drop_table('mistrealm_decks')
