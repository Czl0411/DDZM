from copy import deepcopy
from datetime import date, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from dzmm_bot.admin.app import create_app
from dzmm_bot.admin.core_client import CoreClient
from dzmm_bot.admin.repository import AdminRepository
from dzmm_bot.core.app import create_app as create_core_app
from dzmm_bot.core.honors import HonorSeasonMember, midnight
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import AuditEventRecord, Base, beijing_now


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
    internal = TestClient(core_app)

    def transport(request):
        response = internal.request(request.method, str(request.url), headers=request.headers, content=request.content)
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)

    upstream = httpx.Client(transport=httpx.MockTransport(transport), base_url="http://testserver",
                            headers={"X-Core-Token": "core-secret"})
    core = CoreClient("http://testserver", "core-secret", client=upstream)
    admin_repository = AdminRepository(factory)
    account = admin_repository.create_account("viewer", "password-for-tests")
    token = admin_repository.create_session(account.id, beijing_now())
    admin = TestClient(create_app("admin-secret", core, repository=admin_repository,
                                  profile_upload_dir=tmp_path / "profiles"))
    yield admin, repository, {"X-Admin-Session": token}
    upstream.close()
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
    assert client.post("/api/game/honors/backfill", headers=viewer).status_code == 403
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


def test_super_admin_can_backfill_all_missing_periods(context):
    client, repository, _ = context
    response = client.post(
        "/api/game/honors/backfill",
        headers={"X-Admin-Token": "admin-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "count": 1,
        "settled_weeks": ["2026-09-28"],
        "next_week": "2026-10-05",
    }
    assert repository.honor_periods()["total"] == 1


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


def test_manual_permanent_honor_grant_wear_and_revoke(context):
    client, repository, viewer = context
    base = "/api/game/honors"
    super_admin = {"X-Admin-Token": "admin-secret"}
    now = midnight(date(2026, 10, 5))
    assert client.get(f"{base}/employees?query=糯").status_code == 401
    employee, = client.get(f"{base}/employees?query=糯", headers=viewer).json()["items"]
    assert client.get(f"{base}/employees", headers=viewer, params={"query": f"#{employee['employee_number']:04d}"}).json() == {"items": [employee]}
    grant = {"employee_number": employee["employee_number"], "name": "年度热心同事", "reason": "帮同事整理资料"}
    headers = {**viewer, "Idempotency-Key": str(uuid4())}
    path = f"{base}/permanent/grant"
    assert client.post(path, headers=headers, json={**grant, "actor": "spoofed"}).status_code == 422
    response = client.post(path, headers=headers, json=grant)
    assert response.status_code == 200, response.text
    award = response.json()
    assert award["source"] == "manual" and award["expires_at"] is None
    assert award["source_details"] == {"actor": "viewer", "reason": grant["reason"]}
    assert client.post(path, headers=headers, json=grant).json() == award
    assert client.post(path, headers={**viewer, "Idempotency-Key": str(uuid4())}, json=grant).status_code == 409

    personal = repository.my_honors("user-1", now)
    assert personal["equipped"] is None
    assert "source_details" not in personal["items"][0]
    assert repository.wear_honor("user-1", 1, now) == grant["name"]
    future = now + timedelta(days=400)
    assert repository.get_equipped_honor("user-1", future) == grant["name"]

    path = f"{base}/permanent/{award['id']}/revoke"
    reason = {"reason": "员工申请撤回"}
    assert client.post(path, headers=viewer, json=reason).status_code == 403
    response = client.post(path, headers=super_admin, json=reason)
    assert response.status_code == 200, response.text
    assert client.post(path, headers=super_admin, json=reason).json() == response.json()
    assert repository.my_honors("user-1", now)["items"] == []
    assert repository.get_equipped_honor("user-1", now) is None
    history, = client.get(f"{base}/history?source=manual", headers=viewer).json()["items"]
    assert history["week_start"] is None and history["active"] is False
    assert history["source_details"]["revoke_reason"] == reason["reason"]
    with repository._session() as session:
        events = session.scalars(select(AuditEventRecord.event_type).where(
            AuditEventRecord.event_type.in_(["honor_permanent_grant", "honor_permanent_revoke"]),
        )).all()
    assert sorted(events) == ["honor_permanent_grant", "honor_permanent_revoke"]


def test_s1_admin_issuance_routes_are_removed_but_history_is_preserved(context):
    client, repository, _ = context
    base = "/api/game/honors/seasons/s1"
    super_admin = {"X-Admin-Token": "admin-secret"}
    now = midnight(date(2026, 10, 5))
    routes = [
        ("GET", f"{base}/settings", None),
        ("PATCH", f"{base}/settings", {"minimum_rank_order": 8, "expected_version": 0}),
        ("POST", f"{base}/preview", {"roster": []}),
        ("POST", f"{base}/issue", {"roster": [], "preview_digest": "0" * 64}),
    ]
    for method, path, body in routes:
        assert client.request(method, path, headers=super_admin, json=body).status_code == 404

    with TestClient(create_core_app(repository, "core-secret", clock=lambda: now)) as core:
        for method, path, body in routes:
            internal_path = path.replace("/api/", "/internal/")
            assert core.request(
                method,
                internal_path,
                headers={"X-Core-Token": "core-secret"},
                json=body,
            ).status_code == 404

    employee = repository.find_user("user-1")
    roster = [HonorSeasonMember(
        employee_number=employee.employee_number,
        department="结季技术部",
        rank="技术总监",
    )]
    preview = repository.preview_s1_honors(roster, now)
    repository.issue_s1_honors(roster, preview["preview_digest"], "legacy-admin", now)
    history, = client.get("/api/game/honors/history?source=season", headers=super_admin).json()["items"]
    assert history["source_details"]["department"] == "结季技术部"
    assert history["season_info"]["closing_rank"] == "技术总监"
    assert history["season_info"]["eligible"] and history["season_info"]["status"] == "available"
    assert not history["season_info"]["customized"]
