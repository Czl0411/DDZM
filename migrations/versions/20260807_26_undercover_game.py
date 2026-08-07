"""Persist Who Is the Undercover game sessions."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260807_26"
down_revision: str | None = "20260807_25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DEFAULT_ROLE_RULES = (
    (4, 3, 1, 0),
    (5, 3, 1, 1),
    (6, 4, 1, 1),
    (7, 4, 2, 1),
    (8, 5, 2, 1),
)


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "undercover_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("vote_seconds", sa.Integer(), nullable=False),
        sa.Column("whiteboard_win_remaining", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "undercover_role_rules",
        sa.Column("player_count", sa.Integer(), nullable=False),
        sa.Column("civilian_count", sa.Integer(), nullable=False),
        sa.Column("undercover_count", sa.Integer(), nullable=False),
        sa.Column("whiteboard_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("player_count"),
    )
    op.create_table(
        "direct_chats",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("platform_user_id", sa.String(length=255), nullable=False),
        sa.Column("chatroom_id", sa.String(length=255), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform_user_id"),
        sa.UniqueConstraint("chatroom_id"),
    )
    op.create_table(
        "undercover_sessions",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("active_key", sa.String(length=32), nullable=True),
        sa.Column("target_player_count", sa.Integer(), nullable=False),
        sa.Column("signup_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("await_continue_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_undercover_one_active_session",
        "undercover_sessions",
        ["active_key"],
        unique=True,
        postgresql_where=sa.text("active_key IS NOT NULL"),
        sqlite_where=sa.text("active_key IS NOT NULL"),
    )
    op.create_table(
        "undercover_session_members",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("session_id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("is_original", sa.Boolean(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["undercover_sessions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "user_id"),
    )
    op.create_table(
        "undercover_games",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("session_id", uuid_type, nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("current_vote_round", sa.Integer(), nullable=False),
        sa.Column("civilian_word", sa.String(length=64), nullable=False),
        sa.Column("undercover_word", sa.String(length=64), nullable=False),
        sa.Column("vote_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["undercover_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "round_number"),
    )
    op.create_table(
        "undercover_game_players",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("game_id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("seat_number", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("card_delivery_state", sa.String(length=32), nullable=False),
        sa.Column("card_outbound_message_id", uuid_type, nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["undercover_games.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["card_outbound_message_id"], ["outbound_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "user_id"),
        sa.UniqueConstraint("game_id", "seat_number"),
        sa.UniqueConstraint("card_outbound_message_id"),
    )
    op.create_table(
        "undercover_votes",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("game_id", uuid_type, nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("voter_user_id", uuid_type, nullable=False),
        sa.Column("target_user_id", uuid_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["undercover_games.id"]),
        sa.ForeignKeyConstraint(["voter_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "round_number", "voter_user_id"),
    )
    with op.batch_alter_table("outbound_messages") as batch:
        batch.add_column(sa.Column("destination_chatroom_id", sa.String(length=255)))
        batch.add_column(
            sa.Column(
                "delivery_kind",
                sa.String(length=32),
                nullable=False,
                server_default="group",
            )
        )

    settings = sa.table(
        "undercover_settings",
        sa.column("id", sa.Integer()),
        sa.column("enabled", sa.Boolean()),
        sa.column("vote_seconds", sa.Integer()),
        sa.column("whiteboard_win_remaining", sa.Integer()),
    )
    role_rules = sa.table(
        "undercover_role_rules",
        sa.column("player_count", sa.Integer()),
        sa.column("civilian_count", sa.Integer()),
        sa.column("undercover_count", sa.Integer()),
        sa.column("whiteboard_count", sa.Integer()),
    )
    op.bulk_insert(
        settings,
        [
            {
                "id": 1,
                "enabled": True,
                "vote_seconds": 120,
                "whiteboard_win_remaining": 3,
            }
        ],
    )
    op.bulk_insert(
        role_rules,
        [
            {
                "player_count": player_count,
                "civilian_count": civilian_count,
                "undercover_count": undercover_count,
                "whiteboard_count": whiteboard_count,
            }
            for player_count, civilian_count, undercover_count, whiteboard_count
            in _DEFAULT_ROLE_RULES
        ],
    )


def downgrade() -> None:
    with op.batch_alter_table("outbound_messages") as batch:
        batch.drop_column("delivery_kind")
        batch.drop_column("destination_chatroom_id")
    op.drop_table("undercover_votes")
    op.drop_table("undercover_game_players")
    op.drop_table("undercover_games")
    op.drop_table("undercover_session_members")
    op.drop_index("ux_undercover_one_active_session", table_name="undercover_sessions")
    op.drop_table("undercover_sessions")
    op.drop_table("direct_chats")
    op.drop_table("undercover_role_rules")
    op.drop_table("undercover_settings")
