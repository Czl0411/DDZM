"""Persist asynchronous AI player memory settings and jobs."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260808_28"
down_revision: str | None = "20260808_27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_memory_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("gameplay_guide", sa.Text(), nullable=False),
        sa.Column("extraction_prompt", sa.Text(), nullable=False),
        sa.Column("history_limit", sa.Integer(), nullable=False),
        sa.Column("max_memory_chars", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ai_player_memories",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("memory_text", sa.Text(), nullable=False),
        sa.Column("last_scanned_message_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["last_scanned_message_id"], ["inbound_messages.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "ai_memory_jobs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target_message_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("lease_worker_id", sa.String(length=255)),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("failure_summary", sa.String(length=128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["target_message_id"], ["inbound_messages.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.bulk_insert(
        sa.table(
            "ai_memory_settings",
            sa.column("id", sa.Integer()),
            sa.column("enabled", sa.Boolean()),
            sa.column("gameplay_guide", sa.Text()),
            sa.column("extraction_prompt", sa.Text()),
            sa.column("history_limit", sa.Integer()),
            sa.column("max_memory_chars", sa.Integer()),
        ),
        [{
            "id": 1,
            "enabled": True,
            "gameplay_guide": "你是摸鱼公司群总监事。玩法、经济和游戏裁定以机器人指令为准；需要操作时引导玩家使用 /帮助 分类。",
            "extraction_prompt": "仅整理玩家稳定的称呼偏好、回复风格、长期兴趣和互动禁忌；不要记录隐私、第三方信息、游戏过程、余额、职位或部门。没有稳定信息时返回空文本。",
            "history_limit": 500,
            "max_memory_chars": 1200,
        }],
    )


def downgrade() -> None:
    op.drop_table("ai_memory_jobs")
    op.drop_table("ai_player_memories")
    op.drop_table("ai_memory_settings")
