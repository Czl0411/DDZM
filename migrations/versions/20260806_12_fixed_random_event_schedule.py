"""Configure fixed random event schedules."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260806_12"
down_revision: str | None = "20260806_11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DEFAULT_TIMES = '["00:00", "02:00", "10:00", "14:00", "16:00", "20:00"]'
_DEFAULT_NOTICE = "可选身份：{可选身份}\n请使用 /加入 身份 报名，报名将在 {报名截止分钟} 分钟后截止。"
_OLD_JOINED_TEMPLATE = "{昵称}已加入随机事件，担任{角色}。"
_NEW_JOINED_TEMPLATE = "{昵称} 已加入随机事件，担任 {角色}。\n剩余可选身份：{剩余席位}"


def upgrade() -> None:
    op.add_column("random_event_settings", sa.Column("schedule_times", sa.JSON()))
    op.add_column("random_event_settings", sa.Column("signup_notice_template", sa.Text()))
    op.add_column("random_event_schedules", sa.Column("signup_notice_template", sa.Text()))
    settings = sa.table(
        "random_event_settings",
        sa.column("schedule_times", sa.JSON()),
        sa.column("signup_notice_template", sa.Text()),
    )
    op.execute(
        settings.update().values(
            schedule_times=sa.text(f"'{_DEFAULT_TIMES}'::json"),
            signup_notice_template=_DEFAULT_NOTICE,
        )
    )
    op.alter_column("random_event_settings", "schedule_times", nullable=False)
    op.alter_column("random_event_settings", "signup_notice_template", nullable=False)
    templates = sa.table(
        "command_reply_templates",
        sa.column("command", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("template", sa.Text()),
    )
    op.execute(
        templates.update()
        .where(
            templates.c.command == "/加入",
            templates.c.scenario == "joined",
            templates.c.template == _OLD_JOINED_TEMPLATE,
        )
        .values(template=_NEW_JOINED_TEMPLATE)
    )


def downgrade() -> None:
    op.drop_column("random_event_schedules", "signup_notice_template")
    op.drop_column("random_event_settings", "signup_notice_template")
    op.drop_column("random_event_settings", "schedule_times")
