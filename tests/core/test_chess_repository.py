from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, InboundRecord, OutboundRecord, PRIMARY_GROUP_CHAT_ID


NOW = datetime(2026, 10, 13, 12, tzinfo=ZoneInfo("Asia/Shanghai"))


@pytest.fixture
def chess_repo(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'chess.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repo = CoreRepository(factory)
    repo.bootstrap_primary_group("https://www.aikda.com/chat?c=chess", NOW)
    for pid in ("creator", "alice", "bob"):
        repo.create_user(pid, pid, NOW, 0)
    inbound_id = uuid4()
    with factory.begin() as session:
        session.add(InboundRecord(id=inbound_id, platform_message_id="chess-start", sender_platform_id="creator", content="/象棋", received_at=NOW, group_chat_id=PRIMARY_GROUP_CHAT_ID, chatroom_id="chess"))
    return repo, factory, inbound_id


def mark_sent(factory, inbound_id):
    with factory.begin() as session:
        session.add(OutboundRecord(inbound_message_id=inbound_id, group_chat_id=PRIMARY_GROUP_CHAT_ID, text="chess link", status="sent"))


def test_parallel_games_and_sent_gate(chess_repo):
    repo, factory, inbound_id = chess_repo
    one = repo.create_chess_game("creator", PRIMARY_GROUP_CHAT_ID, inbound_id, NOW)
    two = repo.create_chess_game("creator", PRIMARY_GROUP_CHAT_ID, inbound_id, NOW)
    assert one.id != two.id
    assert one.code.isdigit() and len(one.code) == 4
    assert repo.claim_chess_seat(one.id, "alice", one.code, NOW).status == "not_announced"
    mark_sent(factory, inbound_id)
    assert repo.claim_chess_seat(one.id, "creator", one.code, NOW).status == "same_player"
    assert repo.claim_chess_seat(one.id, "nobody", one.code, NOW).status == "not_joined"
    assert repo.claim_chess_seat(one.id, "alice", "00000", NOW).status == "invalid_code"
    claimed = repo.claim_chess_seat(one.id, "alice", one.code, NOW)
    assert claimed.status == "claimed"
    assert claimed.game.status == "playing"
    assert claimed.game.red_platform_id in {"creator", "alice"}
    assert claimed.game.black_platform_id in {"creator", "alice"}
    assert repo.claim_chess_seat(one.id, "bob", one.code, NOW).status == "occupied"
    assert repo.claim_chess_seat(two.id, "bob", two.code, NOW + timedelta(minutes=10)).status == "expired"
    with pytest.raises(ValueError):
        repo.create_chess_game("nobody", PRIMARY_GROUP_CHAT_ID, inbound_id, NOW)


def test_concurrent_claim_has_one_winner(chess_repo):
    repo, factory, inbound_id = chess_repo
    game = repo.create_chess_game("creator", PRIMARY_GROUP_CHAT_ID, inbound_id, NOW)
    mark_sent(factory, inbound_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pid: repo.claim_chess_seat(game.id, pid, game.code, NOW), ("alice", "bob")))
    assert sorted(result.status for result in results) == ["claimed", "occupied"]
    assert repo.get_chess_game(game.id).version == 1
