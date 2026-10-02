from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Uuid,
    create_engine,
    inspect,
    text,
)


ROOT = Path(__file__).resolve().parents[2]


def test_shop_category_limit_migration_backfills_system_items(
    tmp_path, monkeypatch
):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'shop-category-limit.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(database_url)
    metadata = MetaData()
    items = Table(
        "items",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("system_key", String(64)),
        Column("name", String(64), nullable=False),
    )
    usage = Table(
        "shop_purchase_daily_usage",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("category", String(16), nullable=False),
        Column("count", Integer, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            items.insert(),
            [
                {"id": uuid4(), "system_key": "gift_basic", "name": "初级赠送卡"},
                {"id": uuid4(), "system_key": "scratch_a", "name": "刮刮卡 A"},
                {"id": uuid4(), "system_key": "ai_quota", "name": "总监事对话卡"},
                {"id": uuid4(), "system_key": None, "name": "自建商品"},
            ],
        )
        connection.execute(
            usage.insert(),
            [
                {"id": uuid4(), "category": "gift", "count": 1},
                {"id": uuid4(), "category": "scratch", "count": 2},
            ],
        )
    command.stamp(config, "20261003_79")

    command.upgrade(config, "20261003_80")

    assert {"category", "daily_purchase_limit"} <= {
        column["name"] for column in inspect(engine).get_columns("items")
    }
    with engine.connect() as connection:
        defaults = {
            system_key: (category, limit)
            for system_key, category, limit in connection.execute(
                text("SELECT system_key, category, daily_purchase_limit FROM items")
            ).all()
        }
        buckets = dict(
            connection.execute(
                text("SELECT category, count FROM shop_purchase_daily_usage")
            ).all()
        )
    assert defaults["gift_basic"] == ("礼物赠送", 2)
    assert defaults["scratch_a"] == ("刮刮乐", 3)
    assert defaults["ai_quota"] == ("功能道具", None)
    assert defaults[None] == (None, None)
    assert buckets == {"礼物赠送": 1, "刮刮乐": 2}

    command.downgrade(config, "20261003_79")

    assert "category" not in {
        column["name"] for column in inspect(engine).get_columns("items")
    }
    with engine.connect() as connection:
        assert dict(
            connection.execute(
                text("SELECT category, count FROM shop_purchase_daily_usage")
            ).all()
        ) == {"gift": 1, "scratch": 2}
