"""Expand blame bomb settlement notices with net economy results."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


revision: str = "20260810_33"
down_revision: str | None = "20260810_32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TEMPLATE_UPDATES = (
    (
        "/甩锅游戏",
        "exploded",
        "【甩锅游戏】锅爆炸了，{失败者} 背锅。",
        "【甩锅游戏】锅爆炸了，{失败者} 背锅，扣除 {扣除金额} {货币}；"
        "{获胜者} 获胜，每人获得 {奖励} {货币}。",
    ),
    (
        "/甩锅游戏",
        "turn_timeout",
        "【甩锅游戏】操作超时，{失败者} 背锅。",
        "【甩锅游戏】操作超时，{失败者} 背锅，扣除 {扣除金额} {货币}；"
        "{获胜者} 获胜，每人获得 {奖励} {货币}。",
    ),
    (
        "/甩锅",
        "settled",
        "锅已经爆炸，{失败者} 背锅；其他玩家每人获得 1 {货币}。",
        "【甩锅游戏】本局结束，{失败者} 背锅，扣除 {扣除金额} {货币}；"
        "{获胜者} 获胜，每人获得 {奖励} {货币}。",
    ),
    (
        "/退出甩锅",
        "settled",
        "{失败者} 主动退出并背锅，本局结束。",
        "【甩锅游戏】{失败者} 主动退出并背锅，扣除 {扣除金额} {货币}；"
        "{获胜者} 获胜，每人获得 {奖励} {货币}。",
    ),
)


def apply_template_updates(
    connection: Connection,
    updates: Sequence[tuple[str, str, str, str]],
) -> None:
    templates = sa.table(
        "command_reply_templates",
        sa.column("command", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("template", sa.Text()),
    )
    for command, scenario, old_template, new_template in updates:
        connection.execute(
            templates.update()
            .where(
                templates.c.command == command,
                templates.c.scenario == scenario,
                templates.c.template == old_template,
            )
            .values(template=new_template)
        )


def upgrade() -> None:
    apply_template_updates(op.get_bind(), TEMPLATE_UPDATES)


def downgrade() -> None:
    apply_template_updates(
        op.get_bind(),
        tuple(
            (command, scenario, new_template, old_template)
            for command, scenario, old_template, new_template in TEMPLATE_UPDATES
        ),
    )
