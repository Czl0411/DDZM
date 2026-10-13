from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.app import create_app
from dzmm_bot.core.commands import GroupCommandHandler
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, ChessGameRecord, OutboundRecord
from dzmm_bot.core.service import CoreService
from dzmm_bot.runtime.contracts import InboundMessage


NOW = datetime(2026, 10, 13, 12, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_bot_to_gamefy_two_rooms_spectator_reconnect_and_final_notice(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'flow.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repo = CoreRepository(factory)
    repo.bootstrap_primary_group("https://www.aikda.com/chat?c=chess", NOW)
    for pid in ("creator", "opponent", "spectator"):
        repo.create_user(pid, pid, NOW, 0)

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        "dzmm_bot.core.chess_auth.jwks_client",
        type("Jwks", (), {"get_signing_key_from_jwt": lambda self, token: type("Key", (), {"key": private.public_key()})()})(),
    )

    def header(pid):
        token = jwt.encode({
            "sub": pid, "aud": "chess-game", "iss": "dzmm-gamefy",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        }, private, algorithm="RS256", headers={"kid": "test"})
        return {"Authorization": f"Bearer {token}"}

    clock = [NOW]
    service = CoreService(repo, GroupCommandHandler(
        repo, chess_game_id="chess-game",
        chess_game_url="https://www.aikda.com/chat?card=chess-card",
        chess_public_api_url="https://chess.example.com",
    ))
    client = TestClient(create_app(repo, "core", clock=lambda: clock[0], chess_game_id="chess-game"))
    for number in (1, 2):
        service.receive_inbound(InboundMessage(
            f"chess-e2e-{number}", "creator", "/象棋", NOW + timedelta(seconds=number),
            source_type="group", chatroom_id="chess",
        ))
    with factory.begin() as session:
        games = session.scalars(select(ChessGameRecord).order_by(ChessGameRecord.created_at)).all()
        replies = session.scalars(select(OutboundRecord).order_by(OutboundRecord.created_at)).all()
        assert len(games) == 2 and len(replies) == 2
        ids = [game.id for game in games]
        codes = [game.code for game in games]
        for game, reply in zip(games, replies):
            assert str(game.id) in parse_qs(urlsplit(reply.text.splitlines()[1]).query)["gp"][0]
            reply.status = "sent"

    first = f"/api/chess/{ids[0]}"
    second = f"/api/chess/{ids[1]}"
    clock[0] = NOW + timedelta(seconds=3)
    assert client.post(first + "/claim", headers=header("opponent"), json={"code": codes[0]}).status_code == 200
    assert client.post(second + "/claim", headers=header("opponent"), json={"code": codes[1]}).status_code == 200
    a = client.get(first, headers=header("creator")).json()
    b = client.get(second, headers=header("creator")).json()
    assert a["game"]["version"] == b["game"]["version"] == 1
    assert client.get(first, headers=header("spectator")).json()["role"] == "spectator"
    assert client.post(first + "/moves", headers=header("spectator"), json={"from_xy": [0, 6], "to_xy": [0, 5], "version": 1}).status_code == 422
    clock[0] += timedelta(seconds=2)
    red = repo.get_chess_game(ids[0]).red_platform_id
    move = client.post(first + "/moves", headers=header(red), json={"from_xy": [0, 6], "to_xy": [0, 5], "version": 1})
    assert move.status_code == 200
    assert client.post(first + "/chat", headers=header("spectator"), json={"text": "好棋"}).status_code == 200
    assert client.get(first, headers=header("creator")).json()["game"]["version"] == 2
    assert client.get(second, headers=header("creator")).json()["game"]["version"] == 1
    assert client.get(first, headers=header("opponent")).json()["messages"][0]["text"] == "好棋"
    ended = client.post(first + "/actions", headers=header(red), json={"action": "resign"})
    assert ended.status_code == 200 and ended.json()["game"]["status"] == "finished"
    assert client.get(first, headers=header("spectator")).json()["messages"] == []
    assert client.post(first + "/chat", headers=header("spectator"), json={"text": "赛后"}).status_code == 422
    assert repo.advance_chess_deadlines(clock[0] + timedelta(minutes=1)) == 1  # only the second room times out
    with factory() as session:
        notices = session.scalars(select(OutboundRecord).where(OutboundRecord.inbound_message_id.is_(None))).all()
    assert len(notices) == 2
