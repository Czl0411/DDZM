"""Persist Minimax AI assistant configuration and work queue."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260808_27"
down_revision: str | None = "20260807_26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DEFAULT_QUOTAS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10)


def upgrade() -> None:
    op.create_table(
        "ai_assistant_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("persona", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("over_limit_reply", sa.Text(), nullable=False),
        sa.Column("failure_reply", sa.Text(), nullable=False),
        sa.Column("max_response_chars", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ai_rank_quotas",
        sa.Column("rank_id", sa.Uuid(), nullable=False),
        sa.Column("daily_limit", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["rank_id"], ["ranks.id"]),
        sa.PrimaryKeyConstraint("rank_id"),
    )
    op.create_table(
        "daily_ai_usage",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id", "usage_date"),
    )
    op.create_table(
        "ai_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inbound_message_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lease_worker_id", sa.String(length=255)),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("result_text", sa.Text()),
        sa.Column("failure_summary", sa.String(length=128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["inbound_message_id"], ["inbound_messages.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inbound_message_id"),
    )

    settings = sa.table(
        "ai_assistant_settings",
        sa.column("id", sa.Integer()),
        sa.column("enabled", sa.Boolean()),
        sa.column("persona", sa.Text()),
        sa.column("system_prompt", sa.Text()),
        sa.column("over_limit_reply", sa.Text()),
        sa.column("failure_reply", sa.Text()),
        sa.column("max_response_chars", sa.Integer()),
        sa.column("timeout_seconds", sa.Integer()),
    )
    op.bulk_insert(
        settings,
        [
            {
                "id": 1,
                "enabled": False,
                "persona": "你是摸鱼公司群的美女总监事，说话简短、有公司群调侃感。",
                "system_prompt": "仅回答当前艾特内容，不执行或裁决系统玩法。",
                "over_limit_reply": "今日找总监事聊天的次数已用完，明天再来吧。",
                "failure_reply": "总监事暂时忙碌，请稍后再试。",
                "max_response_chars": 600,
                "timeout_seconds": 20,
            }
        ],
    )
    ranks = op.get_bind().execute(
        sa.text("SELECT id FROM ranks ORDER BY sort_order")
    ).mappings()
    quotas = sa.table(
        "ai_rank_quotas",
        sa.column("rank_id", sa.Uuid()),
        sa.column("daily_limit", sa.Integer()),
    )
    op.bulk_insert(
        quotas,
        [
            {"rank_id": row["id"], "daily_limit": _DEFAULT_QUOTAS[index]}
            for index, row in enumerate(ranks)
            if index < len(_DEFAULT_QUOTAS)
        ],
    )


def downgrade() -> None:
    op.drop_table("ai_requests")
    op.drop_table("daily_ai_usage")
    op.drop_table("ai_rank_quotas")
    op.drop_table("ai_assistant_settings")
