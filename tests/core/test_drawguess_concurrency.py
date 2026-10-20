import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, InboundRecord, OutboundRecord, PRIMARY_GROUP_CHAT_ID


POSTGRES_URL = os.getenv("DZMM_TEST_POSTGRES_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="需要隔离的 PostgreSQL 测试库")
def test_concurrent_last_seat_and_strokes():
    engine = create_engine(POSTGRES_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repo = CoreRepository(factory)
    now = datetime.now(timezone.utc)
    repo.bootstrap_primary_group("https://www.aikda.com/chat?c=drawguess-pg", now)
    for uid in ("host", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"):
        repo.create_user(uid, uid, now, 0)
    inbound = uuid4()
    with factory.begin() as session:
        session.add(InboundRecord(
            id=inbound, platform_message_id=str(inbound), sender_platform_id="host",
            content="/你画我猜", received_at=now, group_chat_id=PRIMARY_GROUP_CHAT_ID,
            chatroom_id="drawguess-pg",
        ))
    room = repo.create_drawguess_room("host", PRIMARY_GROUP_CHAT_ID, inbound, now)
    with factory.begin() as session:
        session.add(OutboundRecord(
            inbound_message_id=inbound, group_chat_id=PRIMARY_GROUP_CHAT_ID,
            text="入座码", status="sent", content_type="text",
        ))

    def act(view, uid, action, payload=None):
        return repo.drawguess_action(
            UUID(view["room_id"]), uid, view["state"]["turn_id"], view["state"]["version"],
            uuid4(), action, payload or {}, now,
        )

    for uid in ("p1", "p2", "p3", "p4", "p5", "p6"):
        room = act(room, uid, "claim", {"code": room["code"]})

    def claim(uid):
        try:
            return act(room, uid, "claim", {"code": room["code"]})
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ("p7", "p8")))
    assert sum(value is not None for value in claims) == 1
    room = repo.drawguess_view(UUID(room["room_id"]), "host", now)
    assert len(room["state"]["players"]) == 8
    for player in ["host", "p1", "p2", "p3", "p4", "p5", "p6", "p7" if claims[0] else "p8"]:
        room = act(room, player, "ready")
    room = act(room, "host", "start")
    selected = room["state"]["candidates"][0]
    room = act(room, "host", "choose", {"word_id": selected["id"]})
    operation = {"op": "begin", "stroke_id": "unused", "points": [[0.1, 0.1]],
                 "color": "#222222", "width": 0.008, "tool": "pen"}

    def stroke(index):
        return repo.drawguess_strokes(
            UUID(room["room_id"]), "host", room["state"]["turn_id"], uuid4(),
            [{**operation, "stroke_id": f"s{index}"}], now,
        )["cursor"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        cursors = list(pool.map(stroke, range(8)))
    assert len(set(cursors)) == 8
    assert max(cursors) - min(cursors) == 7
