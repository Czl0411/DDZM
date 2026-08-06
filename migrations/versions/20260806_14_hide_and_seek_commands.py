"""Update solo hide and seek player commands."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260806_14"
down_revision: str | None = "20260806_13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


old_usage_template = "请用 /摸鱼躲猫猫 发起游戏，或 /摸鱼躲猫猫 躲 编号 选择地点。"
new_usage_template = "请用 /开始摸鱼躲藏 发起游戏，再用 /躲 编号 选择地点。"
old_active_template = "你有一局躲猫猫正在选择地点，请先用 /摸鱼躲猫猫 躲 编号 完成选择。"
new_active_template = "你有一局躲猫猫正在选择地点，请先用 /躲 编号 完成选择。"
old_started_template = "{昵称}，躲猫猫开始，已扣除 {入场费} {货币}。\n请选择一个地点：\n{场景列表}\n请在 {选择超时分钟} 分钟内发送 /摸鱼躲猫猫 躲 编号。"
new_started_template = "{昵称}，躲猫猫开始，已扣除 {入场费} {货币}。\n请选择一个地点：\n{场景列表}\n请在 {选择超时分钟} 分钟内发送 /躲 编号。"
old_found_template = "【系统巡查】巡查 {巡查地点}\n你被系统找到了，本局结束。"
new_found_template = "【系统巡查】巡查 {巡查地点}\n你被系统找到了，本局扣除 {惩罚金额} {货币}。当前余额：{余额} {货币}。"


def upgrade() -> None:
    templates = sa.table(
        "command_reply_templates",
        sa.column("command", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("template", sa.Text()),
    )
    for scenario, old_template, new_template in (
        ("usage", old_usage_template, new_usage_template),
        ("already_active", old_active_template, new_active_template),
        ("started", old_started_template, new_started_template),
        ("found", old_found_template, new_found_template),
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
    definitions = sa.table(
        "command_definitions",
        sa.column("command", sa.String()),
        sa.column("description", sa.Text()),
    )
    op.execute(
        definitions.update()
        .where(
            definitions.c.command == "/摸鱼躲猫猫",
            definitions.c.description == "发起单人躲猫猫小游戏",
        )
        .values(description="发起单人躲猫猫小游戏；选择时发送 /躲 序号")
    )


def downgrade() -> None:
    templates = sa.table(
        "command_reply_templates",
        sa.column("command", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("template", sa.Text()),
    )
    for scenario, old_template, new_template in (
        ("usage", old_usage_template, new_usage_template),
        ("already_active", old_active_template, new_active_template),
        ("started", old_started_template, new_started_template),
        ("found", old_found_template, new_found_template),
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
    definitions = sa.table(
        "command_definitions",
        sa.column("command", sa.String()),
        sa.column("description", sa.Text()),
    )
    op.execute(
        definitions.update()
        .where(
            definitions.c.command == "/摸鱼躲猫猫",
            definitions.c.description == "发起单人躲猫猫小游戏；选择时发送 /躲 序号",
        )
        .values(description="发起单人躲猫猫小游戏")
    )
