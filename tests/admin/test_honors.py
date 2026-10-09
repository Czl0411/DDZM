from copy import deepcopy
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from dzmm_bot.admin.app import create_app
from dzmm_bot.admin.core_client import CoreClient
from dzmm_bot.admin.repository import AdminRepository
from dzmm_bot.core.app import create_app as create_core_app
from dzmm_bot.core.honors import midnight
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, beijing_now


@pytest.fixture
def context(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(factory)
    now = midnight(date(2026, 10, 5))
    repository.bootstrap_primary_group("https://www.aikda.com/chat?c=main", now)
    repository.get_honor_config(midnight(date(2026, 9, 28)))
    repository.create_user("user-1", "糯糯", now, 0)
    core_app = create_core_app(repository, "core-secret", clock=lambda: now)
    internal = TestClient(core_app, headers={"X-Core-Token": "core-secret"})
    core = CoreClient("http://testserver", "core-secret", client=internal)
    admin_repository = AdminRepository(factory)
    account = admin_repository.create_account("viewer", "password-for-tests")
    token = admin_repository.create_session(account.id, beijing_now())
    admin = TestClient(create_app("admin-secret", core, repository=admin_repository,
                                  profile_upload_dir=tmp_path / "profiles"))
    yield admin, repository, {"X-Admin-Session": token}
    internal.close()
    engine.dispose()


def payload(repository):
    config = repository.get_honor_config(midnight(date(2026, 10, 5)))
    values = deepcopy(config["configuration"])
    values.pop("activity_rules")
    return {**values, "expected_version": config["version"]}


@pytest.mark.parametrize("path", ["config", "periods", "history", "preview?week_start=2026-09-28"])
def test_honor_read_requires_auth_and_allows_regular_admin(context, path):
    client, _, viewer = context
    assert client.get(f"/api/game/honors/{path}").status_code == 401
    assert client.get(f"/api/game/honors/{path}", headers=viewer).status_code == 200


def test_regular_admin_cannot_configure_settle_or_correct(context):
    client, repository, viewer = context
    assert client.patch("/api/game/honors/config", headers=viewer, json=payload(repository)).status_code == 403
    assert client.post("/api/game/honors/settle", headers=viewer,
        json={"week_start": "2026-09-28", "preview_digest": "0" * 64}).status_code == 403
    assert client.post(f"/api/game/honors/awards/{uuid4()}/correct", headers=viewer,
        json={"winner_id": None, "reason": "测试", "expected_revision": 1}).status_code == 403


def test_super_admin_validation_conflicts_and_trusted_actor(context):
    client, repository, _ = context
    headers = {"X-Admin-Token": "admin-secret"}
    values = payload(repository)
    values["enabled"] = True
    values["announcement_time"] = "08:45"
    response = client.patch("/api/game/honors/config", headers=headers, json=values)
    assert response.status_code == 200
    assert response.json()["effective_week"] == "2026-10-12"
    assert response.json()["configuration"]["announcement_time"] == "08:45"
    assert response.json()["current"]["announcement_time"] == "09:00"
    assert client.patch("/api/game/honors/config", headers=headers, json=values).status_code == 409
    assert client.patch("/api/game/honors/config", headers=headers,
                        json={**payload(repository), "actor": "spoofed"}).status_code == 422
    assert client.get("/api/game/honors/preview?week_start=bad-date", headers=headers).status_code == 422
    preview = client.get("/api/game/honors/preview?week_start=2026-09-28", headers=headers).json()
    settle = {"week_start": "2026-09-28", "preview_digest": preview["preview_digest"]}
    response = client.post("/api/game/honors/settle", headers=headers, json=settle)
    assert response.status_code == 200
    assert client.post("/api/game/honors/settle", headers=headers, json=settle).json()["id"] == response.json()["id"]
    assert client.get("/api/game/users/user-1/honors", headers=headers).json()["name"] == "糯糯"
    assert client.get("/api/game/users/missing/honors", headers=headers).status_code == 404


@pytest.mark.parametrize("invalid_time", ["24:00", "09:60", "9:00", "09:00:00", "", None, 900])
def test_honor_announcement_time_rejects_invalid_values(context, invalid_time):
    client, repository, _ = context
    values = {**payload(repository), "announcement_time": invalid_time}
    response = client.patch("/api/game/honors/config", headers={"X-Admin-Token": "admin-secret"}, json=values)
    assert response.status_code == 422
    assert repository.get_honor_config(midnight(date(2026, 10, 5)))["version"] == 0


def test_honor_page_and_script_are_available(context):
    client, _, _ = context
    assert 'id="honors-view"' in client.get("/").text
    script = client.get("/static/honors.js")
    assert script.status_code == 200
    assert "no-cache" in script.headers["cache-control"]
    assert "preview_digest" in script.text
