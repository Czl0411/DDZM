from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.mistrealm_api import mistrealm_router
from dzmm_bot.core.mistrealm_classic_cards import STARTER_DECKS
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, MistrealmRoomRecord


NOW = datetime(2026, 10, 15, 6, tzinfo=timezone.utc)
PREFIX = "/api/mistrealm"


def headers(uid):
    return {"Authorization": f"MistrealmUid {uid}"}


@pytest.fixture
def game(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'mistrealm-story.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(factory)
    app = FastAPI()
    app.include_router(mistrealm_router(repository, lambda: NOW))
    client = TestClient(app)
    for uid in ("a", "b"):
        assert client.post(
            PREFIX + "/players/me",
            headers=headers(uid),
            json={"name": f"玩家{uid}"},
        ).status_code == 200
    deck = deepcopy(STARTER_DECKS[0])
    saved = client.post(PREFIX + "/classic/decks", headers=headers("a"), json=deck)
    assert saved.status_code == 200
    return client, repository, factory, saved.json()


def test_story_starts_with_server_ai_and_locked_chapters(game):
    client, _, _, deck = game
    progress = client.get(PREFIX + "/classic/story", headers=headers("a")).json()
    assert progress["unlocked"] == 1
    assert progress["chapters"][0]["title"] == "雾门初启"
    locked = client.post(
        PREFIX + "/classic/story/start",
        headers=headers("a"),
        json={"chapter": 2, "deck_id": deck["id"]},
    )
    assert locked.status_code == 403

    response = client.post(
        PREFIX + "/classic/story/start",
        headers=headers("a"),
        json={"chapter": 1, "deck_id": deck["id"]},
    )
    assert response.status_code == 200, response.text
    room = response.json()
    assert room["code"] is None
    assert room["match_id"]
    assert room["state"]["mode"] == "story"
    assert room["state"]["story"]["chapter"] == 1
    assert room["state"]["players"][1]["name"] == "守门人·洛恩"
    assert room["state"]["players"][1].get("hand") is None
    assert room["state"]["phase"] in ("choose_first", "mulligan", "playing")


def test_story_ai_resolves_until_human_can_act_and_records_win(game):
    client, _, factory, deck = game
    room = client.post(
        PREFIX + "/classic/story/start",
        headers=headers("a"),
        json={"chapter": 1, "deck_id": deck["id"]},
    ).json()
    state = room["state"]
    if state["phase"] == "mulligan":
        response = client.post(
            f"{PREFIX}/classic/rooms/{room['room_id']}/actions",
            headers=headers("a"),
            json={
                "request_id": str(uuid4()),
                "match_id": room["match_id"],
                "version": state["version"],
                "action": "mulligan",
                "payload": {"cards": []},
            },
        )
        assert response.status_code == 200, response.text
        state = response.json()["state"]
    assert state["phase"] != "playing" or state["turn"] == 0 or state.get("pending", {}).get("actor") == 0
    if state["phase"] == "playing":
        assert state["deadline_ms"] is None

    with factory.begin() as session:
        record = session.get(MistrealmRoomRecord, UUID(room["room_id"]))
        changed = deepcopy(record.state)
        changed.update(phase="finished", winner=0, deadline_ms=None)
        record.state = changed
        record.phase = "finished"
    snapshot = client.get(
        f"{PREFIX}/classic/rooms/{room['room_id']}", headers=headers("a")
    )
    assert snapshot.status_code == 200
    progress = client.get(PREFIX + "/classic/story", headers=headers("a")).json()
    assert progress["completed"] == [1]
    assert progress["unlocked"] == 2


def test_channel_text_and_challenge_status(game):
    client, _, _, deck = game
    posted = client.post(
        PREFIX + "/channel/messages",
        headers=headers("a"),
        json={"text": "  有人来一局吗？  "},
    )
    assert posted.status_code == 200
    assert posted.json()["text"] == "有人来一局吗？"
    assert posted.json()["player"]["name"] == "玩家a"

    room = client.post(
        PREFIX + "/classic/rooms",
        headers=headers("a"),
        json={"deck_id": deck["id"], "request_id": str(uuid4())},
    ).json()
    challenge = client.post(
        PREFIX + "/channel/challenges",
        headers=headers("a"),
        json={"room_id": room["room_id"]},
    )
    assert challenge.status_code == 200, challenge.text
    assert challenge.json()["challenge"] == {
        "room_id": room["room_id"],
        "status": "waiting",
        "code": room["code"],
    }
    duplicate = client.post(
        PREFIX + "/channel/challenges",
        headers=headers("a"),
        json={"room_id": room["room_id"]},
    )
    assert duplicate.json()["id"] == challenge.json()["id"]
    listed = client.get(PREFIX + "/channel/messages", headers=headers("b")).json()
    assert sorted(item["kind"] for item in listed["items"]) == ["challenge", "text"]


def test_channel_mute_and_rate_limit(game):
    client, _, factory, _ = game
    from dzmm_bot.core.schema import MistrealmPlayerRecord
    from sqlalchemy import select

    with factory.begin() as session:
        player = session.scalar(
            select(MistrealmPlayerRecord).where(MistrealmPlayerRecord.platform_uid == "a")
        )
        player.channel_muted_until = NOW + timedelta(hours=1)
    muted = client.post(
        PREFIX + "/channel/messages", headers=headers("a"), json={"text": "测试"}
    )
    assert muted.status_code == 403
    assert "禁言" in muted.text
