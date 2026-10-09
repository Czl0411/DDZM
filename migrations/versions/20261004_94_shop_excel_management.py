"""shop lifecycle, configurable effects and durable import previews

Revision ID: 20261004_94
Revises: 20261004_93
Create Date: 2026-10-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20261004_94"
down_revision = "20261004_93"
branch_labels = None
depends_on = None

GIFT_AMOUNTS = {"gift_basic": 2, "gift_intermediate": 4, "gift_advanced": 8, "gift_platinum": 15}
SCRATCH_RANGES = {"scratch_a": (1, 10), "scratch_b": (5, 15), "scratch_c": (10, 30)}
SCENE_COUNTS = {"adult_three": 2, "adult_four": 3, "adult_six": 5}
COMMON_DURATIONS = {"adult_common_1h": 60, "adult_common_6h": 360, "adult_common_24h": 1440}
LEGACY_EFFECT_TYPES = {
    **{key: "gift" for key in GIFT_AMOUNTS},
    **{key: "scratch" for key in SCRATCH_RANGES},
    **{key: "adult_common" for key in COMMON_DURATIONS},
    **{key: "adult_scene" for key in (
        "adult_flirt", "adult_training_invite", "adult_trained_invite", "adult_love",
        "adult_three", "adult_four", "adult_six", "adult_sleep", "adult_gender_change",
    )},
    "ai_quota": "ai_quota", "multiplayer_quota": "multiplayer_quota", "adult_m": "adult_m",
}


def legacy_effect_config(key, effect_type):
    if effect_type == "gift":
        return {"reward": GIFT_AMOUNTS.get(key, 2)}
    if effect_type == "scratch":
        minimum, maximum = SCRATCH_RANGES.get(key, (1, 10))
        return {"reward_min": minimum, "reward_max": maximum}
    if effect_type in ("ai_quota", "multiplayer_quota"):
        return {"quota": 1}
    if effect_type == "adult_scene":
        return {"template": key, "recipient_count": SCENE_COUNTS.get(key, 1)}
    if effect_type == "adult_common":
        return {"template": key, "duration_minutes": COMMON_DURATIONS.get(key, 60)}
    return {}


def upgrade():
    op.add_column("items", sa.Column("effect_config", sa.JSON(), nullable=True))
    op.add_column("items", sa.Column("configuration_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("items", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    for table in ("shop_purchases", "shop_item_uses"):
        op.add_column(table, sa.Column("item_snapshot", sa.JSON(), nullable=True))
    op.create_table("shop_catalog_state", sa.Column("id", sa.Integer(), primary_key=True))
    op.create_table("shop_change_batches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
    )
    connection = op.get_bind()
    items = sa.table("items", sa.column("id", sa.Uuid()), sa.column("name", sa.String()),
        sa.column("price", sa.Integer()), sa.column("system_key", sa.String()),
        sa.column("effect_type", sa.String()), sa.column("effect_config", sa.JSON()))
    snapshots = {}
    for row in connection.execute(sa.select(items)).mappings():
        key, effect_type = row["system_key"], row["effect_type"]
        config = legacy_effect_config(key, effect_type)
        connection.execute(items.update().where(items.c.id == row["id"]).values(effect_config=config))
        snapshots[row["id"]] = {"name": row["name"], "price": row["price"],
            "effect_type": effect_type, "effect_config": config}
    for table_name in ("shop_purchases", "shop_item_uses"):
        history = sa.table(table_name, sa.column("item_id", sa.Uuid()), sa.column("item_snapshot", sa.JSON()))
        for item_id, snapshot in snapshots.items():
            connection.execute(history.update().where(history.c.item_id == item_id).values(item_snapshot=snapshot))


def downgrade():
    items = sa.table("items", sa.column("name", sa.String()), sa.column("system_key", sa.String()),
        sa.column("effect_type", sa.String()), sa.column("effect_config", sa.JSON()))
    for row in op.get_bind().execute(sa.select(items)).mappings():
        expected_type = LEGACY_EFFECT_TYPES.get(row["system_key"])
        expected_config = legacy_effect_config(row["system_key"], expected_type)
        if row["effect_type"] != expected_type or (row["effect_config"] or {}) != expected_config:
            raise RuntimeError(f"商品“{row['name']}”配置了旧版本不支持的效果；请先恢复原默认效果和参数，再执行降级")
    op.drop_table("shop_change_batches")
    op.drop_table("shop_catalog_state")
    for table in ("shop_purchases", "shop_item_uses"):
        op.drop_column(table, "item_snapshot")
    for column in ("deleted_at", "configuration_version", "effect_config"):
        op.drop_column("items", column)
