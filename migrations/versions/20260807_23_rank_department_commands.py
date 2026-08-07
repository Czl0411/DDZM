"""Seed rank, department, and promotion command defaults safely."""

from collections.abc import Sequence
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite


revision: str = "20260807_23"
down_revision: str | None = "20260807_22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


old_me_template = "{昵称}，当前余额：{余额} {货币}。\n今日活跃度：{活跃等级}。\n今日收益：{今日收益} {货币}。\n连续打卡：{连续打卡天数} 天。"
new_me_template = "{昵称}\n职位：{职位}（{职级}）\n部门：{部门}\n当前余额：{余额} {货币}。\n今日活跃度：{活跃等级}。\n今日收益：{今日收益} {货币}。\n连续打卡：{连续打卡天数} 天。"

command_definitions = (
    ("/加入部门", "从未分配状态加入一个部门"),
    ("/切换部门", "切换至一个已开放部门"),
    ("/职位", "查看职位和对应群内权益"),
    ("/晋升", "申请下一档职位"),
    ("/晋升申请列表", "查看可处理的晋升申请"),
    ("/同意", "同意指定编号的晋升申请"),
    ("/全部同意", "同意全部可处理的晋升申请"),
    ("/拒绝", "拒绝指定编号的晋升申请"),
    ("/全部拒绝", "拒绝全部可处理的晋升申请"),
)

reply_templates = (
    ("/加入部门", "joined", "{昵称}已加入{部门}。"),
    ("/加入部门", "usage", "请用 /加入部门 部门名 加入部门。"),
    ("/加入部门", "not_joined", "请先用 /入职 名字 加入摸鱼公司。"),
    ("/加入部门", "already_assigned", "你已加入部门，请使用 /切换部门 部门名。"),
    ("/加入部门", "unknown_department", "该部门不存在或暂未开放。"),
    ("/切换部门", "switched", "{昵称}已切换至{部门}。"),
    ("/切换部门", "usage", "请用 /切换部门 部门名 切换部门。"),
    ("/切换部门", "not_joined", "请先用 /入职 名字 加入摸鱼公司。"),
    ("/切换部门", "already_in_department", "你当前已在该部门。"),
    ("/切换部门", "unknown_department", "该部门不存在或暂未开放。"),
    ("/职位", "shown", "职位列表：\n{职位列表}"),
    ("/晋升", "requested", "{昵称}已提交晋升申请：{当前职位} → {目标职位}，需要 {晋升价格} {货币}。"),
    ("/晋升", "already_pending", "你已有一条待审批的晋升申请，请耐心等待。"),
    ("/晋升", "no_next_rank", "你当前没有可申请的下一档职位。"),
    ("/晋升", "not_joined", "请先用 /入职 名字 加入摸鱼公司。"),
    ("/晋升申请列表", "shown", "{申请列表}"),
    ("/晋升申请列表", "empty", "当前没有你可处理的晋升申请。"),
    ("/同意", "approved", "{昵称}已晋升为{目标职位}，扣除 {晋升价格} {货币}。"),
    ("/同意", "usage", "请用 /同意 1 2 3 审批申请。"),
    ("/同意", "empty", "当前没有你可处理的晋升申请。"),
    ("/同意", "insufficient_balance", "你的摸鱼币不够呢。"),
    ("/同意", "unavailable", "该晋升申请不可处理。"),
    ("/全部同意", "approved", "{昵称}已晋升为{目标职位}，扣除 {晋升价格} {货币}。"),
    ("/全部同意", "empty", "当前没有你可处理的晋升申请。"),
    ("/全部同意", "insufficient_balance", "你的摸鱼币不够呢。"),
    ("/全部同意", "unavailable", "该晋升申请不可处理。"),
    ("/拒绝", "rejected", "已拒绝{昵称}的晋升申请。"),
    ("/拒绝", "usage", "请用 /拒绝 1 2 3 审批申请。"),
    ("/拒绝", "empty", "当前没有你可处理的晋升申请。"),
    ("/拒绝", "unavailable", "该晋升申请不可处理。"),
    ("/全部拒绝", "rejected", "已拒绝{昵称}的晋升申请。"),
    ("/全部拒绝", "empty", "当前没有你可处理的晋升申请。"),
    ("/全部拒绝", "unavailable", "该晋升申请不可处理。"),
)


def _insert_if_missing(connection, table, values, index_elements) -> None:
    if connection.dialect.name == "postgresql":
        statement = postgresql.insert(table).values(**values)
    elif connection.dialect.name == "sqlite":
        statement = sqlite.insert(table).values(**values)
    else:
        raise ValueError(f"unsupported database dialect: {connection.dialect.name}")
    connection.execute(statement.on_conflict_do_nothing(index_elements=index_elements))


def upgrade() -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    connection = op.get_bind()
    definitions = sa.table(
        "command_definitions",
        sa.column("command", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    templates = sa.table(
        "command_reply_templates",
        sa.column("id", sa.Uuid()),
        sa.column("command", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("template", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    for command, description in command_definitions:
        _insert_if_missing(
            connection,
            definitions,
            {
                "command": command,
                "description": description,
                "enabled": True,
                "created_at": now,
            },
            [definitions.c.command],
        )
    for command, scenario, template in reply_templates:
        _insert_if_missing(
            connection,
            templates,
            {
                "id": uuid4(),
                "command": command,
                "scenario": scenario,
                "template": template,
                "created_at": now,
                "updated_at": now,
            },
            [templates.c.command, templates.c.scenario],
        )
    op.execute(
        templates.update()
        .where(
            templates.c.command == "/我",
            templates.c.scenario == "shown",
            templates.c.template == old_me_template,
        )
        .values(template=new_me_template, updated_at=now)
    )


def downgrade() -> None:
    templates = sa.table(
        "command_reply_templates",
        sa.column("command", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("template", sa.Text()),
    )
    op.execute(
        templates.update()
        .where(
            templates.c.command == "/我",
            templates.c.scenario == "shown",
            templates.c.template == new_me_template,
        )
        .values(template=old_me_template)
    )
