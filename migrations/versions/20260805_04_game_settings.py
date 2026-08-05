"""Add global game economy settings."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260805_04"
down_revision: str | None = "20260805_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DEFAULT_TEMPLATE_UPDATES = (
    ("/入职", "joined", "{昵称}，欢迎入职摸鱼公司。当前余额：{余额} 摸鱼币。", "{昵称}，欢迎入职摸鱼公司。当前余额：{余额} {货币}。"),
    ("/入职", "already_joined", "{昵称}已经在职，当前余额：{余额} 摸鱼币。", "{昵称}已经在职，当前余额：{余额} {货币}。"),
    ("/打卡", "checked_in", "打卡成功，领取 {打卡奖励} 摸鱼币。当前余额：{余额} 摸鱼币。", "打卡成功，领取 {打卡奖励} {货币}。当前余额：{余额} {货币}。"),
    ("/余额", "shown", "{昵称}，当前余额：{余额} 摸鱼币。", "{昵称}，当前余额：{余额} {货币}。"),
)


def upgrade() -> None:
    op.create_table(
        "game_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("currency_name", sa.String(length=12), nullable=False),
        sa.Column("onboarding_bonus", sa.Integer(), nullable=False),
        sa.Column("checkin_reward", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        sa.table(
            "game_settings",
            sa.column("id", sa.Integer()),
            sa.column("currency_name", sa.String()),
            sa.column("onboarding_bonus", sa.Integer()),
            sa.column("checkin_reward", sa.Integer()),
        ),
        [{"id": 1, "currency_name": "摸鱼币", "onboarding_bonus": 0, "checkin_reward": 5}],
    )
    templates = sa.table(
        "command_reply_templates",
        sa.column("command", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("template", sa.Text()),
    )
    for command, scenario, old_template, new_template in _DEFAULT_TEMPLATE_UPDATES:
        op.execute(
            templates.update()
            .where(
                templates.c.command == command,
                templates.c.scenario == scenario,
                templates.c.template == old_template,
            )
            .values(template=new_template)
        )


def downgrade() -> None:
    op.drop_table("game_settings")
