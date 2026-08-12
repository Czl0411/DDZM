from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    create_engine,
    inspect,
    text,
)


ROOT = Path(__file__).resolve().parents[2]
NUMBER_BOMB_KNOWLEDGE_CARD_ID = UUID("01c667a1-8f6e-4bcb-bde6-e1fba5d63c9d")
OLD_CONTENT = (
    "发送 /蹦蹦数字炸弹 开启不限人数报名，参与者发送 /加入，至少3人后任一参与者发送 /开始。"
    "每轮按私聊提示发送 /报数 数字；群内会定时提醒未报数者，提醒后可用 /跳过 编号移除未报数玩家。"
    "有效轮结算后发送 /继续，开局后不会因无操作自动解散。"
)


def test_number_bomb_random_multiplier_migration_backfills_and_downgrades(
    tmp_path, monkeypatch
):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'number-bomb-multiplier.db'}"
    monkeypatch.setenv("DZMM_DATABASE_URL", database_url)
    config = Config(str(ROOT / "alembic.ini"))
    engine = create_engine(database_url)
    metadata = MetaData()
    rounds = Table(
        "number_bomb_rounds",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("game_id", Uuid, nullable=False),
        Column("round_number", Integer, nullable=False),
        Column("attempt_number", Integer, nullable=False),
        Column("punishment_type", String(16), nullable=False),
        Column("state", String(32), nullable=False),
        Column("total", Integer),
        Column("player_count", Integer, nullable=False),
        Column("target_numerator", Integer),
        Column("target_denominator", Integer),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("finished_at", DateTime(timezone=True)),
    )
    cards = Table(
        "ai_knowledge_cards",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("content", Text, nullable=False),
    )
    metadata.create_all(engine)
    now = datetime(2026, 8, 12, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            rounds.insert(),
            {
                "id": uuid4(),
                "game_id": uuid4(),
                "round_number": 1,
                "attempt_number": 1,
                "punishment_type": "truth",
                "state": "settled",
                "total": 150,
                "player_count": 3,
                "target_numerator": 600,
                "target_denominator": 15,
                "created_at": now,
                "finished_at": now,
            },
        )
        connection.execute(
            cards.insert(),
            {"id": NUMBER_BOMB_KNOWLEDGE_CARD_ID, "content": OLD_CONTENT},
        )
    command.stamp(config, "20260812_39")

    command.upgrade(config, "20260812_40")

    assert "multiplier_tenths" in {
        column["name"] for column in inspect(engine).get_columns("number_bomb_rounds")
    }
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT multiplier_tenths FROM number_bomb_rounds")
        ).scalar_one() == 8
        assert "每轮结算时公布随机倍率" in connection.execute(
            text("SELECT content FROM ai_knowledge_cards")
        ).scalar_one()
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20260812_40"

    command.downgrade(config, "20260812_39")

    assert "multiplier_tenths" not in {
        column["name"] for column in inspect(engine).get_columns("number_bomb_rounds")
    }
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT content FROM ai_knowledge_cards")
        ).scalar_one() == OLD_CONTENT
