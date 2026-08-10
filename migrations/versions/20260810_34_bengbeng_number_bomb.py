"""Add persistent state for the Bengbeng number bomb game."""

from collections.abc import Sequence
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa


revision: str = "20260810_34"
down_revision: str | None = "20260810_33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inbound_messages",
        sa.Column(
            "source_type",
            sa.String(length=16),
            nullable=False,
            server_default="group",
        ),
    )
    op.add_column(
        "inbound_messages",
        sa.Column("chatroom_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "ai_activity_events",
        sa.Column("detail", sa.String(length=32), nullable=True),
    )

    op.create_table(
        "number_bomb_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inactivity_timeout_minutes", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "number_bomb_games",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("active_key", sa.String(length=32), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("target_player_count", sa.Integer(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finish_reason", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_number_bomb_one_active",
        "number_bomb_games",
        ["active_key"],
        unique=True,
        sqlite_where=sa.text("active_key IS NOT NULL"),
        postgresql_where=sa.text("active_key IS NOT NULL"),
    )
    op.create_table(
        "number_bomb_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("roster_order", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["number_bomb_games.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "user_id"),
    )
    op.create_table(
        "number_bomb_rounds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("punishment_type", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("player_count", sa.Integer(), nullable=False),
        sa.Column("target_numerator", sa.Integer(), nullable=True),
        sa.Column("target_denominator", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["game_id"], ["number_bomb_games.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "round_number", "attempt_number"),
    )
    op.create_table(
        "number_bomb_round_players",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("round_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("submitted_number", sa.Integer(), nullable=True),
        sa.Column("deviation_numerator", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(["round_id"], ["number_bomb_rounds.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("round_id", "user_id"),
    )

    settings = sa.table(
        "number_bomb_settings",
        sa.column("id", sa.Integer()),
        sa.column("inactivity_timeout_minutes", sa.Integer()),
    )
    op.bulk_insert(
        settings,
        [{"id": 1, "inactivity_timeout_minutes": 10}],
    )

    knowledge_cards = sa.table(
        "ai_knowledge_cards",
        sa.column("id", sa.Uuid()),
        sa.column("topic", sa.String()),
        sa.column("title", sa.String()),
        sa.column("keywords", sa.JSON()),
        sa.column("content", sa.Text()),
        sa.column("enabled", sa.Boolean()),
        sa.column("priority", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    op.bulk_insert(
        knowledge_cards,
        [
            {
                "id": uuid4(),
                "topic": "number_bomb",
                "title": "蹦蹦数字炸弹",
                "keywords": ["蹦蹦数字炸弹", "平均数炸弹", "报数", "真心话", "大冒险"],
                "content": (
                    "3至10人报名后，每轮玩家私聊发送 /报数 1-100；全员提交后按平均数乘0.8计算。"
                    "有效轮结算后由当前参与者发送 /继续，具体状态与超时以实时数据为准。"
                ),
                "enabled": True,
                "priority": 100,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    knowledge_cards = sa.table(
        "ai_knowledge_cards",
        sa.column("topic", sa.String()),
    )
    op.execute(
        knowledge_cards.delete().where(knowledge_cards.c.topic == "number_bomb")
    )
    op.drop_table("number_bomb_round_players")
    op.drop_table("number_bomb_rounds")
    op.drop_table("number_bomb_members")
    op.drop_index("ux_number_bomb_one_active", table_name="number_bomb_games")
    op.drop_table("number_bomb_games")
    op.drop_table("number_bomb_settings")
    op.drop_column("ai_activity_events", "detail")
    op.drop_column("inbound_messages", "chatroom_id")
    op.drop_column("inbound_messages", "source_type")
