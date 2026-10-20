"""Mistrealm presence, consent-based friends and direct challenges."""
from alembic import op
import sqlalchemy as sa

revision = '20261016_116'
down_revision = '20261015_115'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('mistrealm_players',sa.Column('online_seen_at',sa.DateTime(timezone=True)))
    op.create_index('ix_mistrealm_players_online_seen_at','mistrealm_players',['online_seen_at'])
    op.create_table('mistrealm_friends',
        sa.Column('low_id',sa.Uuid(),sa.ForeignKey('mistrealm_players.id'),primary_key=True),
        sa.Column('high_id',sa.Uuid(),sa.ForeignKey('mistrealm_players.id'),primary_key=True),
        sa.Column('requester_id',sa.Uuid(),sa.ForeignKey('mistrealm_players.id'),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('mistrealm_invites',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('sender_id',sa.Uuid(),sa.ForeignKey('mistrealm_players.id'),nullable=False),
        sa.Column('receiver_id',sa.Uuid(),sa.ForeignKey('mistrealm_players.id'),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('deck_snapshot',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('room_id',sa.Uuid(),sa.ForeignKey('mistrealm_rooms.id')))
    for field in ('sender_id','receiver_id'):
        op.create_index('ix_mistrealm_invites_'+field,'mistrealm_invites',[field])


def downgrade():
    op.drop_table('mistrealm_invites')
    op.drop_table('mistrealm_friends')
    op.drop_index('ix_mistrealm_players_online_seen_at',table_name='mistrealm_players')
    op.drop_column('mistrealm_players','online_seen_at')
