from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.app import create_app
from dzmm_bot.core.chess_auth import verify_gamefy_token
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, InboundRecord, OutboundRecord, PRIMARY_GROUP_CHAT_ID


NOW = datetime(2026, 10, 13, 12, tzinfo=ZoneInfo("Asia/Shanghai"))


@pytest.fixture
def keys(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(public, as_dict=True)
    jwk.update(kid="test-key", use="sig", alg="RS256")

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, token):
            return type("Key", (), {"key": public})()

    monkeypatch.setattr("dzmm_bot.core.chess_auth.jwks_client", FakeJwksClient())

    def token(sub="creator", aud="test-game", exp=None, issuer="dzmm-gamefy"):
        return jwt.encode({"sub": sub, "aud": aud, "iss": issuer, "iat": datetime.now(timezone.utc), "exp": exp or datetime.now(timezone.utc) + timedelta(minutes=30)}, private, algorithm="RS256", headers={"kid": "test-key"})

    return token


def test_gamefy_token_signature_claims_and_expiry(keys):
    assert verify_gamefy_token(keys(), "test-game") == "creator"
    with pytest.raises(ValueError):
        verify_gamefy_token(keys(aud="wrong"), "test-game")
    with pytest.raises(ValueError):
        verify_gamefy_token(keys(issuer="wrong"), "test-game")
    with pytest.raises(ValueError):
        verify_gamefy_token(keys(exp=datetime.now(timezone.utc) - timedelta(minutes=1)), "test-game")


@pytest.fixture
def api(tmp_path, keys):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'api.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repo = CoreRepository(factory)
    repo.bootstrap_primary_group("https://www.aikda.com/chat?c=chess", NOW)
    for pid in ("creator", "opponent", "spectator"):
        repo.create_user(pid, pid, NOW, 0)
    inbound_id = uuid4()
    with factory.begin() as session:
        session.add(InboundRecord(id=inbound_id, platform_message_id="start", sender_platform_id="creator", content="/象棋", received_at=NOW, group_chat_id=PRIMARY_GROUP_CHAT_ID, chatroom_id="chess"))
        session.add(OutboundRecord(inbound_message_id=inbound_id, group_chat_id=PRIMARY_GROUP_CHAT_ID, text="link", status="sent"))
    game = repo.create_chess_game("creator", PRIMARY_GROUP_CHAT_ID, inbound_id, NOW)
    client = TestClient(create_app(repo, "core", clock=lambda: NOW, chess_game_id="test-game"))
    return client, repo, game, keys


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_api_requires_joined_identity_and_protects_code(api):
    client, _, game, token = api
    path = f"/api/chess/{game.id}"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers(token("stranger"))).status_code == 403
    res = client.get(path, headers=headers(token("spectator")))
    assert res.status_code == 200
    assert "code" not in res.json()["game"]
    assert res.json()["role"] == "spectator"
    assert client.post(path + "/moves", headers=headers(token("spectator")), json={"from_xy": [0, 6], "to_xy": [0, 5], "version": 1}).status_code == 422


def test_claim_chat_rate_limit_and_invalid_input(api):
    client, repo, game, token = api
    path = f"/api/chess/{game.id}"
    assert client.post(path + "/claim", headers=headers(token("opponent")), json={"code": game.code}).status_code == 200
    assert client.post(path + "/chat", headers=headers(token("spectator")), json={"text": "你好"}).status_code == 200
    assert client.post(path + "/chat", headers=headers(token("spectator")), json={"text": "刷屏"}).status_code == 429
    assert client.post(path + "/chat", headers=headers(token("spectator")), json={"text": "x" * 301}).status_code == 422
    assert client.post(path + "/moves", headers=headers(token("spectator")), json={"bad": 1}).status_code == 422
    assert repo.get_chess_game(game.id).version == 1
