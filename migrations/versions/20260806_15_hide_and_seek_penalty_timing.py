"""Charge the hide and seek penalty only when the player is found."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260806_15"
down_revision: str | None = "20260806_14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


old_started_template = "{昵称}，躲猫猫开始，已扣除 {入场费} {货币}。\n请选择一个地点：\n{场景列表}\n请在 {选择超时分钟} 分钟内发送 /躲 编号。"
new_started_template = "{昵称}，躲猫猫开始，开局不扣除。若被系统找到，将扣除 {入场费} {货币}。\n请选择一个地点：\n{场景列表}\n请在 {选择超时分钟} 分钟内发送 /躲 编号。"
old_expired_template = "选择已超时，本局已取消，入场费和次数已返还。"
new_expired_template = "选择已超时，本局已取消，次数已返还。"


def upgrade() -> None:
    templates = sa.table(
        "command_reply_templates",
        sa.column("command", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("template", sa.Text()),
    )
    for scenario, old_template, new_template in (
        ("started", old_started_template, new_started_template),
        ("expired", old_expired_template, new_expired_template),
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
        ("started", old_started_template, new_started_template),
        ("expired", old_expired_template, new_expired_template),
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
