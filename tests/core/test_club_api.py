import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from dzmm_bot.core.app import create_app
from dzmm_bot.core.club_api import club_card_events, club_social_events, mahjong_events
from dzmm_bot.core.schema import (
    ClubCardHandRecord,
    ClubCardRoomRecord,
    ClubPlayerRecord,
    DoudizhuRoomRecord,
    DoudizhuRoundRecord,
    DrawguessRoomRecord,
    GameParticipationRecord,
    KingGameRecord,
    KingGameRoundRecord,
    MahjongRoomRecord,
    UserRecord,
)
from tests.core.test_mahjong_repository import NOW, mahjong, seated


def headers(uid):
    return {"Authorization": f"ClubUid {uid}"}


def test_public_club_economy_settings(mahjong):
    repo, _ = mahjong
    repo.set_club_game_economy_settings(
        "mahjong", coin_stakes=[10, 50], rake_percent=15
    )
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))

    response = client.get("/api/club/economy-settings")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert len(response.json()) == 8
    assert response.json()[0] == {
        "game": "mahjong", "coin_stakes": [10, 50], "rake_percent": 15,
    }


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
    assert "code" not in room
    listing = client.get("/api/club/mahjong/rooms", headers=headers("viewer"))
    assert listing.status_code == 200 and listing.headers["cache-control"] == "no-store"
    path = f"/api/club/mahjong/rooms/{room['id']}/actions"
    invalid = client.post(path, headers=headers("alice"), json={
        "version": 0,
        "request_id": str(uuid4()),
        "action": "claim",
        "payload": {"extra": True},
    })
    assert invalid.status_code == 422
    claimed = client.post(path, headers=headers("alice"), json={
        "version": 0,
        "request_id": str(uuid4()),
        "action": "claim",
        "payload": {},
    })
    assert claimed.status_code == 200 and claimed.json()["seat"] == 1


def test_reaction_version_passes_through_real_action_api(mahjong):
    repo, factory = mahjong
    room = seated(mahjong)
    with factory.begin() as session:
        record = session.get(MahjongRoomRecord, UUID(room["id"]))
        record.state = {
            **record.state,
            "hands": [[8], [0, 4, 12, 16], [9, 10], []],
        }
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    path = f"/api/club/mahjong/rooms/{room['id']}/actions"
    discarded = client.post(path, headers=headers("host"), json={
        "version": room["version"],
        "request_id": str(uuid4()),
        "action": "discard",
        "payload": {"tile": 8},
    }).json()
    reaction_version = discarded["game"]["reaction_version"]
    invalid = client.post(path, headers=headers("alice"), json={
        "version": discarded["version"],
        "request_id": str(uuid4()),
        "action": "chi",
        "payload": {"tiles": [4, 12], "reaction_version": True},
    })
    assert invalid.status_code == 422
    answered = client.post(path, headers=headers("alice"), json={
        "version": discarded["version"],
        "request_id": str(uuid4()),
        "action": "chi",
        "payload": {"tiles": [4, 12], "reaction_version": reaction_version},
    })
    assert answered.status_code == 200
    resolved = client.post(path, headers=headers("bob"), json={
        "version": discarded["version"],
        "request_id": str(uuid4()),
        "action": "pass",
        "payload": {"reaction_version": reaction_version},
    })
    assert resolved.status_code == 200
    assert resolved.json()["phase"] == "playing"
    assert resolved.json()["game"]["melds"][1][0]["tiles"] == [4, 8, 12]


def test_uid_auth_and_chat_limits(mahjong):
    repo, _ = mahjong
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    assert client.get("/api/club/mahjong/rooms").status_code == 401
    guest = client.get("/api/club/mahjong/rooms", headers=headers("nobody"))
    assert guest.status_code == 200
    assert client.post("/api/club/mahjong/rooms", headers=headers("nobody"), json={
        "request_id": str(uuid4()), "room_type": "coin", "stake": 10, "match_mode": "east",
    }).status_code == 409
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


def test_social_sse_pushes_public_channel_changes(mahjong):
    repo, _ = mahjong

    class Request:
        async def is_disconnected(self):
            return False

    async def check():
        stream = club_social_events(repo, "guest-b", lambda: NOW, Request())
        initial = json.loads((await anext(stream)).split("data: ", 1)[1])
        repo.send_club_public_message("guest-a", "实时消息", NOW)
        changed = json.loads((await asyncio.wait_for(anext(stream), 1)).split("data: ", 1)[1])
        await stream.aclose()
        return initial, changed

    initial, changed = asyncio.run(check())
    assert initial["channel"] == ""
    assert changed["channel"]


def test_card_sse_pushes_room_chat_changes(mahjong):
    repo, _ = mahjong
    room = repo.create_club_card_room(
        "texas", "host", NOW, room_type="casual", stake=0, request_id=uuid4(),
    )

    class Request:
        async def is_disconnected(self):
            return False

    async def check():
        stream = club_card_events(
            repo, "texas", __import__("uuid").UUID(room["id"]), "viewer", lambda: NOW, Request(),
        )
        await anext(stream)
        repo.club_card_chat("texas", __import__("uuid").UUID(room["id"]), "host", uuid4(), "来一局", NOW)
        event = await asyncio.wait_for(anext(stream), 1)
        await stream.aclose()
        return json.loads(event.split("data: ", 1)[1])

    changed = asyncio.run(check())
    assert changed["messages"][-1]["text"] == "来一局"


def test_daily_jobs_advance_every_club_game_deadline(mahjong, monkeypatch):
    repo, _ = mahjong
    mahjong_advanced = []
    card_advanced = []
    doudizhu_advanced = []
    drawguess_advanced = []
    monkeypatch.setattr(repo, "advance_mahjong_deadlines", mahjong_advanced.append)
    monkeypatch.setattr(repo, "advance_club_card_deadlines", card_advanced.append)
    monkeypatch.setattr(repo, "advance_doudizhu_deadlines", doudizhu_advanced.append)
    monkeypatch.setattr(repo, "advance_drawguess_deadlines", drawguess_advanced.append)
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))

    response = client.post(
        "/internal/daily-jobs/run",
        headers={"X-Core-Token": "internal"},
        json={"now": NOW.isoformat()},
    )

    assert response.status_code == 200
    assert mahjong_advanced == [NOW]
    assert card_advanced == [NOW]
    assert doudizhu_advanced == [NOW]
    assert drawguess_advanced == [NOW]


def test_guest_channel_friendship_and_direct_messages(mahjong):
    repo, _ = mahjong
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    first = client.post(
        "/api/club/session", headers=headers("guest-a"),
        json={"name": "路人甲", "avatar_url": "https://example.invalid/a.webp"},
    ).json()
    second = client.post(
        "/api/club/session", headers=headers("guest-b"), json={"name": "路人乙"},
    ).json()
    assert first["employee"] is False and second["employee"] is False
    initial_version = repo.club_social_version("guest-b", NOW)

    sent = client.post(
        "/api/club/channel", headers=headers("guest-a"),
        json={"request_id": str(uuid4()), "text": "有人开桌吗？"},
    )
    assert sent.status_code == 200
    assert client.get("/api/club/channel", headers=headers("guest-b")).json()[0]["text"] == "有人开桌吗？"
    channel_version = repo.club_social_version("guest-b", NOW)
    assert channel_version["channel"] != initial_version["channel"]

    request = client.post(
        "/api/club/friends", headers=headers("guest-a"), json={"player_id": second["id"]},
    )
    assert request.status_code == 200
    requested_version = repo.club_social_version("guest-b", NOW)
    assert requested_version["friends"] != channel_version["friends"]
    incoming = client.get("/api/club/friends", headers=headers("guest-b")).json()["incoming"][0]
    assert client.post(
        f"/api/club/friends/{incoming['request_id']}/accept", headers=headers("guest-b"),
    ).status_code == 200
    accepted_version = repo.club_social_version("guest-b", NOW)
    assert accepted_version["friends"] != requested_version["friends"]
    message = client.post(
        f"/api/club/friends/{second['id']}/messages", headers=headers("guest-a"),
        json={"request_id": str(uuid4()), "text": "来一局"},
    )
    assert message.status_code == 200
    assert repo.club_social_version("guest-b", NOW)["direct"]
    assert client.get(
        f"/api/club/friends/{first['id']}/messages", headers=headers("guest-b"),
    ).json()[0]["text"] == "来一局"
    profile = client.get(f"/api/club/players/{first['id']}", headers=headers("guest-b"))
    assert profile.status_code == 200
    assert profile.json()["avatar_url"] == "https://example.invalid/a.webp"
    assert profile.json()["relationship"] == "friend"


def test_card_modules_create_join_start_and_reconnect(mahjong):
    repo, _ = mahjong
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    for game in ("texas", "zhajinhua", "blackjack", "niuniu"):
        host = f"host-{game}"
        guest = f"alice-{game}"
        created = client.post(
            f"/api/club/cards/{game}/rooms", headers=headers(host),
            json={"request_id": str(uuid4()), "room_type": "casual", "stake": 0},
        )
        assert created.status_code == 200
        room = created.json()
        minimum = 2
        room = client.post(
            f"/api/club/cards/{game}/rooms/{room['id']}/actions", headers=headers(guest),
            json={"version": room["version"], "request_id": str(uuid4()), "action": "claim", "payload": {}},
        ).json()
        for uid in (host, guest)[:minimum]:
            room = client.post(
                f"/api/club/cards/{game}/rooms/{room['id']}/actions", headers=headers(uid),
                json={"version": room["version"], "request_id": str(uuid4()), "action": "ready", "payload": {}},
            ).json()
        started = client.post(
            f"/api/club/cards/{game}/rooms/{room['id']}/actions", headers=headers(host),
            json={"version": room["version"], "request_id": str(uuid4()), "action": "start", "payload": {}},
        )
        assert started.status_code == 200
        assert started.json()["phase"] in {"playing", "hand_finished"}
        reconnected = client.get(f"/api/club/cards/{game}/rooms/{room['id']}", headers=headers(host))
        assert reconnected.status_code == 200
        assert "deck" not in reconnected.json()["state"]


def test_active_room_endpoint_returns_the_players_card_table(mahjong):
    repo, _ = mahjong
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    room = client.post(
        "/api/club/cards/texas/rooms", headers=headers("host"),
        json={"request_id": str(uuid4()), "room_type": "casual", "stake": 0},
    ).json()

    active = client.get("/api/club/active-room", headers=headers("host"))

    assert active.status_code == 200
    assert active.json() == {
        "game": "texas", "room_id": room["id"], "phase": "waiting",
    }
    assert client.get("/api/club/active-room", headers=headers("viewer")).json() is None


def test_active_room_endpoint_covers_every_club_module(mahjong):
    repo, _ = mahjong
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    rooms = {
        "mahjong": repo.create_mahjong_room(
            "mahjong-host", NOW, room_type="casual", match_mode="east",
            request_id=uuid4(),
        )["id"],
        "chess": str(repo.create_chess_game("chess-host", now=NOW).id),
        "doudizhu": repo.create_doudizhu_room(
            "doudizhu-host", now=NOW, room_type="casual",
        )["id"],
        "drawguess": repo.create_drawguess_room(
            "drawguess-host", now=NOW, room_type="casual",
        )["room_id"],
    }

    for game, room_id in rooms.items():
        active = client.get(
            "/api/club/active-room", headers=headers(f"{game}-host"),
        )
        assert active.status_code == 200
        assert active.json()["game"] == game
        assert active.json()["room_id"] == room_id


def test_active_room_endpoint_recovers_only_recent_finished_seated_rooms(mahjong):
    repo, factory = mahjong
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    doudizhu = repo.create_doudizhu_room("doudizhu-host", now=NOW)
    drawguess = repo.create_drawguess_room("drawguess-host", now=NOW)

    with factory.begin() as session:
        ddz = session.get(DoudizhuRoomRecord, UUID(doudizhu["id"]))
        ddz.phase = "finished"
        ddz.settlement = {"settled_at": NOW.isoformat()}
        draw = session.get(DrawguessRoomRecord, UUID(drawguess["room_id"]))
        draw.phase = "finished"
        draw.state = {**draw.state, "phase": "finished"}
        draw.settlement = {"settled_at": NOW.isoformat()}

    assert client.get(
        "/api/club/active-room", headers=headers("doudizhu-host"),
    ).json() == {
        "game": "doudizhu", "room_id": doudizhu["id"], "phase": "finished",
    }
    assert client.get(
        "/api/club/active-room", headers=headers("drawguess-host"),
    ).json() == {
        "game": "drawguess", "room_id": drawguess["room_id"], "phase": "finished",
    }
    assert client.get(
        "/api/club/active-room", headers=headers("viewer"),
    ).json() is None


def test_active_room_endpoint_does_not_revive_old_or_unstamped_finished_rooms(mahjong):
    repo, factory = mahjong
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    old_doudizhu = repo.create_doudizhu_room("old-ddz-host", now=NOW)
    legacy_drawguess = repo.create_drawguess_room("legacy-draw-host", now=NOW)

    with factory.begin() as session:
        ddz = session.get(DoudizhuRoomRecord, UUID(old_doudizhu["id"]))
        ddz.phase = "finished"
        ddz.settlement = {"settled_at": (NOW - timedelta(hours=6, seconds=1)).isoformat()}
        draw = session.get(DrawguessRoomRecord, UUID(legacy_drawguess["room_id"]))
        draw.phase = "finished"
        draw.state = {**draw.state, "phase": "finished"}
        draw.settlement = {"winner_seats": [0]}

    assert client.get(
        "/api/club/active-room", headers=headers("old-ddz-host"),
    ).json() is None
    assert client.get(
        "/api/club/active-room", headers=headers("legacy-draw-host"),
    ).json() is None


@pytest.mark.parametrize("terminal_phase", ["hand_finished", "match_finished"])
def test_active_room_endpoint_preserves_recent_finished_mahjong(mahjong, terminal_phase):
    repo, factory = mahjong
    room = seated(mahjong)
    with factory.begin() as session:
        record = session.get(MahjongRoomRecord, UUID(room["id"]))
        state = dict(record.state)
        state.update(
            phase=terminal_phase,
            points=[25_000, 23_000, 27_000, 25_000],
            round_wind=27,
            hand_number=1,
            deadline=(NOW - timedelta(seconds=1)).isoformat(),
            next={"dealer_continues": False},
            result={
                "kind": "ron", "winners": [2], "loser": 1,
                "deltas": [0, -2000, 2000, 0],
                "dealer_continues": False,
            },
        )
        record.state = state
        record.phase = terminal_phase
        record.deadline = NOW - timedelta(seconds=1)

    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    assert client.get(
        "/api/club/active-room", headers=headers("host"),
    ).json() == {
        "game": "mahjong", "room_id": room["id"], "phase": terminal_phase,
    }
    assert all(
        item["id"] != room["id"]
        for item in client.get(
            "/api/club/mahjong/rooms", headers=headers("viewer"),
        ).json()
    )
    assert client.get(
        f"/api/club/room-status/mahjong/{room['id']}",
        headers=headers("viewer"),
    ).json()["enterable"] is False
    with factory() as session:
        record = session.get(MahjongRoomRecord, UUID(room["id"]))
        assert record.phase == terminal_phase
        assert record.deadline is None and record.settled
        assert record.ready == [False] * 4


def test_shared_room_status_covers_every_club_game_and_rejects_card_cross_game(mahjong):
    repo, factory = mahjong
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    rooms = {
        "mahjong": repo.create_mahjong_room(
            "mahjong-host", NOW, room_type="casual", match_mode="east", request_id=uuid4(),
        )["id"],
        "chess": str(repo.create_chess_game("chess-host", now=NOW).id),
        "doudizhu": repo.create_doudizhu_room("doudizhu-host", now=NOW)["id"],
        "drawguess": repo.create_drawguess_room("drawguess-host", now=NOW)["room_id"],
    }
    for game in ("texas", "zhajinhua", "blackjack", "niuniu"):
        rooms[game] = repo.create_club_card_room(
            game, f"card-host-{game}", NOW, room_type="casual", stake=0, request_id=uuid4(),
        )["id"]

    expected_capacities = {
        "mahjong": 4, "chess": 2, "doudizhu": 3, "drawguess": 8,
        "texas": 8, "zhajinhua": 6, "blackjack": 5, "niuniu": 6,
    }
    for game, room_id in rooms.items():
        response = client.get(
            f"/api/club/room-status/{game}/{room_id}", headers=headers("viewer"),
        )
        assert response.status_code == 200
        assert response.json() == {
            "game": game,
            "room_id": room_id,
            "state": "waiting",
            "label": "候场",
            "occupied": 1,
            "capacity": expected_capacities[game],
            "enterable": True,
        }

    wrong_game = client.get(
        f"/api/club/room-status/blackjack/{rooms['texas']}", headers=headers("viewer"),
    )
    assert wrong_game.status_code == 200
    assert wrong_game.json()["state"] == "dissolved"
    assert wrong_game.json()["enterable"] is False

    repo.ensure_club_player("alice", NOW)
    with factory.begin() as session:
        texas = session.get(ClubCardRoomRecord, __import__("uuid").UUID(rooms["texas"]))
        alice = session.scalar(select(ClubPlayerRecord).where(
            ClubPlayerRecord.platform_id == "alice"
        ))
        texas.phase = "playing"
        texas.seats = [*texas.seats, str(alice.id)]
    started = client.get(
        f"/api/club/room-status/texas/{rooms['texas']}", headers=headers("viewer"),
    ).json()
    assert started["state"] == "started"
    assert started["label"] == "已开始"
    assert started["occupied"] == 2


def test_presence_counts_recent_players_in_active_game_seats(mahjong):
    repo, factory = mahjong
    from dzmm_bot.core.schema import ClubPlayerRecord, DoudizhuRoomRecord

    room = repo.create_doudizhu_room("host", now=NOW)
    repo.ensure_club_player("alice", NOW)
    repo.ensure_club_player("stale", NOW - timedelta(seconds=31))
    with factory.begin() as session:
        host = session.scalar(select(ClubPlayerRecord).where(
            ClubPlayerRecord.platform_id == "host"
        ))
        alice = session.scalar(select(ClubPlayerRecord).where(
            ClubPlayerRecord.platform_id == "alice"
        ))
        active = session.get(DoudizhuRoomRecord, __import__("uuid").UUID(room["id"]))
        active.phase = "playing"
        active.seats = [str(host.id), str(alice.id), None]

    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    response = client.post("/api/club/presence", headers=headers("viewer"))

    assert response.status_code == 200
    assert response.json() == {"online": 3, "playing": 2}


def test_employee_can_claim_one_time_employment_task(mahjong):
    repo, _ = mahjong
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    before = client.get("/api/club/profile", headers=headers("host")).json()["balance"]
    task = next(item for item in client.get("/api/club/tasks", headers=headers("host")).json()
                if item["key"] == "employment")
    assert task["eligible"] is True and task["claimed"] is False
    claimed = client.post(
        "/api/club/tasks/claim", headers=headers("host"), json={"task_key": "employment"},
    )
    assert claimed.status_code == 200
    assert claimed.json()["balance"] == before + 20
    profile = client.get("/api/club/profile", headers=headers("host")).json()
    task_transaction = next(
        item for item in profile["recent_transactions"] if item["label"] == "任务奖励"
    )
    assert task_transaction["amount"] == 20
    assert client.post(
        "/api/club/tasks/claim", headers=headers("host"), json={"task_key": "employment"},
    ).status_code == 409


def test_guest_can_play_but_cannot_claim_employee_tasks(mahjong):
    repo, _ = mahjong
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    tasks = client.get("/api/club/tasks", headers=headers("guest-player")).json()
    assert all(item["eligible"] is False for item in tasks)
    assert client.post(
        "/api/club/tasks/claim",
        headers=headers("guest-player"),
        json={"task_key": "employment"},
    ).status_code == 409


def test_profile_aggregates_historical_results_for_every_player(mahjong):
    repo, factory = mahjong
    from dzmm_bot.core.schema import ChessGameRecord, ClubPlayerRecord

    for uid in ("host", "alice"):
        repo.ensure_club_player(uid, NOW)
    with factory.begin() as session:
        host = session.scalar(select(ClubPlayerRecord).where(ClubPlayerRecord.platform_id == "host"))
        alice = session.scalar(select(ClubPlayerRecord).where(ClubPlayerRecord.platform_id == "alice"))
        session.add(ChessGameRecord(
            group_chat_id=None,
            inbound_message_id=None,
            creator_user_id=host.id,
            opponent_user_id=alice.id,
            red_user_id=host.id,
            black_user_id=alice.id,
            code="",
            room_type="casual",
            stake=0,
            escrowed=[False, False],
            settled=True,
            settlement={"outcomes": {"red": "win", "black": "loss"}},
            status="finished",
            created_at=NOW,
            claim_deadline=NOW,
            red_remaining_ms=0,
            black_remaining_ms=0,
            version=1,
            result="red:checkmate",
            finished_at=NOW,
            events=[],
        ))

    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    host_stats = client.get("/api/club/profile", headers=headers("host")).json()["stats"]
    alice_stats = client.get("/api/club/profile", headers=headers("alice")).json()["stats"]
    assert host_stats["total"] == {"played": 1, "wins": 1, "losses": 0, "draws": 0}
    assert alice_stats["games"]["chess"] == {"played": 1, "wins": 0, "losses": 1, "draws": 0}


def test_employment_is_once_and_other_task_triggers_are_daily(mahjong):
    repo, factory = mahjong
    from dzmm_bot.core.schema import (
        ClubPlayerRecord,
        DailyCheckinRecord,
        DarkMarketListingRecord,
        DoudizhuRoomRecord,
        DoudizhuRoundRecord,
        InboundRecord,
        RandomEventParticipantRecord,
        UserRecord,
    )

    room = repo.create_doudizhu_room("host", now=NOW)
    with factory.begin() as session:
        user = session.scalar(select(UserRecord).where(UserRecord.platform_id == "host"))
        player = session.scalar(select(ClubPlayerRecord).where(ClubPlayerRecord.platform_id == "host"))
        room_id = __import__("uuid").UUID(room["id"])
        session.get(DoudizhuRoomRecord, room_id).round_number = 5
        completed_rounds = [
            DoudizhuRoundRecord(
                room_id=room_id,
                number=number,
                state={"phase": "finished", "events": [{"at": NOW.isoformat()}]},
            )
            for number in range(1, 5)
        ]
        unfinished_round = DoudizhuRoundRecord(
            room_id=room_id,
            number=5,
            state={"phase": "playing"},
        )
        session.add_all([*completed_rounds, unfinished_round])
        session.flush()
        unfinished_round_id = unfinished_round.id
        session.add(DailyCheckinRecord(
            user_id=user.id, checkin_date=NOW.date(), checked_in_at=NOW,
        ))
        session.add(RandomEventParticipantRecord(
            event_id=uuid4(), user_id=user.id, role="player", rounds=1, joined_at=NOW,
        ))
        session.add_all([
            InboundRecord(
                platform_message_id=f"task-message-{index}",
                sender_platform_id="host",
                content="这是一条用于活跃任务统计的群聊消息",
                content_type="text",
                received_at=NOW,
                status="processed",
                source_type="group",
                group_chat_id=None,
                created_at=NOW,
            )
            for index in range(20)
        ])
        session.add(DarkMarketListingRecord(
            public_number=9999,
            seller_user_id=user.id,
            announcement_group_id=uuid4(),
            name="测试商品",
            purpose="任务回归测试",
            details="已成功上架",
            gender="private",
            starting_price=1,
            duration_hours_snapshot=24,
            fee_percent_snapshot=5,
            state="active",
            ends_at=NOW + timedelta(days=1),
            created_at=NOW,
        ))
        assert player.user_id == user.id

    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    before_completion = client.get("/api/club/tasks", headers=headers("host")).json()
    assert next(item for item in before_completion if item["key"] == "five_rounds")["eligible"] is False
    with factory.begin() as session:
        session.get(DoudizhuRoundRecord, unfinished_round_id).state = {
            "phase": "finished", "events": [{"at": NOW.isoformat()}],
        }
    tasks = client.get("/api/club/tasks", headers=headers("host")).json()
    assert {item["key"] for item in tasks if item["eligible"]} == {
        "employment", "checkin", "random_event", "five_rounds", "activity", "dark_market",
    }
    assert next(item for item in tasks if item["key"] == "employment")["cadence"] == "once"
    assert all(item["cadence"] == "daily" for item in tasks if item["key"] != "employment")
    before = client.get("/api/club/profile", headers=headers("host")).json()["balance"]
    for task in tasks:
        response = client.post(
            "/api/club/tasks/claim",
            headers=headers("host"),
            json={"task_key": task["key"]},
        )
        assert response.status_code == 200
        duplicate = client.post(
            "/api/club/tasks/claim",
            headers=headers("host"),
            json={"task_key": task["key"]},
        )
        assert duplicate.status_code == 409
    assert client.get("/api/club/profile", headers=headers("host")).json()["balance"] == before + 36
    tomorrow = repo.club_tasks("host", NOW + timedelta(days=1))
    assert next(item for item in tomorrow if item["key"] == "employment")["claimed"] is True
    assert all(item["claimed"] is False for item in tomorrow if item["key"] != "employment")


def test_five_round_task_combines_card_hands_from_different_tables(mahjong):
    repo, factory = mahjong
    first = repo.create_club_card_room(
        "blackjack", "host", NOW, room_type="casual", stake=0,
        request_id=uuid4(),
    )
    second = repo.create_club_card_room(
        "blackjack", "alice", NOW, room_type="casual", stake=0,
        request_id=uuid4(),
    )
    with factory.begin() as session:
        host = session.scalar(select(ClubPlayerRecord).where(
            ClubPlayerRecord.platform_id == "host"
        ))
        for room_id, count in ((first["id"], 4), (second["id"], 1)):
            session.add_all(ClubCardHandRecord(
                room_id=UUID(room_id), game="blackjack", hand_number=number,
                players=[str(host.id)], outcomes={}, payouts={}, created_at=NOW,
            ) for number in range(1, count + 1))

    task = next(
        item for item in repo.club_tasks("host", NOW)
        if item["key"] == "five_rounds"
    )
    assert task["eligible"] is True


def test_five_round_task_counts_doudizhu_by_completion_day_across_midnight(mahjong):
    repo, factory = mahjong
    created_at = datetime(2026, 10, 20, 15, 59, tzinfo=timezone.utc)
    completed_at = datetime(2026, 10, 20, 16, 1, tzinfo=timezone.utc)
    room = repo.create_doudizhu_room("host", now=created_at)
    with factory.begin() as session:
        session.add_all(
            DoudizhuRoundRecord(
                room_id=UUID(room["id"]),
                number=number,
                state={
                    "phase": "finished",
                    "events": [{"at": completed_at.isoformat()}],
                },
            )
            for number in range(1, 6)
        )

    previous_day = next(
        item for item in repo.club_tasks("host", created_at)
        if item["key"] == "five_rounds"
    )
    completion_day = next(
        item for item in repo.club_tasks("host", completed_at)
        if item["key"] == "five_rounds"
    )
    assert previous_day["eligible"] is False
    assert completion_day["eligible"] is True


def test_five_round_task_counts_old_drawguess_room_turns_on_actual_day(mahjong):
    repo, factory = mahjong
    created_at = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    day_start = datetime(2026, 10, 20, 16, 0, tzinfo=timezone.utc)
    player = repo.ensure_club_player("host", created_at)
    old_turns = [created_at + timedelta(minutes=index) for index in range(5)]
    today_turns = [day_start + timedelta(minutes=index + 1) for index in range(4)]
    room_id = uuid4()
    with factory.begin() as session:
        session.add(DrawguessRoomRecord(
            id=room_id,
            creator_id=UUID(player["id"]),
            short_id="old-draw-room",
            active_code=None,
            room_type="casual",
            stake=0,
            escrowed=[],
            settled=False,
            settlement=None,
            state={
                "phase": "drawing",
                "seats": [player["id"]],
                "turn_index": 9,
                "completed_turns_ms": [
                    int(value.timestamp() * 1000)
                    for value in [*old_turns, *today_turns]
                ],
            },
            cursor=0,
            phase="drawing",
            created_at=created_at,
            deadline=None,
        ))

    before_fifth = next(
        item for item in repo.club_tasks("host", today_turns[-1])
        if item["key"] == "five_rounds"
    )
    assert before_fifth["eligible"] is False

    fifth_turn = day_start + timedelta(minutes=5)
    with factory.begin() as session:
        row = session.get(DrawguessRoomRecord, room_id)
        row.state = {
            **row.state,
            "turn_index": 10,
            "completed_turns_ms": [
                *row.state["completed_turns_ms"],
                int(fifth_turn.timestamp() * 1000),
            ],
        }
    after_fifth = next(
        item for item in repo.club_tasks("host", fifth_turn)
        if item["key"] == "five_rounds"
    )
    assert after_fifth["eligible"] is True


def test_five_round_task_combines_club_and_king_game_rounds(mahjong):
    repo, factory = mahjong
    group = repo.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=club-task", NOW
    )
    room = repo.create_club_card_room(
        "blackjack", "host", NOW, room_type="casual", stake=0,
        request_id=uuid4(),
    )
    with factory.begin() as session:
        host_player = session.scalar(select(ClubPlayerRecord).where(
            ClubPlayerRecord.platform_id == "host"
        ))
        host_user = session.scalar(select(UserRecord).where(
            UserRecord.platform_id == "host"
        ))
        session.add_all(ClubCardHandRecord(
            room_id=UUID(room["id"]), game="blackjack", hand_number=number,
            players=[str(host_player.id)], outcomes={}, payouts={},
            created_at=NOW,
        ) for number in range(1, 4))
        game = KingGameRecord(
            group_chat_id=group.id, host_user_id=host_user.id, active_key=None,
            state="completed", round_number=2, current_king_user_id=None,
            signup_deadline=None, king_phase_deadline=None,
            end_after_round=False, created_at=NOW, started_at=NOW,
            finished_at=NOW, finish_reason="participant_ended",
        )
        session.add(game)
        session.flush()
        session.add_all(KingGameRoundRecord(
            game_id=game.id, sequence=sequence, king_user_id=host_user.id,
            number_map={str(host_user.id): 1}, revealed_numbers=[1],
            state="revealed", started_at=NOW, revealed_at=NOW,
        ) for sequence in (1, 2))

    task = next(
        item for item in repo.club_tasks("host", NOW)
        if item["key"] == "five_rounds"
    )
    assert task["eligible"] is True


def test_five_round_task_counts_completed_group_game_sessions(mahjong):
    repo, factory = mahjong
    group = repo.bootstrap_primary_group(
        "https://www.aikda.com/chat?c=club-task", NOW
    )
    repo.ensure_club_player("host", NOW)
    with factory.begin() as session:
        host = session.scalar(select(UserRecord).where(
            UserRecord.platform_id == "host"
        ))
        session.add_all(GameParticipationRecord(
            game_type=game_type, game_id=uuid4(), user_id=host.id,
            group_chat_id=group.id, completed_at=NOW,
        ) for game_type in (
            "hide_and_seek", "undercover", "blame_bomb", "texas_holdem",
            "hide_and_seek",
        ))

    task = next(
        item for item in repo.club_tasks("host", NOW)
        if item["key"] == "five_rounds"
    )
    assert task["eligible"] is True
