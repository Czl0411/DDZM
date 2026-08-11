"""Persist Who Is the Undercover state-machine fixes."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260811_38"
down_revision: str | None = "20260811_37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "undercover_games",
        sa.Column("vote_seconds_snapshot", sa.Integer(), nullable=True),
    )
    op.add_column(
        "undercover_games",
        sa.Column(
            "whiteboard_win_remaining_snapshot", sa.Integer(), nullable=True
        ),
    )
    connection = op.get_bind()
    settings = sa.table(
        "undercover_settings",
        sa.column("id", sa.Integer()),
        sa.column("vote_seconds", sa.Integer()),
        sa.column("whiteboard_win_remaining", sa.Integer()),
    )
    games = sa.table(
        "undercover_games",
        sa.column("vote_seconds_snapshot", sa.Integer()),
        sa.column("whiteboard_win_remaining_snapshot", sa.Integer()),
    )
    current = connection.execute(
        sa.select(
            settings.c.vote_seconds,
            settings.c.whiteboard_win_remaining,
        ).where(settings.c.id == 1)
    ).one()
    connection.execute(
        games.update().values(
            vote_seconds_snapshot=current.vote_seconds,
            whiteboard_win_remaining_snapshot=current.whiteboard_win_remaining,
        )
    )
    with op.batch_alter_table("undercover_games") as batch_op:
        batch_op.alter_column(
            "vote_seconds_snapshot", existing_type=sa.Integer(), nullable=False
        )
        batch_op.alter_column(
            "whiteboard_win_remaining_snapshot",
            existing_type=sa.Integer(),
            nullable=False,
        )
    op.add_column(
        "undercover_session_members",
        sa.Column(
            "leave_after_round",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "undercover_abstentions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("player_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=24), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["undercover_games.id"]),
        sa.ForeignKeyConstraint(["player_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "game_id",
            "round_number",
            "player_user_id",
            name="uq_undercover_abstention_player_round",
        ),
    )


def downgrade() -> None:
    op.drop_table("undercover_abstentions")
    with op.batch_alter_table("undercover_session_members") as batch_op:
        batch_op.drop_column("leave_after_round")
    with op.batch_alter_table("undercover_games") as batch_op:
        batch_op.drop_column("whiteboard_win_remaining_snapshot")
        batch_op.drop_column("vote_seconds_snapshot")
