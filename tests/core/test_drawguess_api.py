import asyncio
import json
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from dzmm_bot.core.app import create_app
from tests.core.test_drawguess_repository import NOW, create_room, game, started


def headers(uid):
    return {"Authorization": f"DrawguessUid {uid}"}


def test_auth_validation_projection_and_no_cache(game):
    repo = game[0]
    room = started(game)
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, drawguess_game_id="draw-card"))
    path = f"/api/drawguess/rooms/{room['room_id']}"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers("unknown")).status_code == 403
    response = client.get(path, headers=headers("p1"))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "answer" not in response.json()["state"]
    assert "candidates" not in response.json()["state"]
    assert client.get("/internal/status", headers=headers("p1")).status_code in {401, 403}
    preflight = client.options(path, headers={
        "Origin": "null", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert preflight.status_code == 200


def test_action_chat_and_stroke_payloads_are_strict(game):
    repo = game[0]
    room = started(game)
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, drawguess_game_id="draw-card"))
    base = f"/api/drawguess/rooms/{room['room_id']}"
    common = {"turn_id": room["state"]["turn_id"], "version": room["state"]["version"],
              "request_id": str(uuid4())}
    assert client.post(base + "/actions", headers=headers("host"), json={
        **common, "action": "choose", "payload": {"word_id": room["state"]["candidates"][0]["id"]},
        "extra": True,
    }).status_code == 422
    assert client.post(base + "/actions", headers=headers("host"), json={
        **common, "action": "choose", "payload": {"wrong": "x"},
    }).status_code == 422
    assert client.post(base + "/strokes", headers=headers("p1"), json={
        "turn_id": room["state"]["turn_id"], "request_id": str(uuid4()), "operations": [{"op": "clear"}],
    }).status_code == 409
    spectator_chat = client.post(base + "/chat", headers=headers("viewer"), json={
        "turn_id": room["state"]["turn_id"], "request_id": str(uuid4()), "text": "旁观发言",
    })
    assert spectator_chat.status_code == 200
    assert spectator_chat.json()["text"] == "旁观发言"
    listing = client.get("/api/drawguess/rooms", headers=headers("viewer"))
    assert listing.status_code == 200
    assert "answer" not in repr(listing.json())


def test_sse_snapshot_is_recipient_scoped_and_disconnects(game):
    from dzmm_bot.core.drawguess_api import room_events

    repo = game[0]
    room = started(game)

    class Request:
        disconnected = False

        async def is_disconnected(self):
            return self.disconnected

    async def first(uid):
        request = Request()
        stream = room_events(repo, UUID(room["room_id"]), uid, 0, lambda: NOW, request)
        event = await anext(stream)
        request.disconnected = True
        await stream.aclose()
        return json.loads(event.split("data: ", 1)[1])

    host = asyncio.run(first("host"))
    viewer = asyncio.run(first("viewer"))
    assert "candidates" in host["snapshot"]["state"]
    assert "candidates" not in viewer["snapshot"]["state"]


def test_chat_rate_limit_maps_to_429(game):
    repo = game[0]
    room = started(game)
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW + timedelta(seconds=1), drawguess_game_id="draw-card"))
    base = f"/api/drawguess/rooms/{room['room_id']}/chat"
    payload = {"turn_id": room["state"]["turn_id"], "request_id": str(uuid4()), "text": "先等等"}
    assert client.post(base, headers=headers("p1"), json=payload).status_code == 200
    payload["request_id"] = str(uuid4())
    assert client.post(base, headers=headers("p1"), json=payload).status_code == 429
