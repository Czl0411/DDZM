"""Add solo hide and seek game tables."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260806_13"
down_revision: str | None = "20260806_12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "hide_and_seek_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("entry_fee", sa.Integer(), nullable=False),
        sa.Column("win_reward", sa.Integer(), nullable=False),
        sa.Column("daily_limit", sa.Integer(), nullable=False),
        sa.Column("selection_timeout_minutes", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "hide_and_seek_scenes",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "hide_and_seek_daily_plays",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("play_date", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "play_date"),
    )
    op.create_table(
        "hide_and_seek_games",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("play_date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("candidates", sa.JSON(), nullable=False),
        sa.Column("selected_number", sa.Integer(), nullable=True),
        sa.Column("patrol_numbers", sa.JSON(), nullable=True),
        sa.Column("entry_fee", sa.Integer(), nullable=False),
        sa.Column("win_reward", sa.Integer(), nullable=False),
        sa.Column("choice_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_hide_and_seek_one_selecting_user",
        "hide_and_seek_games",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("state = 'selecting'"),
    )


def downgrade() -> None:
    op.drop_index("ux_hide_and_seek_one_selecting_user", table_name="hide_and_seek_games")
    op.drop_table("hide_and_seek_games")
    op.drop_table("hide_and_seek_daily_plays")
    op.drop_table("hide_and_seek_scenes")
    op.drop_table("hide_and_seek_settings")
