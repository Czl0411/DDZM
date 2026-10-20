"""Friend-only private messages and recipient read state."""
from alembic import op
import sqlalchemy as sa

revision = '20261016_117'
down_revision = '20261016_116'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('mistrealm_direct_messages',
        sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('sender_id',sa.Uuid(),sa.ForeignKey('mistrealm_players.id'),nullable=False),
        sa.Column('receiver_id',sa.Uuid(),sa.ForeignKey('mistrealm_players.id'),nullable=False),
        sa.Column('request_id',sa.Uuid(),nullable=False),
        sa.Column('text',sa.String(200),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('read_at',sa.DateTime(timezone=True)),
        sa.UniqueConstraint('sender_id','request_id',name='uq_mistrealm_dm_request'))
    op.create_index('ix_mistrealm_dm_pair','mistrealm_direct_messages',['sender_id','receiver_id','id'])
    op.create_index('ix_mistrealm_dm_unread','mistrealm_direct_messages',['receiver_id','read_at','id'])


def downgrade():
    op.drop_table('mistrealm_direct_messages')
