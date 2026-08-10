"""Persist blame bomb game configuration and sessions."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260810_30"
down_revision: str | None = "20260809_29"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DEFAULT_DURATIONS = (
    (2, 45, 75),
    (3, 60, 90),
    (4, 75, 120),
    (5, 90, 135),
    (6, 90, 150),
    (7, 105, 165),
    (8, 120, 180),
    (9, 135, 210),
    (10, 150, 240),
)


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "blame_game_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("signup_timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("turn_timeout_seconds", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "blame_game_duration_rules",
        sa.Column("player_count", sa.Integer(), nullable=False),
        sa.Column("minimum_seconds", sa.Integer(), nullable=False),
        sa.Column("maximum_seconds", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("player_count"),
    )
    op.create_table(
        "blame_incident_cards",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "blame_games",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("active_key", sa.String(length=32), nullable=True),
        sa.Column("creator_user_id", uuid_type, nullable=False),
        sa.Column("target_player_count", sa.Integer(), nullable=False),
        sa.Column("signup_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("incident_card_id", uuid_type, nullable=True),
        sa.Column("incident_name", sa.String(length=128), nullable=True),
        sa.Column("incident_description", sa.Text(), nullable=True),
        sa.Column("keywords_snapshot", sa.JSON(), nullable=True),
        sa.Column("total_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("explosion_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("turn_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_holder_user_id", uuid_type, nullable=True),
        sa.Column("previous_holder_user_id", uuid_type, nullable=True),
        sa.Column("last_announced_temperature", sa.String(length=32), nullable=True),
        sa.Column("loser_user_id", uuid_type, nullable=True),
        sa.Column("settlement_reason", sa.String(length=32), nullable=True),
        sa.Column("settlement_complete", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["creator_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["incident_card_id"], ["blame_incident_cards.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["current_holder_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["previous_holder_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["loser_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_blame_game_one_active",
        "blame_games",
        ["active_key"],
        unique=True,
        postgresql_where=sa.text("active_key IS NOT NULL"),
        sqlite_where=sa.text("active_key IS NOT NULL"),
    )
    op.create_table(
        "blame_game_players",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("game_id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("signup_order", sa.Integer(), nullable=False),
        sa.Column("seat_number", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("guarantee_amount", sa.Integer(), nullable=False),
        sa.Column("guarantee_state", sa.String(length=16), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["blame_games.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "user_id"),
        sa.UniqueConstraint("game_id", "seat_number"),
    )
    op.create_table(
        "blame_game_transfers",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("game_id", uuid_type, nullable=False),
        sa.Column("from_user_id", uuid_type, nullable=False),
        sa.Column("to_user_id", uuid_type, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("normalized_reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["blame_games.id"]),
        sa.ForeignKeyConstraint(["from_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["to_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "normalized_reason"),
    )
    op.create_table(
        "blame_game_daily_starts",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("play_date", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "play_date"),
    )

    settings = sa.table(
        "blame_game_settings",
        sa.column("id", sa.Integer()),
        sa.column("enabled", sa.Boolean()),
        sa.column("signup_timeout_seconds", sa.Integer()),
        sa.column("turn_timeout_seconds", sa.Integer()),
    )
    durations = sa.table(
        "blame_game_duration_rules",
        sa.column("player_count", sa.Integer()),
        sa.column("minimum_seconds", sa.Integer()),
        sa.column("maximum_seconds", sa.Integer()),
    )
    op.bulk_insert(
        settings,
        [
            {
                "id": 1,
                "enabled": True,
                "signup_timeout_seconds": 120,
                "turn_timeout_seconds": 30,
            }
        ],
    )
    op.bulk_insert(
        durations,
        [
            {
                "player_count": player_count,
                "minimum_seconds": minimum_seconds,
                "maximum_seconds": maximum_seconds,
            }
            for player_count, minimum_seconds, maximum_seconds in _DEFAULT_DURATIONS
        ],
    )


def downgrade() -> None:
    op.drop_table("blame_game_daily_starts")
    op.drop_table("blame_game_transfers")
    op.drop_table("blame_game_players")
    op.drop_index("ux_blame_game_one_active", table_name="blame_games")
    op.drop_table("blame_games")
    op.drop_table("blame_incident_cards")
    op.drop_table("blame_game_duration_rules")
    op.drop_table("blame_game_settings")
