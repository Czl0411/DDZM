"""Independent doudizhu rooms, rounds and idempotent requests."""
from alembic import op
import sqlalchemy as sa

revision = '20261013_109'
down_revision = '20261013_108'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('doudizhu_rooms',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('group_chat_id', sa.Uuid(), sa.ForeignKey('group_chats.id'), nullable=False),
        sa.Column('inbound_id', sa.Uuid(), sa.ForeignKey('inbound_messages.id'), nullable=False, unique=True),
        sa.Column('creator_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('short_id', sa.String(12), nullable=False, unique=True),
        sa.Column('code', sa.String(4), nullable=False),
        sa.Column('seats', sa.JSON(), nullable=False), sa.Column('ready', sa.JSON(), nullable=False),
        sa.Column('presence', sa.JSON(), nullable=False),
        sa.Column('phase', sa.String(16), nullable=False), sa.Column('round_id', sa.Uuid()),
        sa.Column('round_number', sa.Integer(), nullable=False), sa.Column('redeals', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deadline', sa.DateTime(timezone=True)))
    op.create_index('ix_doudizhu_rooms_phase', 'doudizhu_rooms', ['phase'])
    op.create_index('ix_doudizhu_rooms_deadline', 'doudizhu_rooms', ['deadline'])
    op.create_table('doudizhu_rounds', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('room_id', sa.Uuid(), sa.ForeignKey('doudizhu_rooms.id'), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False), sa.Column('state', sa.JSON(), nullable=False),
        sa.Column('notice_sent', sa.Boolean(), nullable=False), sa.UniqueConstraint('room_id', 'number'))
    op.create_table('doudizhu_requests', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('room_id', sa.Uuid(), sa.ForeignKey('doudizhu_rooms.id'), nullable=False),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_id', sa.Uuid(), nullable=False), sa.Column('digest', sa.String(64), nullable=False),
        sa.UniqueConstraint('room_id', 'user_id', 'request_id'))
    op.create_table('doudizhu_messages', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('room_id', sa.Uuid(), sa.ForeignKey('doudizhu_rooms.id'), nullable=False),
        sa.Column('round_id', sa.Uuid()),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_id', sa.Uuid(), nullable=False), sa.Column('content', sa.String(300), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('room_id', 'user_id', 'request_id'))


def downgrade():
    for table in ('doudizhu_messages', 'doudizhu_requests', 'doudizhu_rounds', 'doudizhu_rooms'):
        op.drop_table(table)
