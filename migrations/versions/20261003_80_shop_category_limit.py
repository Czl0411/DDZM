"""shop item category and daily purchase limit

Revision ID: 20261003_80
Revises: 20261003_79
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_80"
down_revision: str | None = "20261003_79"
branch_labels = None
depends_on = None

# system_key → (category, daily_purchase_limit)；沿用此前代码硬编码的行为
_SYSTEM_ITEM_DEFAULTS = {
    "gift_basic": ("礼物赠送", 2),
    "gift_intermediate": ("礼物赠送", 2),
    "gift_advanced": ("礼物赠送", 2),
    "gift_platinum": ("礼物赠送", 2),
    "scratch_a": ("刮刮乐", 3),
    "scratch_b": ("刮刮乐", 3),
    "scratch_c": ("刮刮乐", 3),
    "ai_quota": ("功能道具", None),
    "multiplayer_quota": ("功能道具", None),
    "adult_m": ("成人内容", None),
    "adult_flirt": ("成人内容", None),
    "adult_training_invite": ("成人内容", None),
    "adult_trained_invite": ("成人内容", None),
    "adult_love": ("成人内容", None),
    "adult_three": ("成人内容", None),
    "adult_four": ("成人内容", None),
    "adult_six": ("成人内容", None),
    "adult_sleep": ("成人内容", None),
    "adult_gender_change": ("成人内容", None),
    "adult_common_1h": ("成人内容", None),
    "adult_common_6h": ("成人内容", None),
    "adult_common_24h": ("成人内容", None),
}


def upgrade() -> None:
    op.add_column("items", sa.Column("category", sa.String(length=32)))
    op.add_column("items", sa.Column("daily_purchase_limit", sa.Integer()))
    items_table = sa.table(
        "items",
        sa.column("system_key", sa.String),
        sa.column("category", sa.String),
        sa.column("daily_purchase_limit", sa.Integer),
    )
    for key, (category, limit) in _SYSTEM_ITEM_DEFAULTS.items():
        op.execute(
            items_table.update()
            .where(items_table.c.system_key == key)
            .values(category=category, daily_purchase_limit=limit)
        )
    with op.batch_alter_table("shop_purchase_daily_usage") as batch_op:
        batch_op.alter_column(
            "category",
            existing_type=sa.String(length=16),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
    usage_table = sa.table(
        "shop_purchase_daily_usage",
        sa.column("category", sa.String),
    )
    for legacy, current in (("gift", "礼物赠送"), ("scratch", "刮刮乐")):
        op.execute(
            usage_table.update()
            .where(usage_table.c.category == legacy)
            .values(category=current)
        )


def downgrade() -> None:
    usage_table = sa.table(
        "shop_purchase_daily_usage",
        sa.column("category", sa.String),
    )
    for current, legacy in (("礼物赠送", "gift"), ("刮刮乐", "scratch")):
        op.execute(
            usage_table.update()
            .where(usage_table.c.category == current)
            .values(category=legacy)
        )
    with op.batch_alter_table("shop_purchase_daily_usage") as batch_op:
        batch_op.alter_column(
            "category",
            existing_type=sa.String(length=32),
            type_=sa.String(length=16),
            existing_nullable=False,
        )
    op.drop_column("items", "daily_purchase_limit")
    op.drop_column("items", "category")
