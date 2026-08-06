"""Update the default hide and seek patrol copy for two rounds."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260806_16"
down_revision: str | None = "20260806_15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


old_found_template = "【系统巡查】巡查 {巡查地点}\n你被系统找到了，本局扣除 {惩罚金额} {货币}。当前余额：{余额} {货币}。"
new_found_template = "{巡查过程}\n你被系统找到了，本局扣除 {惩罚金额} {货币}。当前余额：{余额} {货币}。"
old_won_template = "【系统巡查】巡查 {巡查地点}\n躲藏成功，获得 {奖励} {货币}。当前余额：{余额} {货币}。"
new_won_template = "{巡查过程}\n躲藏成功，获得 {奖励} {货币}。当前余额：{余额} {货币}。"


def upgrade() -> None:
    templates = sa.table(
        "command_reply_templates",
        sa.column("command", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("template", sa.Text()),
    )
    for scenario, old_template, new_template in (
        ("found", old_found_template, new_found_template),
        ("won", old_won_template, new_won_template),
    ):
        op.execute(
            templates.update()
            .where(
                templates.c.command == "/摸鱼躲猫猫",
                templates.c.scenario == scenario,
                templates.c.template == old_template,
            )
            .values(template=new_template)
        )


def downgrade() -> None:
    templates = sa.table(
        "command_reply_templates",
        sa.column("command", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("template", sa.Text()),
    )
    for scenario, old_template, new_template in (
        ("found", old_found_template, new_found_template),
        ("won", old_won_template, new_won_template),
    ):
        op.execute(
            templates.update()
            .where(
                templates.c.command == "/摸鱼躲猫猫",
                templates.c.scenario == scenario,
                templates.c.template == new_template,
            )
            .values(template=old_template)
        )
