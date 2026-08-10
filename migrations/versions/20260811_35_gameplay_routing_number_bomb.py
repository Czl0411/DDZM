"""Add gameplay signup, reminder, and skip state."""

from collections.abc import Sequence
from uuid import UUID

from alembic import op
import sqlalchemy as sa


revision: str = "20260811_35"
down_revision: str | None = "20260810_34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NUMBER_BOMB_KNOWLEDGE_CARD_ID = UUID("01c667a1-8f6e-4bcb-bde6-e1fba5d63c9d")


def upgrade() -> None:
    op.add_column(
        "memory_assessment_settings",
        sa.Column(
            "duel_signup_timeout_minutes",
            sa.Integer(),
            nullable=False,
            server_default="2",
        ),
    )
    op.add_column(
        "memory_assessment_games",
        sa.Column("signup_deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "undercover_settings",
        sa.Column(
            "signup_timeout_minutes",
            sa.Integer(),
            nullable=False,
            server_default="2",
        ),
    )
    op.add_column(
        "number_bomb_settings",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "number_bomb_settings",
        sa.Column(
            "signup_timeout_minutes",
            sa.Integer(),
            nullable=False,
            server_default="2",
        ),
    )
    op.add_column(
        "number_bomb_settings",
        sa.Column(
            "reminder_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default="15",
        ),
    )
    op.add_column(
        "number_bomb_games",
        sa.Column("signup_deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "number_bomb_games",
        sa.Column("next_reminder_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "number_bomb_games",
        sa.Column(
            "skip_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "number_bomb_round_players",
        sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=True),
    )

    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        connection.execute(
            sa.text(
                "UPDATE number_bomb_games "
                "SET signup_deadline = datetime(created_at, '+2 minutes') "
                "WHERE active_key IS NOT NULL AND state = 'signup'"
            )
        )
        connection.execute(
            sa.text(
                "UPDATE number_bomb_games "
                "SET next_reminder_at = datetime(COALESCE(started_at, last_activity_at), '+15 seconds') "
                "WHERE active_key IS NOT NULL AND state = 'collecting'"
            )
        )
    else:
        connection.execute(
            sa.text(
                "UPDATE number_bomb_games "
                "SET signup_deadline = created_at + INTERVAL '2 minutes' "
                "WHERE active_key IS NOT NULL AND state = 'signup'"
            )
        )
        connection.execute(
            sa.text(
                "UPDATE number_bomb_games "
                "SET next_reminder_at = COALESCE(started_at, last_activity_at) + INTERVAL '15 seconds' "
                "WHERE active_key IS NOT NULL AND state = 'collecting'"
            )
        )

    knowledge_cards = sa.table(
        "ai_knowledge_cards",
        sa.column("id", sa.Uuid()),
        sa.column("content", sa.Text()),
    )
    connection.execute(
        knowledge_cards.update()
        .where(knowledge_cards.c.id == NUMBER_BOMB_KNOWLEDGE_CARD_ID)
        .values(
            content=(
                "发送 /蹦蹦数字炸弹 开启不限人数报名，参与者发送 /加入，至少3人后任一参与者发送 /开始。"
                "每轮按私聊提示发送 /报数 数字；群内会定时提醒未报数者，提醒后可用 /跳过 编号移除未报数玩家。"
                "有效轮结算后发送 /继续，开局后不会因无操作自动解散。"
            )
        )
    )


def downgrade() -> None:
    op.drop_column("number_bomb_round_players", "skipped_at")
    op.drop_column("number_bomb_games", "skip_enabled")
    op.drop_column("number_bomb_games", "next_reminder_at")
    op.drop_column("number_bomb_games", "signup_deadline")
    op.drop_column("number_bomb_settings", "reminder_interval_seconds")
    op.drop_column("number_bomb_settings", "signup_timeout_minutes")
    op.drop_column("number_bomb_settings", "enabled")
    op.drop_column("undercover_settings", "signup_timeout_minutes")
    op.drop_column("memory_assessment_games", "signup_deadline")
    op.drop_column("memory_assessment_settings", "duel_signup_timeout_minutes")
