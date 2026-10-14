"""Independent draw-and-guess rooms and bounded event stream."""

from alembic import op
import sqlalchemy as sa


revision = "20261014_110"
down_revision = "20261013_109"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "drawguess_rooms",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("group_chat_id", sa.Uuid(), sa.ForeignKey("group_chats.id"), nullable=False),
        sa.Column("inbound_id", sa.Uuid(), sa.ForeignKey("inbound_messages.id"), nullable=False, unique=True),
        sa.Column("creator_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("short_id", sa.String(12), nullable=False, unique=True),
        sa.Column("active_code", sa.String(4), nullable=True, unique=True),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("cursor", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_drawguess_rooms_phase", "drawguess_rooms", ["phase"])
    op.create_index("ix_drawguess_rooms_deadline", "drawguess_rooms", ["deadline"])
    op.create_table(
        "drawguess_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("room_id", sa.Uuid(), sa.ForeignKey("drawguess_rooms.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("turn_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("room_id", "seq"),
    )
    op.create_table(
        "drawguess_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("room_id", sa.Uuid(), sa.ForeignKey("drawguess_rooms.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("turn_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("room_id", "user_id", "request_id"),
    )
    op.create_table(
        "drawguess_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("room_id", sa.Uuid(), sa.ForeignKey("drawguess_rooms.id"), nullable=False),
        sa.Column("turn_id", sa.Integer()),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("room_id", "user_id", "request_id"),
    )


def downgrade():
    for table in ("drawguess_messages", "drawguess_requests", "drawguess_events", "drawguess_rooms"):
        op.drop_table(table)
