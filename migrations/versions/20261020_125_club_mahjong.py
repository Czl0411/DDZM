"""add club mahjong rooms

Revision ID: 20261020_125
Revises: 20261020_124
"""

from alembic import op
import sqlalchemy as sa


revision = "20261020_125"
down_revision = "20261020_124"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mahjong_rooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_chat_id", sa.Uuid(), nullable=True),
        sa.Column("inbound_id", sa.Uuid(), nullable=True),
        sa.Column("creator_id", sa.Uuid(), nullable=False),
        sa.Column("create_request_id", sa.Uuid(), nullable=False),
        sa.Column("short_id", sa.String(length=12), nullable=False),
        sa.Column("code", sa.String(length=4), nullable=False),
        sa.Column("room_type", sa.String(length=16), nullable=False),
        sa.Column("match_mode", sa.String(length=16), nullable=False),
        sa.Column("seats", sa.JSON(), nullable=False),
        sa.Column("ready", sa.JSON(), nullable=False),
        sa.Column("escrowed", sa.JSON(), nullable=False),
        sa.Column("presence", sa.JSON(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=True),
        sa.Column("phase", sa.String(length=24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("settled", sa.Boolean(), nullable=False),
        sa.Column("settlement", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["creator_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["group_chat_id"], ["group_chats.id"]),
        sa.ForeignKeyConstraint(["inbound_id"], ["inbound_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("creator_id", "create_request_id", name="uq_mahjong_room_create_request"),
        sa.UniqueConstraint("inbound_id"),
        sa.UniqueConstraint("short_id"),
    )
    op.create_index("ix_mahjong_rooms_code", "mahjong_rooms", ["code"])
    op.create_index("ix_mahjong_rooms_deadline", "mahjong_rooms", ["deadline"])
    op.create_index("ix_mahjong_rooms_phase", "mahjong_rooms", ["phase"])
    op.create_table(
        "mahjong_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["mahjong_rooms.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "user_id", "request_id"),
    )
    op.create_table(
        "mahjong_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["mahjong_rooms.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "user_id", "request_id"),
    )


def downgrade() -> None:
    op.drop_table("mahjong_messages")
    op.drop_table("mahjong_requests")
    op.drop_index("ix_mahjong_rooms_phase", table_name="mahjong_rooms")
    op.drop_index("ix_mahjong_rooms_deadline", table_name="mahjong_rooms")
    op.drop_index("ix_mahjong_rooms_code", table_name="mahjong_rooms")
    op.drop_table("mahjong_rooms")
