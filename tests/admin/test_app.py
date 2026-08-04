from dataclasses import dataclass, field

import httpx
import pytest
from fastapi.testclient import TestClient


@dataclass
class FakeCore:
    login_state_value: str = "ready"
    commands: list[str] = field(default_factory=list)

    def status(self):
        return {
            "state": "healthy",
            "last_heartbeat": "2026-08-04T12:00:00Z",
            "queue_counts": {"inbound": 2, "outbound": 1},
            "raw_cookies": "must-not-leak",
            "profile_path": "/secret/profile",
        }

    def login_state(self):
        return self.login_state_value

    def enqueue_command(self, command):
        self.commands.append(command)
        return {"id": "command-1", "command": command, "status": "pending"}


class FakeConsole:
    def __init__(self):
        self.requests = []

    def get(self, path):
        self.requests.append(path)
        return httpx.Response(
            200,
            content=b"<html>noVNC</html>",
            headers={"content-type": "text/html; charset=utf-8"},
            request=httpx.Request("GET", f"http://127.0.0.1:16080{path}"),
        )


@pytest.fixture
def core():
    return FakeCore()


@pytest.fixture
def console():
    return FakeConsole()


@pytest.fixture
def client(core, console):
    from dzmm_bot.admin.app import create_app

    return TestClient(create_app("admin-secret", core, console_client=console))


@pytest.fixture
def headers():
    return {"X-Admin-Token": "admin-secret"}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/status"),
        ("post", "/api/worker/start"),
        ("post", "/api/worker/stop"),
        ("post", "/api/worker/restart"),
        ("post", "/api/login/start"),
        ("post", "/api/login/finish"),
        ("get", "/login-console"),
    ],
)
def test_admin_routes_require_admin_token(client, method, path):
    assert client.request(method, path).status_code == 401


def test_health_is_public_and_discloses_no_configuration(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_returns_only_safe_operational_fields(client, headers):
    response = client.get("/api/status", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "state": "healthy",
        "last_heartbeat": "2026-08-04T12:00:00Z",
        "queue_counts": {"inbound": 2, "outbound": 1},
    }
    assert "cookie" not in response.text.lower()
    assert "profile" not in response.text.lower()


@pytest.mark.parametrize(
    ("action", "command"),
    [
        ("start", "resume_listening"),
        ("stop", "pause_listening"),
        ("restart", "restart_browser"),
    ],
)
def test_worker_actions_create_durable_core_commands(
    client, headers, core, action, command
):
    response = client.post(f"/api/worker/{action}", headers=headers)

    assert response.status_code == 202
    assert response.json() == {
        "id": "command-1",
        "command": command,
        "status": "pending",
    }
    assert core.commands == [command]


def test_login_start_creates_only_durable_command_when_auth_required(
    client, headers, core
):
    core.login_state_value = "auth_required"

    response = client.post("/api/login/start", headers=headers)

    assert response.status_code == 202
    assert core.commands == ["start_auth"]


def test_login_start_rejects_other_states(client, headers, core):
    core.login_state_value = "ready"

    response = client.post("/api/login/start", headers=headers)

    assert response.status_code == 409
    assert core.commands == []


def test_login_finish_creates_only_durable_command_during_auth(
    client, headers, core
):
    core.login_state_value = "auth_in_progress"

    response = client.post("/api/login/finish", headers=headers)

    assert response.status_code == 202
    assert core.commands == ["finish_auth"]


def test_login_console_is_proxied_only_during_auth(
    client, headers, core, console
):
    blocked = client.get("/login-console", headers=headers)
    core.login_state_value = "auth_in_progress"
    allowed = client.get("/login-console", headers=headers)

    assert blocked.status_code == 409
    assert allowed.status_code == 200
    assert allowed.text == "<html>noVNC</html>"
    assert console.requests == ["/vnc.html"]


def test_index_contains_status_fields_and_only_declared_actions(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "last-heartbeat" in response.text
    assert "queue-counts" in response.text
    for path in (
        "/api/worker/start",
        "/api/worker/stop",
        "/api/worker/restart",
        "/api/login/start",
        "/api/login/finish",
    ):
        assert path in response.text
