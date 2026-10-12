"""Join the existing game branch with the feature-test branch."""

from alembic import op
import sqlalchemy as sa


revision = "20261009_101"
down_revision = "20261006_100"
branch_labels = None
depends_on = None


_SCRATCH_DEFAULTS = {
    "scratch_a": (1, 10),
    "scratch_b": (5, 15),
    "scratch_c": (10, 30),
}


def upgrade() -> None:
    items = sa.table(
        "items",
        sa.column("id", sa.Uuid()),
        sa.column("system_key", sa.String()),
        sa.column("scratch_reward_min", sa.Integer()),
        sa.column("scratch_reward_max", sa.Integer()),
        sa.column("effect_config", sa.JSON()),
        sa.column("category", sa.String()),
        sa.column("daily_purchase_limit", sa.Integer()),
    )
    connection = op.get_bind()
    for row in connection.execute(sa.select(items)).mappings():
        key = row["system_key"]
        if key == "event_ad_slot":
            values = {}
            if row["category"] is None:
                values["category"] = "event_ad_slot"
            if row["daily_purchase_limit"] is None:
                values["daily_purchase_limit"] = 1
            if values:
                connection.execute(items.update().where(items.c.id == row["id"]).values(**values))
            continue
        if key not in _SCRATCH_DEFAULTS:
            continue
        config = dict(row["effect_config"] or {})
        configured = (config.get("reward_min"), config.get("reward_max"))
        legacy = (row["scratch_reward_min"], row["scratch_reward_max"])
        if legacy[0] is not None and legacy[1] is not None and configured == _SCRATCH_DEFAULTS[key]:
            config.update(reward_min=legacy[0], reward_max=legacy[1])
            connection.execute(items.update().where(items.c.id == row["id"]).values(effect_config=config))
        elif configured[0] is not None and configured[1] is not None and legacy != configured:
            connection.execute(
                items.update().where(items.c.id == row["id"]).values(
                    scratch_reward_min=configured[0], scratch_reward_max=configured[1]
                )
            )


def downgrade() -> None:
    pass
