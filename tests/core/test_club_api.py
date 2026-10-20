import asyncio
import json
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

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

    sent = client.post(
        "/api/club/channel", headers=headers("guest-a"),
        json={"request_id": str(uuid4()), "text": "有人开桌吗？"},
    )
    assert sent.status_code == 200
    assert client.get("/api/club/channel", headers=headers("guest-b")).json()[0]["text"] == "有人开桌吗？"

    request = client.post(
        "/api/club/friends", headers=headers("guest-a"), json={"player_id": second["id"]},
    )
    assert request.status_code == 200
    incoming = client.get("/api/club/friends", headers=headers("guest-b")).json()["incoming"][0]
    assert client.post(
        f"/api/club/friends/{incoming['request_id']}/accept", headers=headers("guest-b"),
    ).status_code == 200
    message = client.post(
        f"/api/club/friends/{second['id']}/messages", headers=headers("guest-a"),
        json={"request_id": str(uuid4()), "text": "来一局"},
    )
    assert message.status_code == 200
    assert client.get(
        f"/api/club/friends/{first['id']}/messages", headers=headers("guest-b"),
    ).json()[0]["text"] == "来一局"


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


def test_all_one_time_task_triggers_are_claimable_once(mahjong):
    repo, factory = mahjong
    from dzmm_bot.core.schema import (
        ClubPlayerRecord,
        DailyCheckinRecord,
        DarkMarketListingRecord,
        DoudizhuRoomRecord,
        InboundRecord,
        RandomEventParticipantRecord,
        UserRecord,
    )

    room = repo.create_doudizhu_room("host", now=NOW)
    with factory.begin() as session:
        user = session.scalar(select(UserRecord).where(UserRecord.platform_id == "host"))
        player = session.scalar(select(ClubPlayerRecord).where(ClubPlayerRecord.platform_id == "host"))
        session.get(DoudizhuRoomRecord, __import__("uuid").UUID(room["id"])).round_number = 5
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
    tasks = client.get("/api/club/tasks", headers=headers("host")).json()
    assert {item["key"] for item in tasks if item["eligible"]} == {
        "employment", "checkin", "random_event", "five_rounds", "activity", "dark_market",
    }
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
