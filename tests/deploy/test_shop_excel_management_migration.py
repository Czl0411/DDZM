from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[2]


def test_shop_management_migration_preserves_defaults_and_history(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'shop-management.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    engine = sa.create_engine(database_url)
    metadata = sa.MetaData()
    items = sa.Table("items", metadata,
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("name", sa.String(64)),
        sa.Column("price", sa.Integer()), sa.Column("system_key", sa.String(64)),
        sa.Column("effect_type", sa.String(32)),
    )
    purchases = sa.Table("shop_purchases", metadata,
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("item_id", sa.Uuid()), sa.Column("price", sa.Integer()))
    uses = sa.Table("shop_item_uses", metadata,
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("item_id", sa.Uuid()))
    metadata.create_all(engine)
    gift_id, scratch_id, scene_id, common_id, ordinary_id = (uuid4() for _ in range(5))
    with engine.begin() as connection:
        connection.execute(items.insert(), [
            {"id": gift_id, "name": "赠送卡", "price": 10, "system_key": "gift_advanced", "effect_type": "gift"},
            {"id": scratch_id, "name": "刮刮卡", "price": 20, "system_key": "scratch_c", "effect_type": "scratch"},
            {"id": scene_id, "name": "场景卡", "price": 80, "system_key": "adult_three", "effect_type": "adult_scene"},
            {"id": common_id, "name": "状态卡", "price": 80, "system_key": "adult_common_6h", "effect_type": "adult_common"},
            {"id": ordinary_id, "name": "普通商品", "price": 1, "system_key": None, "effect_type": None},
        ])
        connection.execute(purchases.insert(), [{"id": uuid4(), "item_id": gift_id, "price": 7}])
        connection.execute(uses.insert(), [{"id": uuid4(), "item_id": scene_id}])
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    command.stamp(config, "20261004_93")
    command.upgrade(config, "20261004_94")
    migrated = sa.Table("items", sa.MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        rows = {UUID(str(row["id"])): row for row in connection.execute(sa.select(migrated)).mappings()}
        assert rows[gift_id]["effect_config"] == {"reward": 8}
        assert rows[scratch_id]["effect_config"] == {"reward_min": 10, "reward_max": 30}
        assert rows[scene_id]["effect_config"] == {"template": "adult_three", "recipient_count": 2}
        assert rows[common_id]["effect_config"] == {"template": "adult_common_6h", "duration_minutes": 360}
        assert rows[ordinary_id]["effect_config"] == {}
        assert all(row["deleted_at"] is None and row["configuration_version"] == 1 for row in rows.values())
        history = sa.Table("shop_purchases", sa.MetaData(), autoload_with=engine)
        purchase = connection.execute(sa.select(history)).mappings().one()
        assert purchase["price"] == 7 and purchase["item_snapshot"]["name"] == "赠送卡"
        history = sa.Table("shop_item_uses", sa.MetaData(), autoload_with=engine)
        assert connection.execute(sa.select(history.c.item_snapshot)).scalar_one()["effect_type"] == "adult_scene"
    assert {"shop_catalog_state", "shop_change_batches"} <= set(sa.inspect(engine).get_table_names())
    with engine.begin() as connection:
        connection.execute(migrated.update().where(migrated.c.id == gift_id.hex).values(effect_config={"reward": 99}))
    with pytest.raises(RuntimeError, match="请先恢复原默认效果"):
        command.downgrade(config, "20261004_93")
    assert "effect_config" in {column["name"] for column in sa.inspect(engine).get_columns("items")}
    with engine.begin() as connection:
        connection.execute(migrated.update().where(migrated.c.id == gift_id.hex).values(effect_config={"reward": 8}))
    command.downgrade(config, "20261004_93")
    assert "effect_config" not in {column["name"] for column in sa.inspect(engine).get_columns("items")}
    assert "shop_change_batches" not in sa.inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(items)) == 5
    command.upgrade(config, "20261004_94")
    assert "effect_config" in {column["name"] for column in sa.inspect(engine).get_columns("items")}
