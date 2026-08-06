"""Split hide and seek patrol replies into separate template scenarios."""

from collections.abc import Sequence
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "20260806_18"
down_revision: str | None = "20260806_17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


old_found_template = "{巡查过程}\n你被系统找到了，本局扣除 {惩罚金额} {货币}。当前余额：{余额} {货币}。"
new_found_template = "【系统巡查·第二轮】巡查 {巡查地点}\n你被系统找到了，本局扣除 {惩罚金额} {货币}。当前余额：{余额} {货币}。"
old_won_template = "{巡查过程}\n躲藏成功，获得 {奖励} {货币}。当前余额：{余额} {货币}。"
new_won_template = "【系统巡查·第二轮】巡查 {巡查地点}\n躲藏成功，获得 {奖励} {货币}。当前余额：{余额} {货币}。"


def upgrade() -> None:
    templates = sa.table(
        "command_reply_templates",
        sa.column("id", sa.Uuid()),
        sa.column("command", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("template", sa.Text()),
    )
    for scenario, template in (
        ("first_round_missed", "【系统巡查·第一轮】巡查 {巡查地点}\n奇怪，人躲哪里去了......."),
        ("found_first_round", "【系统巡查·第一轮】巡查 {巡查地点}\n你被系统找到了，本局扣除 {惩罚金额} {货币}。当前余额：{余额} {货币}。"),
    ):
        op.execute(
            templates.insert().values(
                id=uuid4(), command="/摸鱼躲猫猫", scenario=scenario, template=template
            )
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
    op.execute(
        templates.delete().where(
            templates.c.command == "/摸鱼躲猫猫",
            templates.c.scenario.in_(("first_round_missed", "found_first_round")),
        )
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
