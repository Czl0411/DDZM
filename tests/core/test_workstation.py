from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from dzmm_bot.admin.app import create_app as create_admin_app
from dzmm_bot.admin.core_client import CoreClient
from dzmm_bot.admin.repository import AdminRepository
from dzmm_bot.core.app import create_app
from dzmm_bot.core.commands import GroupCommandHandler
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import (
    Base, EquipmentItemRecord, EquipmentOwnershipRecord, EquipmentPurchaseRecord,
    OutboundRecord,
)
from dzmm_bot.core.service import CoreService
from dzmm_bot.core.workstation import WORKSTATION_LAYERS, WorkstationLinks
from dzmm_bot.runtime.contracts import InboundMessage
from dzmm_bot.runtime.settings import Settings


NOW = datetime(2026, 10, 15, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
SECRET = "workstation-test-core-secret"
PUBLIC_URL = "https://workstation.example.test"
GAME_URL = "https://www.dzmm.ai/character/3772306"


@pytest.fixture
def workstation_context():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(factory)
    repository.bootstrap_primary_group("https://www.aikda.com/chat?c=workstation-group", NOW)
    links = WorkstationLinks(SECRET, PUBLIC_URL)
    service = CoreService(repository, GroupCommandHandler(repository, workstation_links=links))

    def send(identifier, content, sender="owner"):
        result = service.receive_inbound(InboundMessage(
            identifier, sender, content, NOW, source_type="group", chatroom_id="workstation-group",
        ))
        with factory() as session:
            return "\n".join(session.scalars(select(OutboundRecord.text).where(
                OutboundRecord.inbound_message_id == result.message_id,
            )))

    send("join-owner", "/入职 糯糯")
    send("join-visitor", "/入职 小小糯", "visitor")
    owner = repository.find_user("owner")
    repository.record_balance_change(owner.id, 128 - owner.balance, "board_bonus", NOW)
    with TestClient(create_app(repository, SECRET, workstation_public_url=PUBLIC_URL)) as internal:
        with httpx.Client(
            base_url="http://core.test", headers={"X-Core-Token": SECRET},
            transport=internal._transport,
        ) as http_client:
            core = CoreClient("http://core.test", SECRET, client=http_client)
            with TestClient(create_admin_app(
                "admin-test-secret", core, repository=AdminRepository(factory),
            )) as public:
                yield repository, factory, links, send, internal, public
    engine.dispose()


def test_group_command_sends_personal_link_and_nonmembers_cannot_get_one(workstation_context):
    repository, factory, links, send, _, _ = workstation_context
    owner = repository.find_user("owner")
    reply = send("my-workstation", "/我的工位")
    assert f"{PUBLIC_URL}/workstation/{links.token_for(owner.id)}" in reply
    assert "工位链接将在下一条消息发送" in reply
    with factory() as session:
        records = session.scalars(select(OutboundRecord).where(OutboundRecord.text == links.url_for(owner.id))).all()
        assert len(records) == 1
        assert records[0].reply_index == 1
        assert records[0].reference_message_id is None
        assert records[0].reference_sender_platform_id is None
        assert records[0].reference_content_type is None
        assert records[0].reference_text is None
        assert records[0].destination_chatroom_id == "workstation-group"
        assert records[0].group_chat_id == repository.resolve_enabled_group_chat("workstation-group").id
        overview = session.scalar(select(OutboundRecord).where(
            OutboundRecord.inbound_message_id == records[0].inbound_message_id,
            OutboundRecord.reply_index == 0,
        ))
        assert overview.reference_message_id == "my-workstation"
    send("my-workstation", "/我的工位")
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(OutboundRecord).where(
            OutboundRecord.text == links.url_for(owner.id)
        )) == 1
    assert "糯糯的工位" in reply
    assert "owner" not in reply
    assert SECRET not in reply
    assert "请先使用 /入职" in send("unregistered", "/我的工位", "stranger")
    assert links.token_for(repository.find_user("visitor").id) not in reply


def test_unconfigured_url_reports_unavailable_instead_of_localhost(workstation_context):
    repository, _, _, _, _, _ = workstation_context
    handler = GroupCommandHandler(repository)
    reply = handler.handle(InboundMessage(
        "unconfigured", "owner", "/我的工位", NOW, source_type="group", chatroom_id="workstation-group",
    ))
    assert "请管理员配置公开访问地址" in reply
    assert "http" not in reply


def test_core_inbound_factory_uses_configured_link(workstation_context):
    repository, factory, links, _, internal, _ = workstation_context
    response = internal.post("/internal/inbound", headers={"X-Core-Token": SECRET}, json={
        "platform_message_id": "factory-command", "sender_platform_id": "owner",
        "content": "/我的工位", "received_at": NOW.isoformat(),
        "source_type": "group", "chatroom_id": "workstation-group",
    })
    assert response.status_code == 200
    with factory() as session:
        replies = session.scalars(select(OutboundRecord.text)).all()
        assert any(links.url_for(repository.find_user("owner").id) in reply for reply in replies)


def test_game_entry_uses_platform_identity_without_changing_existing_personal_links(workstation_context):
    repository, factory, links, _, _, public = workstation_context
    owner = repository.find_user("owner")
    original_balance = owner.balance
    with TestClient(create_app(
        repository, SECRET, workstation_public_url=PUBLIC_URL, workstation_game_url=GAME_URL,
    )) as internal:
        for sender in ["owner", "visitor"]:
            message_id = f"platform-entry-{sender}"
            response = internal.post("/internal/inbound", headers={"X-Core-Token": SECRET}, json={
                "platform_message_id": message_id, "sender_platform_id": sender,
                "content": "/我的工位", "received_at": NOW.isoformat(),
                "source_type": "group", "chatroom_id": "workstation-group",
            })
            assert response.status_code == 200
        with factory() as session:
            replies = list(session.scalars(select(OutboundRecord.text)))
        for sender in ["owner", "visitor"]:
            employee = repository.find_user(sender)
            reply = next(text for text in replies if f"【{employee.display_name}的工位】" in text)
            assert GAME_URL not in reply
            assert "当前 DZMM 登录账号" in reply
            assert "/workstation/" not in reply
            assert links.token_for(employee.id) not in reply
        assert replies.count(GAME_URL) == 2
        with factory() as session:
            link_records = session.scalars(select(OutboundRecord).where(OutboundRecord.text == GAME_URL)).all()
            assert len(link_records) == 2
            assert all(link.reference_message_id is None and link.reference_text is None for link in link_records)
            assert all(link.delivery_kind == "group" and link.destination_chatroom_id == "workstation-group" for link in link_records)
    assert repository.find_user("owner").balance == original_balance
    assert public.get(f"/api/workstations/{links.token_for(owner.id)}").status_code == 200


def test_public_view_reads_actual_equipment_and_refreshes_without_charging(workstation_context):
    repository, factory, links, send, _, public = workstation_context
    token = links.token_for(repository.find_user("owner").id)
    path = f"/api/workstations/{token}"
    assert public.get(path).json()["equipped"] == []
    assert "购买成功" in send("buy", "/购买装备 1")
    assert public.get(path).json()["equipped"] == []
    send("equip", "/装备 1")
    response = public.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "display_name": "糯糯", "employee_number": "#0001", "equipped": [{
            "number": 1, "asset_key": "monitor-main", "name": "主显示器", "daily_income": 2,
        }], "daily_income": 2, "income_settlement_enabled": False, "currency_name": "摸鱼币",
    }
    visitor_token = links.token_for(repository.find_user("visitor").id)
    assert public.get(f"/api/workstations/{visitor_token}").json()["equipped"] == []
    with factory.begin() as session:
        item = session.scalar(select(EquipmentItemRecord).where(EquipmentItemRecord.public_number == 1))
        item.enabled = False
        item.daily_income = 4
    assert public.get(path).json()["daily_income"] == 4
    assert "工位概览" in public.get(f"/workstation/{token}").text
    send("remove", "/卸下 1")
    assert public.get(path).json()["daily_income"] == 0
    assert repository.find_user("owner").balance == 92
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(EquipmentOwnershipRecord)) == 1
        assert session.scalar(select(func.count()).select_from(EquipmentPurchaseRecord)) == 1


def test_public_view_cannot_mutate_or_authorize_admin_endpoints(workstation_context):
    repository, _, links, _, internal, public = workstation_context
    token = links.token_for(repository.find_user("owner").id)
    assert internal.get(f"/internal/workstations/{token}").status_code == 401
    assert public.post(f"/api/workstations/{token}", json={"equipped": [1]}).status_code == 405
    assert public.get("/api/status", headers={"X-Admin-Token": token}).status_code == 401
    assert public.get("/api/integration/users/owner/balance", headers={"X-Api-Key": token}).status_code in {401, 503}


@pytest.mark.parametrize("invalid", ["invalid", "0" * 32 + "." + "0" * 64, "signed-unknown", "tampered"])
def test_invalid_or_unknown_workstation_returns_friendly_404(workstation_context, invalid):
    repository, _, links, _, _, public = workstation_context
    if invalid == "signed-unknown":
        invalid = links.token_for(uuid4())
    elif invalid == "tampered":
        invalid = links.token_for(repository.find_user("owner").id)
        invalid = invalid[:-1] + ("0" if invalid[-1] != "0" else "1")
    for prefix in ("/workstation/", "/api/workstations/"):
        response = public.get(prefix + invalid)
        assert response.status_code == 404
        assert "重新发送 /我的工位" in response.text


def test_assets_are_packaged_and_public_page_does_not_use_demo_state(workstation_context):
    repository, _, links, _, _, public = workstation_context
    token = links.token_for(repository.find_user("owner").id)
    response = public.get(f"/workstation/{token}")
    assert response.status_code == 200
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "img-src 'self' data:" in response.headers["content-security-policy"]
    assert "default-src 'self';" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert SECRET not in response.text
    script = public.get("/static/workstation.js")
    assert script.status_code == 200
    assert "localStorage" not in script.text
    assert "innerHTML" not in script.text
    assert "credentials: \"omit\"" in script.text
    assert public.get("/static/workstation.css").status_code == 200
    for name in ["core-base.png", *(f"{key}-layer.png" for key in WORKSTATION_LAYERS)]:
        asset = public.get(f"/static/workstation/{name}")
        assert asset.status_code == 200
        assert asset.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert public.get("/static/workstation/manifest.json").status_code == 404


@pytest.mark.parametrize("failure", ["unavailable", "upstream-error"])
def test_public_view_sanitizes_core_failures(workstation_context, failure):
    repository, factory, links, _, _, _ = workstation_context
    token = links.token_for(repository.find_user("owner").id)

    class UnavailableCore:
        def get_workstation(self, token):
            request = httpx.Request("GET", "http://core.test/internal/workstations/test")
            if failure == "unavailable":
                raise httpx.ConnectError("private connection details", request=request)
            response = httpx.Response(500, text="private database details", request=request)
            response.raise_for_status()

    with TestClient(create_admin_app("admin-test-secret", UnavailableCore(), repository=AdminRepository(factory))) as client:
        for prefix in ("/workstation/", "/api/workstations/"):
            response = client.get(prefix + token)
            assert response.status_code == 503
            assert "稍后重试" in response.text
            assert "private" not in response.text


def test_public_read_does_not_seed_missing_catalog(workstation_context):
    repository, factory, links, _, _, public = workstation_context
    with factory.begin() as session:
        session.query(EquipmentItemRecord).delete()
    token = links.token_for(repository.find_user("owner").id)
    assert public.get(f"/api/workstations/{token}").status_code == 200
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(EquipmentItemRecord)) == 0


def test_changing_signing_key_invalidates_old_links():
    identifier = UUID("00000000-0000-0000-0000-000000000001")
    old = WorkstationLinks("old-test-key", PUBLIC_URL)
    new = WorkstationLinks("new-test-key", PUBLIC_URL)
    token = old.token_for(identifier)
    assert old.user_id_for(token) == identifier
    assert new.user_id_for(token) is None
    assert old.user_id_for(str(identifier)) is None
    assert old.url_for(identifier) == old.url_for(identifier)


@pytest.mark.parametrize("value", [
    "javascript:alert(1)", "https://user:password@example.test", "https://example.test?a=b",
    "https://example.test#token", "https://example.test/../admin", "https://example.test:bad",
    "https://example.test:0", "https://example.test/with space", "https://example.test\\evil", "https://[invalid",
])
def test_settings_rejects_unsafe_public_url(monkeypatch, value):
    monkeypatch.setenv("DZMM_DATABASE_URL", "sqlite://")
    monkeypatch.setenv("DZMM_CORE_TOKEN", SECRET)
    monkeypatch.setenv("DZMM_BROWSER_PROFILE", str(Path.cwd() / "output" / "test-browser"))
    monkeypatch.setenv("DZMM_WORKSTATION_PUBLIC_URL", value)
    with pytest.raises(ValueError, match="DZMM_WORKSTATION_PUBLIC_URL"):
        Settings.from_environment()


def test_settings_supports_optional_url_and_proxy_prefix(monkeypatch):
    monkeypatch.setenv("DZMM_DATABASE_URL", "sqlite://")
    monkeypatch.setenv("DZMM_CORE_TOKEN", SECRET)
    monkeypatch.setenv("DZMM_BROWSER_PROFILE", str(Path.cwd() / "output" / "test-browser"))
    monkeypatch.delenv("DZMM_WORKSTATION_PUBLIC_URL", raising=False)
    monkeypatch.delenv("DZMM_WORKSTATION_GAME_URL", raising=False)
    assert Settings.from_environment().workstation_public_url is None
    assert Settings.from_environment().workstation_game_url is None
    monkeypatch.setenv("DZMM_WORKSTATION_PUBLIC_URL", PUBLIC_URL + "/games/")
    assert Settings.from_environment().workstation_public_url == PUBLIC_URL + "/games"
    monkeypatch.setenv("DZMM_WORKSTATION_GAME_URL", GAME_URL + "/")
    assert Settings.from_environment().workstation_game_url == GAME_URL


@pytest.mark.parametrize("value", ["http://www.dzmm.ai/character/3772306", "https://user:password@example.test", "https://example.test?token=private"])
def test_settings_rejects_unsafe_game_entry_url(monkeypatch, value):
    monkeypatch.setenv("DZMM_DATABASE_URL", "sqlite://")
    monkeypatch.setenv("DZMM_CORE_TOKEN", SECRET)
    monkeypatch.setenv("DZMM_BROWSER_PROFILE", str(Path.cwd() / "output" / "test-browser"))
    monkeypatch.setenv("DZMM_WORKSTATION_GAME_URL", value)
    with pytest.raises(ValueError, match="DZMM_WORKSTATION_GAME_URL"):
        Settings.from_environment()
