"""Persist a random multiplier for each number-bomb round."""

from collections.abc import Sequence
from uuid import UUID

from alembic import op
import sqlalchemy as sa


revision: str = "20260812_40"
down_revision: str | None = "20260812_39"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NUMBER_BOMB_KNOWLEDGE_CARD_ID = UUID("01c667a1-8f6e-4bcb-bde6-e1fba5d63c9d")
OLD_CONTENT = (
    "发送 /蹦蹦数字炸弹 开启不限人数报名，参与者发送 /加入，至少3人后任一参与者发送 /开始。"
    "每轮按私聊提示发送 /报数 数字；群内会定时提醒未报数者，提醒后可用 /跳过 编号移除未报数玩家。"
    "有效轮结算后发送 /继续，开局后不会因无操作自动解散。"
)
NEW_CONTENT = (
    "发送 /蹦蹦数字炸弹 开启不限人数报名，参与者发送 /加入，至少3人后任一参与者发送 /开始。"
    "每轮按私聊提示发送 /报数 数字；群内会定时提醒未报数者，提醒后可用 /跳过 编号移除未报数玩家。"
    "每轮结算时公布随机倍率（0.8、0.9、1.0、1.1、1.2之一），并按平均数乘该倍率计算。"
    "有效轮结算后发送 /继续，开局后不会因无操作自动解散。"
)


def upgrade() -> None:
    with op.batch_alter_table("number_bomb_rounds") as batch_op:
        batch_op.add_column(
            sa.Column(
                "multiplier_tenths",
                sa.Integer(),
                nullable=False,
                server_default="8",
            )
        )
        batch_op.create_check_constraint(
            "ck_number_bomb_round_multiplier_tenths",
            "multiplier_tenths IN (8, 9, 10, 11, 12)",
        )
    _replace_known_content(OLD_CONTENT, NEW_CONTENT)


def downgrade() -> None:
    _replace_known_content(NEW_CONTENT, OLD_CONTENT)
    with op.batch_alter_table("number_bomb_rounds") as batch_op:
        batch_op.drop_constraint(
            "ck_number_bomb_round_multiplier_tenths", type_="check"
        )
        batch_op.drop_column("multiplier_tenths")


def _replace_known_content(old_content: str, new_content: str) -> None:
    cards = sa.table(
        "ai_knowledge_cards",
        sa.column("id", sa.Uuid()),
        sa.column("content", sa.Text()),
    )
    op.get_bind().execute(
        cards.update()
        .where(
            cards.c.id == NUMBER_BOMB_KNOWLEDGE_CARD_ID,
            cards.c.content == old_content,
        )
        .values(content=new_content)
    )
