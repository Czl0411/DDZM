"""Add weekly attendance rewards."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260806_11"
down_revision: str | None = "20260806_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.add_column(
        "game_settings",
        sa.Column(
            "weekly_attendance_reward",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
    )
    op.alter_column("game_settings", "weekly_attendance_reward", server_default=None)
    templates = sa.table(
        "command_reply_templates",
        sa.column("command", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("template", sa.Text()),
    )
    old_template = "{昵称}，当前余额：{余额} {货币}。\n今日活跃度：{活跃等级}。\n今日收益：{今日收益} {货币}。"
    new_template = old_template + "\n连续打卡：{连续打卡天数} 天。"
    op.execute(
        templates.update()
        .where(
            templates.c.command == "/我",
            templates.c.scenario == "shown",
            templates.c.template == old_template,
        )
        .values(template=new_template)
    )
    op.create_table(
        "weekly_attendance_settlements",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("reward", sa.Integer(), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "week_start"),
    )


def downgrade() -> None:
    op.drop_table("weekly_attendance_settlements")
    op.drop_column("game_settings", "weekly_attendance_reward")
