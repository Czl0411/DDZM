from dataclasses import dataclass, field

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@dataclass
class FakeCore:
    login_state_value: str = "ready"
    commands: list[str] = field(default_factory=list)
    command_definitions: list[dict] = field(
        default_factory=lambda: [
            {
                "command": "/打卡",
                "description": "每日领取 5 摸鱼币",
                "enabled": True,
                "templates": [
                    {
                        "scenario": "checked_in",
                        "label": "打卡成功",
                        "template": "打卡成功，领取 {打卡奖励} 摸鱼币。",
                        "variables": ["{昵称}", "{余额}", "{打卡奖励}", "{日期}"],
                    }
                ],
            }
        ]
    )
    employees: list[dict] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    template_error: bool = False

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

    def list_game_commands(self):
        return self.command_definitions

    def set_game_command_enabled(self, command, enabled):
        record = next(item for item in self.command_definitions if item["command"] == command)
        record["enabled"] = enabled
        return record

    def set_game_command_template(self, command, scenario, template):
        if self.template_error:
            request = httpx.Request("PATCH", "http://core/internal/game/command-templates")
            response = httpx.Response(422, text="invalid template", request=request)
            raise httpx.HTTPStatusError("invalid template", request=request, response=response)
        record = next(item for item in self.command_definitions if item["command"] == command)
        reply = next(item for item in record["templates"] if item["scenario"] == scenario)
        reply["template"] = template
        return reply

    def list_game_users(self):
        return self.employees

    def list_game_items(self):
        return self.items

    def create_game_item(self, item):
        item = {**item, "enabled": True}
        self.items.append(item)
        return item


class FakeConsole:
    def __init__(self):
        self.requests = []

    def get(self, path):
        self.requests.append(path)
        content = {
            "/vnc.html": b'<script src="app/ui.js"></script>',
            "/app/ui.js": b"export const ui = true;",
        }.get(path, b"not found")
        status_code = 200 if path in {"/vnc.html", "/app/ui.js"} else 404
        return httpx.Response(
            status_code,
            content=content,
            headers={
                "content-type": (
                    "text/html; charset=utf-8"
                    if path == "/vnc.html"
                    else "text/javascript"
                )
            },
            request=httpx.Request("GET", f"http://127.0.0.1:16080{path}"),
        )


class FakeUpstreamWebSocket:
    def __init__(self):
        self._frames = iter([b"server-frame"])
        self.sent = []
        self.subprotocol = "binary"

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._frames)
        except StopIteration:
            raise StopAsyncIteration

    async def send(self, data):
        self.sent.append(data)


class FakeWebSocketConnection:
    def __init__(self):
        self.paths = []
        self.upstream = FakeUpstreamWebSocket()

    def connect(self, path, *, subprotocols=None):
        self.paths.append((path, subprotocols))
        upstream = self.upstream

        class Connection:
            async def __aenter__(self):
                return upstream

            async def __aexit__(self, *args):
                return None

        return Connection()


@pytest.fixture
def core():
    return FakeCore()


@pytest.fixture
def console():
    return FakeConsole()


@pytest.fixture
def websocket_connection():
    return FakeWebSocketConnection()


@pytest.fixture
def client(core, console, websocket_connection):
    from dzmm_bot.admin.app import create_app

    return TestClient(
        create_app(
            "admin-secret",
            core,
            console_client=console,
            websocket_connector=websocket_connection.connect,
        )
    )


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
        ("post", "/api/session"),
        ("patch", "/api/game/command-templates"),
        ("get", "/login-console"),
    ],
)
def test_admin_routes_require_admin_token(client, method, path):
    assert client.request(method, path).status_code == 401


def test_health_is_public_and_discloses_no_configuration(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_admin_dashboard_serves_its_login_and_style_assets(client):
    page = client.get("/")
    stylesheet = client.get("/static/admin.css")

    assert page.status_code == 200
    assert 'id="login-screen"' in page.text
    assert 'id="dashboard"' in page.text
    assert 'data-action="/api/login/start"' in page.text
    assert 'id="login-console-frame"' in page.text
    assert stylesheet.status_code == 200
    assert "--surface" in stylesheet.text


def test_admin_dashboard_exposes_game_navigation_and_proxies_game_data(
    client, headers
):
    page = client.get("/")
    commands = client.get("/api/game/commands", headers=headers)
    disabled = client.patch(
        "/api/game/commands",
        headers=headers,
        json={"command": "/打卡", "enabled": False},
    )
    item = client.post(
        "/api/game/items",
        headers=headers,
        json={"name": "工位午睡券", "description": "眯十分钟。", "price": 5, "stock": 3},
    )

    assert 'id="nav-commands"' in page.text
    assert 'id="nav-employees"' in page.text
    assert 'id="nav-shop"' in page.text
    assert commands.json()[0]["command"] == "/打卡"
    assert disabled.json()["enabled"] is False
    assert item.status_code == 201


def test_admin_relay_updates_a_command_template(client, headers, core):
    response = client.patch(
        "/api/game/command-templates",
        headers=headers,
        json={
            "command": "/打卡",
            "scenario": "checked_in",
            "template": "{昵称} +{打卡奖励}",
        },
    )

    assert response.status_code == 200
    assert response.json()["template"] == "{昵称} +{打卡奖励}"
    assert core.command_definitions[0]["templates"][0]["template"] == "{昵称} +{打卡奖励}"


def test_admin_relay_rejects_a_template_without_required_fields(client, headers):
    response = client.patch(
        "/api/game/command-templates", headers=headers, json={"command": "/余额"}
    )

    assert response.status_code == 422


def test_admin_relay_forwards_core_template_validation_failure(client, headers, core):
    core.template_error = True

    response = client.patch(
        "/api/game/command-templates",
        headers=headers,
        json={
            "command": "/打卡",
            "scenario": "checked_in",
            "template": "{商店列表}",
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid template"}


def test_command_library_serves_template_editor_controls(client):
    """Fails if the command library cannot render or save reply templates."""
    script = client.get("/static/admin.js")

    assert "data-template-command" in script.text
    assert "data-variable" in script.text
    assert "/api/game/command-templates" in script.text


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


def test_concrete_core_client_uses_aggregate_status_endpoint():
    from dzmm_bot.admin.core_client import CoreClient

    def handle(request):
        assert request.headers["X-Core-Token"] == "core-secret"
        assert request.url.path == "/internal/status"
        return httpx.Response(
            200,
            json={
                "state": "auth_required",
                "last_heartbeat": "2026-08-04T12:00:00Z",
                "queue_counts": {
                    "inbound_accepted": 3,
                    "outbound_pending": 2,
                    "worker_commands_pending": 1,
                },
            },
        )

    transport = httpx.MockTransport(handle)
    http_client = httpx.Client(
        base_url="http://127.0.0.1:18120",
        headers={"X-Core-Token": "core-secret"},
        transport=transport,
    )

    assert CoreClient("unused", "unused", client=http_client).status() == {
        "state": "auth_required",
        "last_heartbeat": "2026-08-04T12:00:00Z",
        "queue_counts": {
            "inbound_accepted": 3,
            "outbound_pending": 2,
            "worker_commands_pending": 1,
        },
    }


def test_novnc_websocket_connector_targets_only_loopback():
    from dzmm_bot.admin.core_client import NoVNCWebSocketConnector

    calls = []
    expected_connection = object()

    def connect(uri, *, subprotocols=None):
        calls.append((uri, subprotocols))
        return expected_connection

    connector = NoVNCWebSocketConnector(port=16080, connect=connect)

    assert connector("/websockify", subprotocols=["binary"]) is expected_connection
    assert calls == [
        ("ws://127.0.0.1:16080/websockify", ["binary"]),
    ]


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
    assert 'src="app/ui.js"' in allowed.text
    assert console.requests == ["/vnc.html"]


def test_admin_token_creates_httponly_console_session_without_url_secret(
    client, headers
):
    response = client.post("/api/session", headers=headers)

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert "dzmm_admin_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/login-console" in cookie
    assert "admin-secret" not in cookie
    assert "admin-secret" not in response.headers.get("location", "")


def test_console_session_authenticates_root_and_relative_assets(
    client, headers, core, console
):
    client.post("/api/session", headers=headers)
    core.login_state_value = "auth_in_progress"

    root = client.get("/login-console")
    asset = client.get("/login-console/app/ui.js")

    assert root.status_code == 200
    assert root.url.path == "/login-console/"
    assert root.url.params["path"] == "login-console/websockify"
    assert asset.status_code == 200
    assert asset.text == "export const ui = true;"
    assert console.requests == ["/vnc.html", "/app/ui.js"]


def test_console_root_forces_authenticated_novnc_websocket_path(
    client, headers, core
):
    client.post("/api/session", headers=headers)
    core.login_state_value = "auth_in_progress"

    response = client.get("/login-console/?path=websockify")

    assert response.status_code == 200
    assert response.url.params["path"] == "login-console/websockify"


def test_console_root_redirects_duplicate_attacker_first_path(
    client, headers, core, console
):
    client.post("/api/session", headers=headers)
    core.login_state_value = "auth_in_progress"

    response = client.get(
        "/login-console/?path=attacker&path=login-console%2Fwebsockify",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == (
        "/login-console/?path=login-console%2Fwebsockify"
    )
    assert console.requests == []


def test_console_assets_reject_session_when_auth_is_not_active(
    client, headers, core
):
    client.post("/api/session", headers=headers)
    core.login_state_value = "ready"

    assert client.get("/login-console/app/ui.js").status_code == 409


def test_console_asset_proxy_preserves_upstream_not_found(client, headers, core):
    client.post("/api/session", headers=headers)
    core.login_state_value = "auth_in_progress"

    response = client.get("/login-console/missing.js")

    assert response.status_code == 404
    assert response.text == "not found"


def test_console_websocket_requires_session_and_active_auth(
    client, headers, core, websocket_connection
):
    core.login_state_value = "auth_in_progress"
    with pytest.raises(WebSocketDisconnect) as missing_session:
        with client.websocket_connect("/login-console/websockify"):
            pass
    assert missing_session.value.code == 4401

    client.post("/api/session", headers=headers)
    core.login_state_value = "ready"
    with pytest.raises(WebSocketDisconnect) as wrong_state:
        with client.websocket_connect("/login-console/websockify"):
            pass
    assert wrong_state.value.code == 4409

    core.login_state_value = "auth_in_progress"
    with client.websocket_connect(
        "/login-console/websockify", subprotocols=["binary"]
    ) as websocket:
        assert websocket.accepted_subprotocol == "binary"
        assert websocket.receive_bytes() == b"server-frame"

    assert websocket_connection.paths == [("/websockify", ["binary"])]


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
