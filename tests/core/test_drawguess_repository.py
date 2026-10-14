from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import (
    Base, DrawguessRoomRecord, InboundRecord, OutboundRecord, PRIMARY_GROUP_CHAT_ID,
)


NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)


@pytest.fixture
def game(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'drawguess.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repo = CoreRepository(factory)
    repo.bootstrap_primary_group("https://www.aikda.com/chat?c=drawguess", NOW)
    for uid in ("host", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "viewer"):
        repo.create_user(uid, uid, NOW, 0)
    inbound = uuid4()
    with factory.begin() as session:
        session.add(InboundRecord(
            id=inbound, platform_message_id=str(inbound), sender_platform_id="host",
            content="/你画我猜", received_at=NOW, group_chat_id=PRIMARY_GROUP_CHAT_ID,
            chatroom_id="drawguess",
        ))
    return repo, factory, inbound


def create_room(game, announced=True):
    repo, factory, inbound = game
    room = repo.create_drawguess_room("host", PRIMARY_GROUP_CHAT_ID, inbound, NOW)
    if announced:
        with factory.begin() as session:
            session.add(OutboundRecord(
                inbound_message_id=inbound, group_chat_id=PRIMARY_GROUP_CHAT_ID,
                text="入座码", status="sent", content_type="text",
            ))
    return room


def action(repo, room, uid, kind, payload=None, now=NOW, request_id=None):
    return repo.drawguess_action(
        UUID(room["room_id"]), uid, room["state"]["turn_id"], room["state"]["version"],
        request_id or uuid4(), kind, payload or {}, now,
    )


def started(game):
    repo = game[0]
    room = create_room(game)
    for uid in ("p1", "p2"):
        room = action(repo, room, uid, "claim", {"code": room["code"]})
    for uid in ("host", "p1", "p2"):
        room = action(repo, room, uid, "ready")
    return action(repo, room, "host", "start")


def test_claim_ready_start_host_transfer_and_rematch(game):
    repo, factory, _ = game
    room = create_room(game, announced=False)
    assert repo.create_drawguess_room("host", PRIMARY_GROUP_CHAT_ID, game[2], NOW)["room_id"] == room["room_id"]
    with pytest.raises(ValueError, match="送达"):
        action(repo, room, "p1", "claim", {"code": room["code"]})
    create_room(game, announced=True)
    for uid in ("p1", "p2", "p3", "p4", "p5", "p6", "p7"):
        room = action(repo, room, uid, "claim", {"code": room["code"]})
    with pytest.raises(ValueError, match="坐满"):
        action(repo, room, "viewer", "claim", {"code": room["code"]})
    room = action(repo, room, "host", "leave")
    assert room["state"]["host_name"] == "p1"
    for uid in ("p1", "p2", "p3", "p4", "p5", "p6", "p7"):
        room = action(repo, room, uid, "ready")
    room = action(repo, room, "p1", "start")
    assert room["state"]["phase"] == "selecting"
    assert room["code"] is None
    with pytest.raises(ValueError, match="进行中"):
        action(repo, room, "viewer", "claim", {"code": "0000"})

    candidate = room["state"]["candidates"][0]
    room = action(repo, room, "p1", "choose", {"word_id": candidate["id"]}, NOW + timedelta(seconds=1))
    repo.drawguess_strokes(
        UUID(room["room_id"]), "p1", room["state"]["turn_id"], uuid4(),
        [{"op": "begin", "stroke_id": "old", "points": [[0.1, 0.1]],
          "color": "#222222", "width": 0.008, "tool": "pen"}], NOW + timedelta(seconds=2),
    )

    with factory.begin() as session:
        row = session.get(DrawguessRoomRecord, UUID(room["room_id"]))
        row.state = {**row.state, "phase": "finished", "ranking": []}
        row.phase = "finished"
        row.deadline = None
    room = repo.drawguess_view(UUID(room["room_id"]), "p1", NOW)
    room = action(repo, room, "p1", "rematch")
    assert room["state"]["phase"] == "waiting"
    assert all(not player["ready"] for player in room["state"]["players"])
    assert room["code"] and room["code"].isdigit()
    for uid in ("p1", "p2", "p3", "p4", "p5", "p6", "p7"):
        room = action(repo, room, uid, "ready")
    room = action(repo, room, "p1", "start")
    assert room["canvas"] == []


def test_expired_code_and_only_employees(game):
    repo, factory, _ = game
    room = create_room(game)
    with pytest.raises(ValueError, match="入职"):
        repo.list_drawguess_rooms("unknown", NOW)
    with pytest.raises(ValueError, match="入座码"):
        action(repo, room, "p1", "claim", {"code": room["code"]}, NOW + timedelta(minutes=10))
    with factory.begin() as session:
        assert session.scalar(select(DrawguessRoomRecord)).phase == "closed"


def test_deadline_guess_race_and_request_idempotency(game):
    repo = game[0]
    room = started(game)
    candidate = room["state"]["candidates"][0]
    other_candidate = room["state"]["candidates"][1]
    request_id = uuid4()
    room = action(repo, room, "host", "choose", {"word_id": candidate["id"]}, NOW + timedelta(seconds=1), request_id)
    repeated = repo.drawguess_action(
        UUID(room["room_id"]), "host", room["state"]["turn_id"], room["state"]["version"] - 1,
        request_id, "choose", {"word_id": candidate["id"]}, NOW + timedelta(seconds=2),
    )
    assert repeated["state"]["phase"] == "drawing"
    with pytest.raises(ValueError, match="内容不同"):
        repo.drawguess_action(
            UUID(room["room_id"]), "host", room["state"]["turn_id"], room["state"]["version"] - 1,
            request_id, "choose", {"word_id": other_candidate["id"]}, NOW + timedelta(seconds=2),
        )
    deadline = datetime.fromtimestamp(room["state"]["deadline_ms"] / 1000, timezone.utc)
    with pytest.raises(ValueError, match="超时"):
        action(repo, room, "p1", "guess", {"text": room["state"]["word_length"] * "字"}, deadline)
    advanced = repo.drawguess_view(UUID(room["room_id"]), "p1", deadline + timedelta(seconds=20))
    assert advanced["state"]["phase"] in {"selecting", "drawing", "revealing"}


def test_recipient_projection_and_chat_never_leak_answer(game):
    repo = game[0]
    room = started(game)
    host_view = repo.drawguess_view(UUID(room["room_id"]), "host", NOW)
    p1_view = repo.drawguess_view(UUID(room["room_id"]), "p1", NOW)
    assert "candidates" in host_view["state"]
    assert "candidates" not in p1_view["state"]
    assert "answer" not in p1_view["state"]
    chosen = host_view["state"]["candidates"][0]
    room = action(repo, host_view, "host", "choose", {"word_id": chosen["id"]}, NOW + timedelta(seconds=1))
    assert repo.drawguess_view(UUID(room["room_id"]), "host", NOW)["state"]["answer"] == chosen["answer"]
    for uid in ("p1", "viewer"):
        projected = repo.drawguess_view(UUID(room["room_id"]), uid, NOW)
        assert "answer" not in projected["state"]
        assert "candidates" not in projected["state"]
    wrong = repo.drawguess_chat(UUID(room["room_id"]), "p1", room["state"]["turn_id"], uuid4(), "不是答案", NOW + timedelta(seconds=2))
    assert wrong["text"] == "不是答案"
    correct = repo.drawguess_chat(UUID(room["room_id"]), "p2", room["state"]["turn_id"], uuid4(), chosen["answer"], NOW + timedelta(seconds=2))
    assert correct["text"].startswith("已猜中 +")
    public = repo.drawguess_view(UUID(room["room_id"]), "p1", NOW + timedelta(seconds=2))
    assert chosen["answer"] not in repr(public["messages"])
    with pytest.raises(ValueError, match="观众"):
        repo.drawguess_chat(UUID(room["room_id"]), "viewer", room["state"]["turn_id"], uuid4(), "围观", NOW + timedelta(seconds=3))


def test_stroke_order_limits_clear_and_incremental_events(game):
    repo = game[0]
    room = started(game)
    candidate = room["state"]["candidates"][0]
    room = action(repo, room, "host", "choose", {"word_id": candidate["id"]}, NOW + timedelta(seconds=1))
    operation = {"op": "begin", "stroke_id": "s1", "points": [[0.1, 0.2], [0.2, 0.3]],
                 "color": "#222222", "width": 0.008, "tool": "pen"}
    request_id = uuid4()
    result = repo.drawguess_strokes(UUID(room["room_id"]), "host", room["state"]["turn_id"], request_id, [operation], NOW)
    assert result["cursor"] == 1
    repeated = repo.drawguess_strokes(UUID(room["room_id"]), "host", room["state"]["turn_id"], request_id, [operation], NOW)
    assert repeated["cursor"] == 1
    with pytest.raises(ValueError, match="画手"):
        repo.drawguess_strokes(UUID(room["room_id"]), "p1", room["state"]["turn_id"], uuid4(), [operation], NOW)
    invalid = {**operation, "stroke_id": "bad", "points": [[float("nan"), 0.2]]}
    with pytest.raises(ValueError, match="坐标"):
        repo.drawguess_strokes(UUID(room["room_id"]), "host", room["state"]["turn_id"], uuid4(), [invalid], NOW)
    too_many = {**operation, "stroke_id": "huge", "points": [[0.1, 0.1]] * 257}
    with pytest.raises(ValueError, match="256"):
        repo.drawguess_strokes(UUID(room["room_id"]), "host", room["state"]["turn_id"], uuid4(), [too_many], NOW)
    clear = repo.drawguess_strokes(UUID(room["room_id"]), "host", room["state"]["turn_id"], uuid4(), [{"op": "clear"}], NOW)
    assert clear["snapshot"]["canvas"] == []
    events = repo.drawguess_events(UUID(room["room_id"]), "p1", 0, NOW)
    assert events["reset"] is True
    assert events["cursor"] == 2
    assert events["snapshot"]["canvas"] == []
