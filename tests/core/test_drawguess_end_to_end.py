from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from dzmm_bot.core.app import create_app
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import (
    BalanceTransactionRecord, DrawguessMessageRecord, DrawguessRequestRecord, UserRecord,
)
from tests.core.test_drawguess_repository import NOW, create_room, game


def _headers(uid):
    return {"Authorization": f"DrawguessUid {uid}"}


def test_three_players_six_turns_and_restart(game):
    repo, factory, _ = game
    room = create_room(game)
    now = [NOW]

    def client_for(repository):
        return TestClient(create_app(
            repository, "internal", clock=lambda: now[0], drawguess_game_id="draw-card",
        ))

    client = client_for(repo)
    room_id = room["room_id"]

    def snapshot(uid):
        response = client.get(f"/api/drawguess/rooms/{room_id}", headers=_headers(uid))
        assert response.status_code == 200, response.text
        return response.json()

    def action(uid, kind, payload=None):
        current = snapshot(uid)
        response = client.post(
            f"/api/drawguess/rooms/{room_id}/actions",
            headers=_headers(uid),
            json={
                "turn_id": current["state"]["turn_id"],
                "version": current["state"]["version"],
                "request_id": str(uuid4()),
                "action": kind,
                "payload": payload or {},
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    def chat(uid, text, request_id=None):
        current = snapshot(uid)
        response = client.post(
            f"/api/drawguess/rooms/{room_id}/chat",
            headers=_headers(uid),
            json={
                "turn_id": current["state"]["turn_id"],
                "request_id": request_id or str(uuid4()),
                "text": text,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    with factory() as session:
        balances_before = dict(session.execute(select(UserRecord.platform_id, UserRecord.balance)).all())
        transactions_before = session.scalar(select(func.count()).select_from(BalanceTransactionRecord))

    for uid in ("p1", "p2"):
        action(uid, "claim", {"code": room["code"]})
    for uid in ("host", "p1", "p2"):
        action(uid, "ready")
    action("host", "start")

    blocked = client.post(
        f"/api/drawguess/rooms/{room_id}/actions",
        headers=_headers("viewer"),
        json={
            "turn_id": snapshot("viewer")["state"]["turn_id"],
            "version": snapshot("viewer")["state"]["version"],
            "request_id": str(uuid4()),
            "action": "ready",
            "payload": {},
        },
    )
    assert blocked.status_code == 409

    players = ("host", "p1", "p2")
    for turn in range(6):
        drawer = players[turn % 3]
        drawer_view = snapshot(drawer)
        assert drawer_view["state"]["phase"] == "selecting"
        chosen = drawer_view["state"]["candidates"][0]
        now[0] += timedelta(seconds=1)
        action(drawer, "choose", {"word_id": chosen["id"]})

        spectator_view = snapshot("viewer")
        assert chosen["answer"] not in repr(spectator_view)
        if turn == 2:
            now[0] += timedelta(seconds=90)
            assert snapshot("p1")["state"]["phase"] == "revealing"
            now[0] += timedelta(seconds=5)
            snapshot("p1")
        else:
            guessers = [uid for uid in players if uid != drawer]
            if turn == 0:
                now[0] += timedelta(seconds=1)
                assert chat("p1", "这不是答案")["text"] == "这不是答案"
                correct_request_id = str(uuid4())
                assert chat("p2", chosen["answer"], correct_request_id)["text"] == "已猜中 +99分"
                changed_retry = client.post(
                    f"/api/drawguess/rooms/{room_id}/chat",
                    headers=_headers("p2"),
                    json={
                        "turn_id": snapshot("p2")["state"]["turn_id"],
                        "request_id": correct_request_id,
                        "text": "修改后的重复请求",
                    },
                )
                assert changed_retry.status_code == 409
                assert chat("p2", chosen["answer"], correct_request_id)["text"] == "已猜中 +99分"
                now[0] += timedelta(seconds=1)
                assert chat("p1", chosen["answer"])["text"] == "已猜中 +98分"
            else:
                now[0] += timedelta(seconds=1)
                for uid in guessers:
                    assert chat(uid, chosen["answer"])["text"] == "已猜中 +99分"
            assert snapshot("viewer")["state"]["phase"] == "revealing"
            now[0] += timedelta(seconds=5)
            snapshot("viewer")

        if turn == 2:
            repo = CoreRepository(factory)
            client.close()
            client = client_for(repo)
            assert snapshot("host")["state"]["turn_index"] == 3

    final = snapshot("host")
    assert final["state"]["phase"] == "finished"
    assert final["state"]["ranking"] == [
        {"name": "p2", "score": 436, "rank": 1},
        {"name": "host", "score": 377, "rank": 2},
        {"name": "p1", "score": 376, "rank": 3},
    ]

    with factory() as session:
        balances_after = dict(session.execute(select(UserRecord.platform_id, UserRecord.balance)).all())
        transactions_after = session.scalar(select(func.count()).select_from(BalanceTransactionRecord))
        request_turns = set(session.scalars(select(DrawguessRequestRecord.turn_id)))
        message_turns = set(session.scalars(select(DrawguessMessageRecord.turn_id)))
    assert balances_after == balances_before
    assert transactions_after == transactions_before
    assert request_turns == {final["state"]["turn_id"]}
    assert message_turns == {final["state"]["turn_id"]}
    client.close()
