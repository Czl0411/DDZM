import base64
import json
from io import BytesIO
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from PIL import Image

from dzmm_bot.admin.app import create_app as create_admin_app
from dzmm_bot.admin.core_client import CoreClient
from dzmm_bot.admin.repository import AdminRepository
from dzmm_bot.core.app import create_app
from dzmm_bot.core.commands import GroupCommandHandler
from dzmm_bot.core.gamefy import GamefyIdentityVerifier, JWKS_URL
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, EquipmentItemRecord, GroupChatRecord, InboundRecord, OutboundRecord
from dzmm_bot.core.service import CoreService
from dzmm_bot.runtime.contracts import InboundMessage
from dzmm_bot.runtime.settings import Settings


GAME_ID = "3772306"
CORE_SECRET = "gamefy-test-core-only"
OWNER = str(uuid4())
VISITOR = str(uuid4())


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def signed_token(signing_key, **overrides):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": OWNER, "iss": "dzmm-gamefy", "aud": GAME_ID,
        "iat": now, "exp": now + timedelta(minutes=30), **overrides,
    }
    return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test-key"})


@pytest.fixture
def gamefy_keys(signing_key, monkeypatch):
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    public.update(kid="test-key", alg="RS256", use="sig")
    calls = []

    def fetch(opener, request, **kwargs):
        assert request.full_url == JWKS_URL
        assert request.get_header("User-agent") == "DDZM-Workstation/1.0"
        assert request.get_header("Accept") == "application/json"
        calls.append(request.full_url)
        return BytesIO(json.dumps({"keys": [public]}).encode())

    monkeypatch.setattr("urllib.request.OpenerDirector.open", fetch)
    return calls


def test_rs256_verification_uses_fixed_jwks_and_caches_public_keys(signing_key, gamefy_keys):
    verifier = GamefyIdentityVerifier(GAME_ID)
    token = signed_token(signing_key)
    assert verifier.verify(token) == OWNER
    assert verifier.verify(token) == OWNER
    assert gamefy_keys == [JWKS_URL]


def test_platform_uuid_game_audience_is_distinct_from_numeric_card_id(signing_key, gamefy_keys):
    game_id = str(uuid4())
    verifier = GamefyIdentityVerifier(game_id)
    assert verifier.verify(signed_token(signing_key, aud=game_id)) == OWNER
    for audience in [GAME_ID, str(uuid4())]:
        with pytest.raises(HTTPException) as error:
            verifier.verify(signed_token(signing_key, aud=audience))
        assert error.value.status_code == 401


@pytest.mark.parametrize("claims", [
    {"aud": "another-game"}, {"aud": [GAME_ID, "another-game"]},
    {"iss": "another-issuer"}, {"sub": "not-a-platform-uuid"}, {"sub": None},
    {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
    {"iat": datetime.now(timezone.utc) + timedelta(hours=1)},
    {"exp": None},
])
def test_rejects_invalid_or_cross_game_claims(signing_key, gamefy_keys, claims):
    with pytest.raises(HTTPException) as error:
        GamefyIdentityVerifier(GAME_ID).verify(signed_token(signing_key, **claims))
    assert error.value.status_code == 401


def test_rejects_wrong_signature_algorithm_and_unknown_key(signing_key, gamefy_keys):
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for token in [
        signed_token(wrong_key),
        jwt.encode({"sub": OWNER}, "test-symmetric-secret-at-least-thirty-two-bytes", algorithm="HS256", headers={"kid": "test-key"}),
        jwt.encode({"sub": OWNER}, signing_key, algorithm="RS256", headers={"kid": "unknown-key"}),
        "malformed-token",
    ]:
        with pytest.raises(HTTPException) as error:
            GamefyIdentityVerifier(GAME_ID).verify(token)
        assert error.value.status_code == 401


def test_jwks_outage_is_retryable_without_leaking_details(signing_key, monkeypatch):
    verifier = GamefyIdentityVerifier(GAME_ID)

    def unavailable(token):
        raise jwt.PyJWKClientConnectionError("private network diagnostics")

    monkeypatch.setattr(verifier.keys, "get_signing_key_from_jwt", unavailable)
    with pytest.raises(HTTPException) as error:
        verifier.verify(signed_token(signing_key))
    assert error.value.status_code == 503
    assert "private" not in error.value.detail


@pytest.mark.parametrize("identifier", ["", "0", "-1", "other", "３７７２３０６"])
def test_invalid_game_configuration_fails_closed(identifier):
    with pytest.raises(ValueError):
        GamefyIdentityVerifier(identifier)


def test_environment_reads_optional_game_id(monkeypatch, tmp_path):
    monkeypatch.setenv("DZMM_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("DZMM_CORE_TOKEN", CORE_SECRET)
    monkeypatch.setenv("DZMM_BROWSER_PROFILE", str(tmp_path))
    monkeypatch.delenv("DZMM_GAMEFY_GAME_ID", raising=False)
    assert Settings.from_environment().gamefy_game_id is None
    monkeypatch.setenv("DZMM_GAMEFY_GAME_ID", GAME_ID)
    assert Settings.from_environment().gamefy_game_id == GAME_ID


@pytest.fixture
def gamefy_context(gamefy_keys):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(factory)
    now = datetime.now(timezone.utc)
    repository.bootstrap_primary_group("https://www.aikda.com/chat?c=gamefy-test", now)
    service = CoreService(repository, GroupCommandHandler(repository))

    def send(identifier, text, sender=OWNER):
        service.receive_inbound(InboundMessage(
            identifier, sender, text, now, source_type="group", chatroom_id="gamefy-test",
        ))

    send("join-owner", "/入职 糯糯")
    send("join-visitor", "/入职 小小糯", VISITOR)
    owner = repository.find_user(OWNER)
    repository.record_balance_change(owner.id, 300 - owner.balance, "board_bonus", now)
    send("buy", "/购买装备 1")
    send("equip", "/装备 1")
    with TestClient(create_app(repository, CORE_SECRET, gamefy_game_id=GAME_ID)) as internal:
        with httpx.Client(base_url="http://core.test", headers={"X-Core-Token": CORE_SECRET}, transport=internal._transport) as transport:
            core = CoreClient("http://core.test", CORE_SECRET, client=transport)
            with TestClient(create_admin_app("admin-test-only", core, repository=AdminRepository(factory))) as public:
                yield SimpleNamespace(repository=repository, internal=internal, public=public, send=send)
    engine.dispose()


def test_game_reads_only_authenticated_players_equipped_items(gamefy_context, signing_key):
    context = gamefy_context
    path = "/api/gamefy/workstation"
    headers = {"Authorization": f"Bearer {signed_token(signing_key)}", "Origin": "null"}
    balance = context.repository.find_user(OWNER).balance
    response = context.public.get(path + f"?user_id={VISITOR}", headers=headers)
    assert response.status_code == 200
    assert response.json()["display_name"] == "糯糯"
    assert response.json()["equipped"][0]["asset_key"] == "monitor-main"
    assert response.json()["daily_income"] == 2
    assert response.json()["income_settlement_enabled"] is False
    assert response.json()["employee_number"] == "#0001"
    assert set(response.json()) == {"display_name", "employee_number", "share_groups", "equipped", "daily_income", "currency_name", "income_settlement_enabled"}
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["cache-control"] == "no-store"
    assert "access-control-allow-credentials" not in response.headers
    visitor = {"Authorization": f"Bearer {signed_token(signing_key, sub=VISITOR)}"}
    assert context.public.get(path, headers=visitor).json()["equipped"] == []
    context.send("remove", "/卸下 1")
    assert context.public.get(path, headers=headers).json()["equipped"] == []
    assert context.repository.find_user(OWNER).balance == balance
    assert CORE_SECRET not in response.text
    assert OWNER not in response.text


def test_sandbox_preflight_is_scoped_to_gamefy(gamefy_context):
    public = gamefy_context.public
    response = public.options("/api/gamefy/workstation", headers={
        "Origin": "null", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["access-control-allow-headers"] == "Authorization, Content-Type"
    assert "access-control-allow-origin" not in public.options("/api/status").headers


def test_authentication_and_read_only_access(gamefy_context, signing_key):
    context = gamefy_context
    path = "/api/gamefy/workstation"
    for authorization in [None, "Bearer invalid", f"Bearer {signed_token(signing_key, aud='wrong-game')}", "Bearer " + "a" * 8193]:
        headers = {} if authorization is None else {"Authorization": authorization}
        response = context.public.get(path, headers=headers)
        assert response.status_code == 401
        assert response.headers["access-control-allow-origin"] == "*"
    token = signed_token(signing_key)
    assert context.internal.get("/internal/gamefy/workstation", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert context.public.get(path, headers={"Authorization": f"Bearer {signed_token(signing_key, sub=str(uuid4()))}"}).status_code == 404
    assert context.public.post(path, headers={"Authorization": f"Bearer {token}"}, json={"equipped": [1]}).status_code == 405
    assert context.public.get("/api/status", headers={"X-Admin-Token": token}).status_code == 401


def test_lobby_lists_public_workstations_including_empty_and_searches_literally(gamefy_context, signing_key):
    context = gamefy_context
    headers = {"Authorization": f"Bearer {signed_token(signing_key)}"}
    path = "/api/gamefy/workstation/lobby"
    response = context.public.get(path, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2 and data["my_number"] == 1
    assert data["items"] == [
        {"number": 1, "employee_number": "#0001", "display_name": "糯糯",
         "asset_keys": ["monitor-main"], "equipped_count": 1, "daily_income": 2},
        {"number": 2, "employee_number": "#0002", "display_name": "小小糯",
         "asset_keys": [], "equipped_count": 0, "daily_income": 0},
    ]
    assert response.headers["cache-control"] == "no-store"
    for query in ["#0002", "0002", " 小小糯 "]:
        matches = context.public.get(path, headers=headers, params={"query": query}).json()
        assert [item["number"] for item in matches["items"]] == [2]
    for query in ["%", "_", "不存在", "9" * 64]:
        assert context.public.get(path, headers=headers, params={"query": query}).json()["items"] == []
    for private in [OWNER, VISITOR, CORE_SECRET, "balance", "birthday", "platform_id", "share_groups"]:
        assert private not in response.text
    assert context.public.get(path, headers=headers, params={"page": 2}).json()["items"] == []
    for params in [{"page": 0}, {"page": 1000001}, {"query": "a" * 65}]:
        assert context.public.get(path, headers=headers, params=params).status_code == 422


def test_lobby_pagination_is_stable_and_bounded(gamefy_context, signing_key):
    context = gamefy_context
    for number in range(3, 27):
        context.send(f"join-{number}", f"/入职 员工{number}", str(uuid4()))
    path = "/api/gamefy/workstation/lobby"
    headers = {"Authorization": f"Bearer {signed_token(signing_key)}"}
    first = context.public.get(path, headers=headers).json()
    second = context.public.get(path, params={"page": 2}, headers=headers).json()
    assert first["total"] == second["total"] == 26
    assert [item["number"] for item in first["items"]] == list(range(1, 25))
    assert [item["number"] for item in second["items"]] == [25, 26]


def test_employee_view_is_read_only_and_does_not_grant_others_share_access(gamefy_context, signing_key):
    context = gamefy_context
    headers = {"Authorization": f"Bearer {signed_token(signing_key)}"}
    context.send("entry", "/我的工位")
    own = context.public.get("/api/gamefy/workstation/employees/1", headers=headers).json()
    other = context.public.get("/api/gamefy/workstation/employees/2", headers=headers).json()
    assert own["is_owner"] is True and len(own["share_groups"]) == 1
    assert other["display_name"] == "小小糯" and other["is_owner"] is False
    assert other["equipped"] == [] and other["share_groups"] == []
    visitor_headers = {"Authorization": f"Bearer {signed_token(signing_key, sub=VISITOR)}"}
    visited = context.public.get("/api/gamefy/workstation/employees/1", headers=visitor_headers).json()
    assert visited["equipped"] == own["equipped"]
    assert visited["share_groups"] == [] and visited["is_owner"] is False
    assert context.public.get("/api/gamefy/workstation/employees/99999", headers=headers).status_code == 404
    for suffix in ["/lobby", "/employees/1", "/employees/1/image"]:
        path = "/api/gamefy/workstation" + suffix
        assert context.public.get(path).status_code == 401
        assert context.public.get(path, headers={"Authorization": "Bearer invalid"}).status_code == 401
        assert context.public.post(path, json={}, headers=headers).status_code == 405
        assert context.public.options(path).headers["access-control-allow-origin"] == "*"
    for suffix in ["/lobby", "/employees/1"]:
        assert context.internal.get("/internal/gamefy/workstation" + suffix, headers=headers).status_code == 401


def test_download_composes_trusted_equipment_without_enqueuing_messages(gamefy_context, signing_key):
    context = gamefy_context
    headers = {"Authorization": f"Bearer {signed_token(signing_key)}"}
    balance = context.repository.find_user(OWNER).balance
    with context.repository._session() as session:
        before = set(session.scalars(select(OutboundRecord.id)))
    prefix = "/api/gamefy/workstation/employees/"
    images = []
    for number in [1, 2]:
        response = context.public.get(prefix + f"{number}/image", headers=headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert set(response.json()) == {"data_url"}
        encoded = response.json()["data_url"].removeprefix("data:image/png;base64,")
        with Image.open(BytesIO(base64.b64decode(encoded))) as image:
            assert image.format == "PNG" and image.size == (1536, 1024)
            images.append(image.tobytes())
    assert images[0] != images[1]
    assert context.public.get(prefix + "99999/image", headers=headers).status_code == 404
    with context.repository._session() as session:
        assert set(session.scalars(select(OutboundRecord.id))) == before
    assert context.repository.find_user(OWNER).balance == balance


def test_unconfigured_game_does_not_accept_a_valid_platform_token(gamefy_context, signing_key):
    with TestClient(create_app(gamefy_context.repository, CORE_SECRET)) as client:
        response = client.get("/internal/gamefy/workstation", headers={
            "X-Core-Token": CORE_SECRET, "Authorization": f"Bearer {signed_token(signing_key)}",
        })
        assert response.status_code == 503


def test_share_requires_own_identity_recent_group_entry_and_is_idempotent(gamefy_context, signing_key):
    context = gamefy_context
    headers = {"Authorization": f"Bearer {signed_token(signing_key)}", "Origin": "null"}
    path = "/api/gamefy/workstation"
    assert context.public.get(path, headers=headers).json()["share_groups"] == []
    payload = {"group_id": str(uuid4()), "request_id": str(uuid4())}
    assert context.public.post(path + "/share", headers=headers, json=payload).status_code == 403
    assert context.public.post(path + "/share", json=payload).status_code == 401
    context.send("entry", "/我的工位")
    groups = context.public.get(path, headers=headers).json()["share_groups"]
    assert len(groups) == 1
    payload["group_id"] = groups[0]["id"]
    for number in range(2, 11):
        context.send(f"buy-{number}", f"/购买装备 {number}")
        context.send(f"equip-{number}", f"/装备 {number}")
    with context.repository._session() as session:
        item = session.scalar(select(EquipmentItemRecord).where(EquipmentItemRecord.public_number == 1))
        item.name = "测试装备" * 25
        previous_ids = set(session.scalars(select(OutboundRecord.id)))
    balance = context.repository.find_user(OWNER).balance
    first = context.public.post(path + "/share", headers=headers, json=payload)
    assert first.status_code == 200
    assert first.json()["status"] == "pending"
    assert first.headers["access-control-allow-origin"] == "*"
    assert context.public.post(path + "/share", headers=headers, json=payload).json() == first.json()
    with context.repository._session() as session:
        records = session.scalars(select(OutboundRecord).where(OutboundRecord.content_type == "workstation")).all()
        assert len(records) == 1
        assert len(set(session.scalars(select(OutboundRecord.id))) - previous_ids) == 1
        snapshot = json.loads(records[0].text)
        assert snapshot["display_name"] == "糯糯"
        assert snapshot["employee_number"] == "#0001"
        assert snapshot["equipped"][0]["asset_key"] == "monitor-main"
        assert len(snapshot["equipped"]) == 10
        assert len(records[0].text) > 1000
        assert records[0].destination_chatroom_id == "gamefy-test"
        assert records[0].group_chat_id == UUID(groups[0]["id"])
        records[0].status = "sent"
    status_path = path + "/shares/" + payload["request_id"]
    assert context.public.get(status_path, headers=headers).json()["status"] == "sent"
    visitor = {"Authorization": f"Bearer {signed_token(signing_key, sub=VISITOR)}"}
    assert context.public.get(status_path, headers=visitor).status_code == 404
    assert context.public.post(path + "/share", headers=visitor, json=payload).status_code == 403
    too_fast = context.public.post(path + "/share", headers=headers, json={**payload, "request_id": str(uuid4())})
    assert too_fast.status_code == 429
    assert context.repository.find_user(OWNER).balance == balance


def test_share_rejects_expired_disabled_and_forged_targets(gamefy_context, signing_key):
    context = gamefy_context
    headers = {"Authorization": f"Bearer {signed_token(signing_key)}"}
    path = "/api/gamefy/workstation"
    context.send("entry", "/我的工位")
    group_id = context.public.get(path, headers=headers).json()["share_groups"][0]["id"]
    payload = {"group_id": group_id, "request_id": str(uuid4())}
    for extra in [{"user_id": VISITOR}, {"image_url": "https://untrusted.test/photo.png"}, {"equipped": [1]}]:
        assert context.public.post(path + "/share", headers=headers, json={**payload, **extra}).status_code == 422
    assert context.internal.post("/internal/gamefy/workstation/share", headers=headers, json=payload).status_code == 401
    with context.repository._session() as session:
        entry = session.scalar(select(InboundRecord).where(InboundRecord.platform_message_id == "entry"))
        entry.received_at -= timedelta(hours=25)
    assert context.public.post(path + "/share", headers=headers, json=payload).status_code == 403
    context.send("new-entry", "/我的工位")
    with context.repository._session() as session:
        group = session.scalar(select(GroupChatRecord).where(GroupChatRecord.chatroom_id == "gamefy-test"))
        group.listening_enabled = False
    assert context.public.get(path, headers=headers).json()["share_groups"] == []
    assert context.public.post(path + "/share", headers=headers, json=payload).status_code == 403


def test_share_preflight_accepts_authorized_json_from_sandbox(gamefy_context):
    response = gamefy_context.public.options("/api/gamefy/workstation/share", headers={
        "Origin": "null", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]
    assert response.headers["access-control-allow-origin"] == "*"
