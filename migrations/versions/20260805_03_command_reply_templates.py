"""Add editable group command reply templates."""

from collections.abc import Sequence
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260805_03"
down_revision: str | None = "20260805_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TEMPLATES = (
    ("/入职", "joined", "{昵称}，欢迎入职摸鱼公司。当前余额：{余额} 摸鱼币。"),
    ("/入职", "already_joined", "{昵称}已经在职，当前余额：{余额} 摸鱼币。"),
    ("/入职", "missing_name", "请用 /入职 名字 加入摸鱼公司。"),
    ("/打卡", "checked_in", "打卡成功，领取 {打卡奖励} 摸鱼币。当前余额：{余额} 摸鱼币。"),
    ("/打卡", "already_checked_in", "今天已经打过卡啦，明天再来。"),
    ("/打卡", "not_joined", "请先用 /入职 名字 加入摸鱼公司。"),
    ("/余额", "shown", "{昵称}，当前余额：{余额} 摸鱼币。"),
    ("/余额", "not_joined", "请先用 /入职 名字 加入摸鱼公司。"),
    ("/我的物品", "shown", "{昵称}的物品：\n{物品列表}"),
    ("/我的物品", "not_joined", "请先用 /入职 名字 加入摸鱼公司。"),
    ("/商店", "items_available", "总监事小卖部：\n{商店列表}"),
    ("/商店", "empty", "总监事小卖部还没有上架商品。"),
    ("/帮助", "shown", "总监事指令簿：\n{指令列表}"),
)


def upgrade() -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "command_reply_templates",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("command", sa.String(length=32), nullable=False),
        sa.Column("scenario", sa.String(length=64), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command", "scenario"),
    )
    command_definitions = sa.table(
        "command_definitions",
        sa.column("command", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        postgresql.insert(command_definitions)
        .values(
            command="/帮助",
            description="查看当前可用指令",
            enabled=True,
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=["command"])
    )
    template_table = sa.table(
        "command_reply_templates",
        sa.column("id", uuid_type),
        sa.column("command", sa.String()),
        sa.column("scenario", sa.String()),
        sa.column("template", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        template_table,
        [
            {
                "id": uuid4(),
                "command": command,
                "scenario": scenario,
                "template": template,
                "created_at": now,
                "updated_at": now,
            }
            for command, scenario, template in _TEMPLATES
        ],
    )


def downgrade() -> None:
    op.drop_table("command_reply_templates")
    op.execute(
        sa.text("DELETE FROM command_definitions WHERE command = :command").bindparams(
            command="/帮助"
        )
    )

