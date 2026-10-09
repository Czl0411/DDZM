"""Add the liar dice tables and enable the game for every group."""

import json
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261002_77"
down_revision: str | None = "20260917_76"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _load_types(raw) -> list:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, str):
        raw = json.loads(raw)
    return list(raw)


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "liar_dice_games",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_chat_id", sa.Uuid(), nullable=False),
        sa.Column("host_user_id", sa.Uuid(), nullable=False),
        sa.Column("active_key", sa.String(length=32)),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("current_call", sa.JSON()),
        sa.Column("last_caller_user_id", sa.Uuid()),
        sa.Column("current_seat", sa.Integer(), nullable=False),
        sa.Column("turn_deadline", sa.DateTime(timezone=True)),
        sa.Column(
            "timeout_streak", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("signup_deadline", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("finish_reason", sa.String(length=64)),
        sa.ForeignKeyConstraint(["group_chat_id"], ["group_chats.id"]),
        sa.ForeignKeyConstraint(["host_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["last_caller_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "state IN ('signup', 'dealing', 'calling', 'round_end', "
            "'completed', 'cancelled', 'forced_ended')",
            name="ck_liar_dice_game_state",
        ),
    )
    op.create_index(
        "ux_liar_dice_one_active",
        "liar_dice_games",
        ["group_chat_id"],
        unique=True,
        postgresql_where=sa.text("active_key IS NOT NULL"),
        sqlite_where=sa.text("active_key IS NOT NULL"),
    )
    op.create_table(
        "liar_dice_players",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("seat_number", sa.Integer()),
        sa.Column("dice", sa.JSON()),
        sa.Column("hand_delivery_state", sa.String(length=16)),
        sa.Column("hand_outbound_id", sa.Uuid()),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["game_id"], ["liar_dice_games.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["hand_outbound_id"], ["outbound_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "user_id"),
        sa.UniqueConstraint("game_id", "seat_number"),
        sa.CheckConstraint(
            "state IN ('signup', 'active', 'left')",
            name="ck_liar_dice_player_state",
        ),
    )
    op.create_table(
        "liar_dice_rounds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("wild_face", sa.Integer(), nullable=False),
        sa.Column(
            "wild_invalidated", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("calls", sa.JSON(), nullable=False),
        sa.Column("opener_user_id", sa.Uuid()),
        sa.Column("last_caller_user_id", sa.Uuid()),
        sa.Column("call_count", sa.Integer()),
        sa.Column("call_face", sa.Integer()),
        sa.Column("actual_count", sa.Integer()),
        sa.Column("winner_user_id", sa.Uuid()),
        sa.Column("loser_user_id", sa.Uuid()),
        sa.Column("dice_snapshot", sa.JSON()),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["game_id"], ["liar_dice_games.id"]),
        sa.ForeignKeyConstraint(["opener_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["last_caller_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["winner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["loser_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "sequence"),
        sa.CheckConstraint(
            "state IN ('active', 'resolved', 'voided')",
            name="ck_liar_dice_round_state",
        ),
    )
    rows = bind.execute(
        sa.text("SELECT id, enabled_game_types FROM group_chats")
    ).fetchall()
    for group_id, raw_types in rows:
        types = _load_types(raw_types)
        if "liar_dice" in types:
            continue
        types.append("liar_dice")
        bind.execute(
            sa.text("UPDATE group_chats SET enabled_game_types = :types WHERE id = :id"),
            {"types": json.dumps(types), "id": str(group_id)},
        )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, enabled_game_types FROM group_chats")
    ).fetchall()
    for group_id, raw_types in rows:
        types = _load_types(raw_types)
        if "liar_dice" not in types:
            continue
        types = [value for value in types if value != "liar_dice"]
        bind.execute(
            sa.text("UPDATE group_chats SET enabled_game_types = :types WHERE id = :id"),
            {"types": json.dumps(types), "id": str(group_id)},
        )
    inspector = sa.inspect(bind)
    for table in ("liar_dice_rounds", "liar_dice_players", "liar_dice_games"):
        if inspector.has_table(table):
            op.drop_table(table)
