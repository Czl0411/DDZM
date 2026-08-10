"""Add authoritative AI knowledge cards and command syntax."""

from collections.abc import Sequence
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260810_32"
down_revision: str | None = "20260810_31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


COMMAND_SYNTAX = {
    "/入职": "/入职 名字", "/我的物品": "/我的物品", "/打卡": "/打卡",
    "/余额": "/余额", "/我": "/我；/me", "/商店": "/商店", "/帮助": "/帮助",
    "/加入": "/加入；/加入 身份", "/退出": "/退出",
    "/摸鱼躲猫猫": "/开始摸鱼躲藏；/躲 编号",
    "/记忆考核": "/记忆考核；/记忆考核 对战；/答案 内容",
    "/继续": "/继续", "/收手": "/收手", "/投降": "/投降",
    "/部门": "/部门", "/加入部门": "/加入部门 部门名",
    "/切换部门": "/切换部门 部门名", "/部门申请列表": "/部门申请列表",
    "/同意部门": "/同意部门 编号", "/全部同意部门": "/全部同意部门",
    "/拒绝部门": "/拒绝部门 编号", "/全部拒绝部门": "/全部拒绝部门",
    "/职位": "/职位", "/晋升": "/晋升", "/晋升申请列表": "/晋升申请列表",
    "/同意": "/同意 编号", "/全部同意": "/全部同意",
    "/拒绝": "/拒绝 编号", "/全部拒绝": "/全部拒绝",
    "/谁是卧底": "/谁是卧底 人数", "/开始投票": "/开始投票",
    "/投票": "/投票 序号", "/退出谁是卧底": "/退出谁是卧底",
    "/结束游戏": "/结束游戏", "/甩锅游戏": "/甩锅游戏 人数",
    "/甩锅": "/甩锅 玩家编号 甩锅理由", "/退出甩锅": "/退出甩锅",
}

KNOWLEDGE_CARDS = (
    ("economy", "金币与余额原则", ["金币", "摸鱼币", "赚钱", "收入", "余额"], "余额可能因奖励或惩罚变化；具体可用来源、金额和条件必须以实时数据为准。"),
    ("departments", "部门加入与切换", ["部门", "加入部门", "切换部门", "部门申请"], "首次加入部门与切换部门使用不同流程；普通员工通常需要目标部门更高职位成员审批，核心董事会按系统权限直接处理。"),
    ("ranks", "职位与晋升", ["职位", "职级", "晋升", "升职"], "晋升只申请下一档普通职位，申请时不扣款，同意时按冻结价格结算；核心董事会不能通过普通晋升获得。"),
    ("shop", "商店与物品", ["商店", "商品", "物品", "购买"], "商店只展示当前可用商品；是否存在购买或使用指令必须以实时启用命令为准。"),
    ("checkin_activity", "打卡与活跃度", ["打卡", "活跃", "全勤", "连续打卡"], "成功打卡按自然日计算；普通非指令发言可形成日活跃度，奖励由后台按系统配置结算。"),
    ("random_events", "随机事件", ["随机事件", "事件", "角色报名"], "随机事件按场景报名并进行；只有正式业务结果决定是否完成和获得奖励，过程发言不改变固定规则。"),
    ("hide_and_seek", "摸鱼躲猫猫", ["躲猫猫", "躲藏", "巡查"], "玩家先发起再从系统展示的地点编号中选择；最终奖励、惩罚、次数和时限以当前配置为准。"),
    ("memory_assessment", "记忆考核", ["记忆考核", "答案", "收手", "对战"], "记忆考核分单人和对战；只有机器人确认题目撤回后才接受格式正确的答案，具体难度、奖励与时限以实时配置为准。"),
    ("undercover", "谁是卧底", ["谁是卧底", "卧底", "白板", "投票"], "谁是卧底通过报名、发牌、描述和投票推进；角色配比、投票时间和胜负阈值以当前配置为准。"),
    ("blame_bomb", "甩锅游戏", ["甩锅", "锅", "事故卡", "关键词"], "甩锅游戏按编号公开转交，理由必须满足本局冻结关键词；时间、人数和经济结果以当前对局与配置为准。"),
    ("commands_help", "指令帮助", ["指令", "命令", "帮助", "怎么操作"], "只推荐当前启用且由系统提供准确语法的指令；没有可靠指令时引导玩家查看帮助。"),
    ("player_activity", "个人游戏经历", ["战绩", "玩过", "赢过", "输了", "参加过"], "个人游戏经历只使用系统结算产生的累计参与、胜负和最近结果，不根据聊天自述推断。"),
)


def upgrade() -> None:
    op.add_column(
        "command_definitions",
        sa.Column("syntax", sa.Text(), nullable=False, server_default=""),
    )
    commands = sa.table(
        "command_definitions",
        sa.column("command", sa.String()),
        sa.column("syntax", sa.Text()),
    )
    for command, syntax in COMMAND_SYNTAX.items():
        op.execute(commands.update().where(commands.c.command == command).values(syntax=syntax))
    op.create_table(
        "ai_knowledge_cards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("keywords", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_knowledge_cards_topic_enabled_priority",
        "ai_knowledge_cards",
        ["topic", "enabled", "priority"],
    )
    cards = sa.table(
        "ai_knowledge_cards",
        sa.column("id", sa.Uuid()), sa.column("topic", sa.String()),
        sa.column("title", sa.String()), sa.column("keywords", sa.JSON()),
        sa.column("content", sa.Text()), sa.column("enabled", sa.Boolean()),
        sa.column("priority", sa.Integer()), sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    op.bulk_insert(cards, [
        {"id": uuid4(), "topic": topic, "title": title, "keywords": keywords,
         "content": content, "enabled": True, "priority": 100,
         "created_at": now, "updated_at": now}
        for topic, title, keywords, content in KNOWLEDGE_CARDS
    ])


def downgrade() -> None:
    op.drop_index("ix_ai_knowledge_cards_topic_enabled_priority", table_name="ai_knowledge_cards")
    op.drop_table("ai_knowledge_cards")
    op.drop_column("command_definitions", "syntax")
