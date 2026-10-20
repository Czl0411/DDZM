import asyncio
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from dzmm_bot.core.app import create_app
from dzmm_bot.core.club_api import mahjong_events
from tests.core.test_mahjong_repository import NOW, mahjong


def headers(uid):
    return {"Authorization": f"ClubUid {uid}"}


def test_create_list_claim_and_payload_validation(mahjong):
    repo, _ = mahjong
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    create = client.post(
        "/api/club/mahjong/rooms",
        headers=headers("host"),
        json={"request_id": str(uuid4()), "room_type": "casual", "match_mode": "east"},
    )
    assert create.status_code == 200
    room = create.json()
    assert room["code"].isdigit()
    listing = client.get("/api/club/mahjong/rooms", headers=headers("viewer"))
    assert listing.status_code == 200 and listing.headers["cache-control"] == "no-store"
    path = f"/api/club/mahjong/rooms/{room['id']}/actions"
    invalid = client.post(path, headers=headers("alice"), json={
        "version": 0,
        "request_id": str(uuid4()),
        "action": "claim",
        "payload": {"code": room["code"], "extra": True},
    })
    assert invalid.status_code == 422
    claimed = client.post(path, headers=headers("alice"), json={
        "version": 0,
        "request_id": str(uuid4()),
        "action": "claim",
        "payload": {"code": room["code"]},
    })
    assert claimed.status_code == 200 and claimed.json()["seat"] == 1


def test_uid_auth_and_chat_limits(mahjong):
    repo, _ = mahjong
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    assert client.get("/api/club/mahjong/rooms").status_code == 401
    assert client.get("/api/club/mahjong/rooms", headers=headers("nobody")).status_code == 409
    room = client.post("/api/club/mahjong/rooms", headers=headers("host"), json={
        "request_id": str(uuid4()), "room_type": "casual", "match_mode": "east",
    }).json()
    path = f"/api/club/mahjong/rooms/{room['id']}/chat"
    payload = {"request_id": str(uuid4()), "text": "约一桌吗？"}
    first = client.post(path, headers=headers("viewer"), json=payload)
    assert first.status_code == 200
    assert client.post(path, headers=headers("viewer"), json=payload).json() == first.json()
    assert client.post(path, headers=headers("viewer"), json={
        "request_id": str(uuid4()), "text": "太快了",
    }).status_code == 429


def test_sse_snapshot_is_recipient_scoped(mahjong):
    repo, _ = mahjong
    room = repo.create_mahjong_room(
        "host", NOW, room_type="casual", match_mode="east", request_id=uuid4(),
    )

    class Request:
        async def is_disconnected(self):
            return False

    async def first():
        stream = mahjong_events(repo, __import__("uuid").UUID(room["id"]), "viewer", lambda: NOW, Request())
        event = await anext(stream)
        await stream.aclose()
        return event

    event = asyncio.run(first())
    payload = json.loads(event.split("data: ", 1)[1])
    assert payload["seat"] is None


def test_daily_jobs_advance_mahjong_deadlines(mahjong, monkeypatch):
    repo, _ = mahjong
    advanced = []
    monkeypatch.setattr(repo, "advance_mahjong_deadlines", advanced.append)
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))

    response = client.post(
        "/internal/daily-jobs/run",
        headers={"X-Core-Token": "internal"},
        json={"now": NOW.isoformat()},
    )

    assert response.status_code == 200
    assert advanced == [NOW]
