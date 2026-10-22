"""unify Club identity, social features, tasks, and game stakes

Revision ID: 20261021_126
Revises: 20261020_125
"""

from alembic import op
import sqlalchemy as sa


revision = "20261021_126"
down_revision = "20261020_125"
branch_labels = None
depends_on = None


GAME_PLAYER_FOREIGN_KEYS = (
    ("doudizhu_rooms", "creator_id"),
    ("doudizhu_requests", "user_id"),
    ("doudizhu_messages", "user_id"),
    ("drawguess_rooms", "creator_id"),
    ("drawguess_requests", "user_id"),
    ("drawguess_messages", "user_id"),
    ("mahjong_rooms", "creator_id"),
    ("mahjong_requests", "user_id"),
    ("mahjong_messages", "user_id"),
    ("chess_games", "creator_user_id"),
    ("chess_games", "opponent_user_id"),
    ("chess_games", "red_user_id"),
    ("chess_games", "black_user_id"),
    ("chess_games", "offer_user_id"),
    ("chess_messages", "user_id"),
)


def _default_fk_name(table: str, column: str) -> str:
    return f"{table}_{column}_fkey"


def upgrade() -> None:
    op.create_table(
        "club_players",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("platform_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform_id"),
        sa.UniqueConstraint("user_id"),
    )
    op.execute(sa.text(
        """
        INSERT INTO club_players
            (id, platform_id, display_name, avatar_url, user_id, created_at, updated_at)
        SELECT id, platform_id, display_name, profile_image_url, id, joined_at, joined_at
        FROM users
        """
    ))

    op.create_table(
        "club_public_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["club_players.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_club_public_messages_player_id", "club_public_messages", ["player_id"])
    op.create_index("ix_club_public_messages_created_at", "club_public_messages", ["created_at"])
    op.create_table(
        "club_friendships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requester_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("requester_id <> recipient_id", name="ck_club_friend_distinct"),
        sa.ForeignKeyConstraint(["requester_id"], ["club_players.id"]),
        sa.ForeignKeyConstraint(["recipient_id"], ["club_players.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("requester_id", "recipient_id"),
    )
    op.create_index("ix_club_friendships_requester_id", "club_friendships", ["requester_id"])
    op.create_index("ix_club_friendships_recipient_id", "club_friendships", ["recipient_id"])
    op.create_table(
        "club_direct_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sender_id"], ["club_players.id"]),
        sa.ForeignKeyConstraint(["recipient_id"], ["club_players.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_club_direct_messages_sender_id", "club_direct_messages", ["sender_id"])
    op.create_index("ix_club_direct_messages_recipient_id", "club_direct_messages", ["recipient_id"])
    op.create_index("ix_club_direct_messages_created_at", "club_direct_messages", ["created_at"])
    op.create_table(
        "club_task_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_key", sa.String(length=32), nullable=False),
        sa.Column("reward", sa.Integer(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "task_key"),
    )
    op.create_index("ix_club_task_claims_user_id", "club_task_claims", ["user_id"])

    for table, column in GAME_PLAYER_FOREIGN_KEYS:
        op.drop_constraint(_default_fk_name(table, column), table, type_="foreignkey")
        op.create_foreign_key(
            _default_fk_name(table, column), table, "club_players", [column], ["id"]
        )

    op.alter_column("doudizhu_rooms", "group_chat_id", nullable=True)
    op.alter_column("doudizhu_rooms", "inbound_id", nullable=True)
    op.add_column("doudizhu_rooms", sa.Column("room_type", sa.String(length=16), server_default="casual", nullable=False))
    op.add_column("doudizhu_rooms", sa.Column("stake", sa.Integer(), server_default="0", nullable=False))
    op.add_column("doudizhu_rooms", sa.Column("escrowed", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("doudizhu_rooms", sa.Column("settled", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("doudizhu_rooms", sa.Column("settlement", sa.JSON(), nullable=True))

    op.alter_column("drawguess_rooms", "group_chat_id", nullable=True)
    op.alter_column("drawguess_rooms", "inbound_id", nullable=True)
    op.add_column("drawguess_rooms", sa.Column("room_type", sa.String(length=16), server_default="casual", nullable=False))
    op.add_column("drawguess_rooms", sa.Column("stake", sa.Integer(), server_default="0", nullable=False))
    op.add_column("drawguess_rooms", sa.Column("escrowed", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("drawguess_rooms", sa.Column("settled", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("drawguess_rooms", sa.Column("settlement", sa.JSON(), nullable=True))

    op.add_column("mahjong_rooms", sa.Column("stake", sa.Integer(), server_default="0", nullable=False))

    op.alter_column("chess_games", "group_chat_id", nullable=True)
    op.alter_column("chess_games", "inbound_message_id", nullable=True)
    op.add_column("chess_games", sa.Column("room_type", sa.String(length=16), server_default="casual", nullable=False))
    op.add_column("chess_games", sa.Column("stake", sa.Integer(), server_default="0", nullable=False))
    op.add_column("chess_games", sa.Column("escrowed", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("chess_games", sa.Column("settled", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("chess_games", sa.Column("settlement", sa.JSON(), nullable=True))


def downgrade() -> None:
    # A downgrade cannot represent guest-owned games in the former employee-only
    # schema. Remove those rows before restoring the original user foreign keys.
    for table, column in reversed(GAME_PLAYER_FOREIGN_KEYS):
        op.execute(sa.text(
            f"DELETE FROM {table} WHERE {column} IS NOT NULL "
            f"AND {column} NOT IN (SELECT id FROM users)"
        ))
        op.drop_constraint(_default_fk_name(table, column), table, type_="foreignkey")
        op.create_foreign_key(
            _default_fk_name(table, column), table, "users", [column], ["id"]
        )

    for table in ("chess_games", "drawguess_rooms", "doudizhu_rooms"):
        for column in ("settlement", "settled", "escrowed", "stake", "room_type"):
            op.drop_column(table, column)
    op.drop_column("mahjong_rooms", "stake")
    op.alter_column("chess_games", "inbound_message_id", nullable=False)
    op.alter_column("chess_games", "group_chat_id", nullable=False)
    op.alter_column("drawguess_rooms", "inbound_id", nullable=False)
    op.alter_column("drawguess_rooms", "group_chat_id", nullable=False)
    op.alter_column("doudizhu_rooms", "inbound_id", nullable=False)
    op.alter_column("doudizhu_rooms", "group_chat_id", nullable=False)

    op.drop_table("club_task_claims")
    op.drop_table("club_direct_messages")
    op.drop_table("club_friendships")
    op.drop_table("club_public_messages")
    op.drop_table("club_players")
