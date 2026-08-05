from dataclasses import dataclass, field
from html.parser import HTMLParser

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect


def _page(items, page, page_size):
    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start : start + page_size],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
    }


def assign_super_login_lease(core):
    core.manual_login_lease = {
        "operator_id": "super_admin",
        "operator_name": "超级管理员",
        "expires_at": "2026-08-05T12:03:00+08:00",
    }


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
    game_settings: dict = field(
        default_factory=lambda: {
            "currency_name": "摸鱼币",
            "onboarding_bonus": 0,
            "checkin_reward": 5,
            "reset_time_label": "北京时间 00:00",
        }
    )
    activity_settings: dict = field(
        default_factory=lambda: {
            "rules": [
                {
                    "level": level,
                    "character_threshold": level * 10,
                    "reward": level,
                }
                for level in range(1, 11)
            ],
            "report_times": ["12:00", "16:00", "20:00", "23:59"],
        }
    )
    random_event_settings: dict = field(
        default_factory=lambda: {
            "start_time": "10:00",
            "end_time": "24:00",
            "events_per_day": 1,
            "minimum_interval_minutes": 60,
            "signup_timeout_minutes": 15,
            "reminder_interval_minutes": 5,
        }
    )
    random_event_scenes: list[dict] = field(default_factory=list)
    today_random_events: list[dict] = field(default_factory=list)
    manual_login_lease: dict | None = None

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

    def get_manual_login_lease(self):
        return self.manual_login_lease

    def start_manual_login(self, operator_id, operator_name):
        self.manual_login_lease = {
            "operator_id": operator_id,
            "operator_name": operator_name,
            "expires_at": "2026-08-05T12:03:00+08:00",
        }
        self.commands.append("start_auth")
        return self.manual_login_lease

    def finish_manual_login(self, operator_id, operator_name):
        if self.manual_login_lease is None or self.manual_login_lease["operator_id"] != operator_id:
            request = httpx.Request("POST", "http://core/internal/admin/login/finish")
            response = httpx.Response(409, text="manual login is not owned by actor", request=request)
            raise httpx.HTTPStatusError("forbidden", request=request, response=response)
        self.manual_login_lease = None
        self.commands.append("finish_auth")
        return {"accepted": True}

    def cancel_manual_login(self):
        cancelled = self.manual_login_lease is not None
        self.manual_login_lease = None
        if cancelled:
            self.commands.append("cancel_auth")
        return {"accepted": cancelled}

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

    def list_game_users(self, page, page_size):
        return _page(self.employees, page, page_size)

    def list_game_items(self, page, page_size):
        return _page(self.items, page, page_size)

    def create_game_item(self, item):
        item = {**item, "enabled": True}
        self.items.append(item)
        return item

    def get_game_settings(self):
        return self.game_settings

    def set_game_settings(self, settings):
        self.game_settings = {**settings, "reset_time_label": "北京时间 00:00"}
        return self.game_settings

    def get_activity_settings(self):
        return self.activity_settings

    def set_activity_settings(self, settings):
        self.activity_settings = settings
        return self.activity_settings

    def get_random_event_settings(self):
        return self.random_event_settings

    def set_random_event_settings(self, settings):
        self.random_event_settings = settings
        return self.random_event_settings

    def list_random_event_scenes(self, page, page_size):
        return _page(self.random_event_scenes, page, page_size)

    def create_random_event_scene(self, scene):
        saved = {**scene, "id": f"scene-{len(self.random_event_scenes) + 1}", "enabled": True}
        self.random_event_scenes.append(saved)
        return saved

    def update_random_event_scene(self, scene_id, scene):
        index = next(
            index
            for index, item in enumerate(self.random_event_scenes)
            if item["id"] == scene_id
        )
        saved = {**scene, "id": scene_id}
        self.random_event_scenes[index] = saved
        return saved

    def delete_random_event_scene(self, scene_id):
        self.random_event_scenes = [
            scene for scene in self.random_event_scenes if scene["id"] != scene_id
        ]
        return {"accepted": True}

    def list_today_random_events(self):
        return self.today_random_events

    def reschedule_random_event(self, schedule_id, scheduled_at):
        schedule = next(item for item in self.today_random_events if item["id"] == schedule_id)
        schedule["scheduled_at"] = scheduled_at
        return schedule


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
def admin_repository():
    from dzmm_bot.admin.repository import AdminRepository
    from dzmm_bot.core.schema import Base

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return AdminRepository(sessionmaker(engine, expire_on_commit=False))


@pytest.fixture
def client(core, console, websocket_connection, admin_repository):
    from dzmm_bot.admin.app import create_app

    return TestClient(
        create_app(
            "admin-secret",
            core,
            repository=admin_repository,
            console_client=console,
            websocket_connector=websocket_connection.connect,
        )
    )


@pytest.fixture
def headers():
    return {
        "X-Admin-Token": "admin-secret",
        "Idempotency-Key": "test-request",
        "If-Match": "0",
    }


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
        ("get", "/api/game/settings"),
        ("get", "/api/game/activity-settings"),
        ("patch", "/api/game/activity-settings"),
        ("get", "/login-console"),
    ],
)
def test_admin_routes_require_admin_token(client, method, path):
    assert client.request(method, path).status_code == 401


def test_health_is_public_and_discloses_no_configuration(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_regular_admin_authenticates_but_cannot_manage_administrators(
    client, admin_repository
):
    admin_repository.create_account("alice", "strong-password")

    login = client.post(
        "/api/auth/login", json={"username": "alice", "password": "strong-password"}
    )

    assert login.status_code == 200
    assert login.json()["account_id"]
    session_headers = {"X-Admin-Session": login.json()["session_token"]}
    assert client.get("/api/status", headers=session_headers).status_code == 200
    assert client.get("/api/admins", headers=session_headers).status_code == 403


def test_super_admin_creates_an_account_once_for_a_retried_request(client, headers):
    request_headers = {**headers, "Idempotency-Key": "create-bob"}

    first = client.post(
        "/api/admins",
        headers=request_headers,
        json={"username": "bob", "password": "strong-password"},
    )
    second = client.post(
        "/api/admins",
        headers=request_headers,
        json={"username": "bob", "password": "strong-password"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json() == first.json()
    assert [account["username"] for account in client.get("/api/admins", headers=headers).json()] == ["bob"]


def test_super_admin_retries_account_update_without_repeating_side_effects(
    client, headers, admin_repository
):
    account = admin_repository.create_account("bob", "strong-password")
    request_headers = {**headers, "Idempotency-Key": "disable-bob"}

    first = client.patch(
        f"/api/admins/{account.id}", headers=request_headers, json={"active": False}
    )
    second = client.patch(
        f"/api/admins/{account.id}", headers=request_headers, json={"active": False}
    )

    assert first.status_code == 200
    assert second.json() == first.json()
    assert second.json()["active"] is False


def test_any_admin_can_cancel_manual_login(client, admin_repository, core):
    admin_repository.create_account("alice", "strong-password")
    core.manual_login_lease = {
        "operator_id": "super_admin",
        "operator_name": "超级管理员",
        "expires_at": "2026-08-05T12:03:00+08:00",
    }
    session_token = client.post(
        "/api/auth/login", json={"username": "alice", "password": "strong-password"}
    ).json()["session_token"]

    response = client.post(
        "/api/login/cancel",
        headers={"X-Admin-Session": session_token, "Idempotency-Key": "cancel-login"},
    )

    assert response.status_code == 202
    assert core.commands[-1] == "cancel_auth"


def test_only_login_operator_can_open_console(client, admin_repository, core):
    account = admin_repository.create_account("alice", "strong-password")
    core.manual_login_lease = {
        "operator_id": "super_admin",
        "operator_name": "超级管理员",
        "expires_at": "2026-08-05T12:03:00+08:00",
    }
    session_token = client.post(
        "/api/auth/login", json={"username": "alice", "password": "strong-password"}
    ).json()["session_token"]

    response = client.post("/api/session", headers={"X-Admin-Session": session_token})

    assert response.status_code == 409
    assert account.username == "alice"


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


def test_admin_proxies_paginated_employee_and_item_pages(client, headers, core):
    core.employees = [
        {
            "platform_id": f"user-{index}",
            "display_name": f"员工{index}",
            "balance": 5,
            "joined_at": "2026-08-05T09:00:00+08:00",
        }
        for index in range(21)
    ]
    core.items = [
        {
            "name": f"午休券{index}",
            "description": "可安心休息十分钟。",
            "price": 5,
            "stock": 1,
            "enabled": True,
        }
        for index in range(21)
    ]

    employees = client.get("/api/game/users?page=2&page_size=20", headers=headers)
    items = client.get("/api/game/items?page=2&page_size=20", headers=headers)

    assert employees.json()["page"] == 2
    assert employees.json()["items"][0]["display_name"] == "员工20"
    assert items.json()["page_size"] == 20
    assert items.json()["items"][0]["name"] == "午休券20"


def test_admin_dashboard_exposes_pagination_and_mutation_controls(client):
    page = client.get("/").text
    script = client.get("/static/admin.js").text

    assert 'id="employee-pagination"' in page
    assert 'id="shop-pagination"' in page
    assert "runMutation" in script
    assert "renderPagination" in script
    assert "/api/game/users?page=${page}&page_size=${pageSize}" in script
    assert "/api/game/items?page=${page}&page_size=${pageSize}" in script
    assert '"保存中…"' in script
    assert '"上架中…"' in script
    assert "请填写场景名称和开场文案" in script


def test_admin_accepts_the_browser_item_form_json_body(client, headers):
    response = client.post(
        "/api/game/items",
        headers={**headers, "Content-Type": "text/plain;charset=UTF-8"},
        content=(
            '{"name":"午休券","description":"可安心休息十分钟。",'
            '"price":5,"stock":1}'
        ),
    )

    assert response.status_code == 201
    assert response.json()["name"] == "午休券"


def test_admin_proxies_game_settings(client, headers, core):
    initial = client.get("/api/game/settings", headers=headers)
    updated = client.patch(
        "/api/game/settings",
        headers=headers,
        json={"currency_name": "工分", "onboarding_bonus": 3, "checkin_reward": 7},
    )

    assert initial.json()["currency_name"] == "摸鱼币"
    assert updated.json()["currency_name"] == "工分"
    assert updated.json()["version"] == 1
    assert core.game_settings["checkin_reward"] == 7


def test_admin_rejects_stale_configuration_write(client, headers):
    first = client.patch(
        "/api/game/settings",
        headers=headers,
        json={"currency_name": "工分", "onboarding_bonus": 3, "checkin_reward": 7},
    )
    second = client.patch(
        "/api/game/settings",
        headers={**headers, "Idempotency-Key": "stale-settings"},
        json={"currency_name": "银元", "onboarding_bonus": 3, "checkin_reward": 7},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["version"] == 1


def test_admin_proxies_activity_settings(client, headers, core):
    initial = client.get("/api/game/activity-settings", headers=headers)
    updated = client.patch(
        "/api/game/activity-settings",
        headers=headers,
        json={
            "rules": core.activity_settings["rules"],
            "report_times": ["09:30", "18:00"],
        },
    )

    assert initial.json()["report_times"] == ["12:00", "16:00", "20:00", "23:59"]
    assert updated.json()["report_times"] == ["09:30", "18:00"]


def test_admin_page_exposes_activity_settings_modal(client):
    page = client.get("/").text
    script = client.get("/static/admin.js").text

    assert 'id="edit-activity-settings"' in page
    assert 'id="activity-settings-modal"' in page
    assert "openActivitySettingsModal" in script
    assert "/api/game/activity-settings" in script


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


def test_command_library_keeps_template_scenarios_inside_a_modal(client):
    """Fails if scenario cards return to the command-library main page."""
    page = client.get("/")
    script = client.get("/static/admin.js")

    assert 'id="template-modal"' in page.text
    assert 'id="template-modal-scenario"' in page.text
    assert 'id="template-modal-input"' in page.text
    assert "data-command-templates" in script.text
    assert "data-variable" in script.text
    assert "closeTemplateModal" in script.text
    assert "/api/game/command-templates" in script.text


def test_admin_page_exposes_game_settings_navigation_and_modal(client):
    page = client.get("/").text
    script = client.get("/static/admin.js").text

    assert 'data-view="settings"' in page
    assert 'id="settings-view"' in page
    assert 'id="settings-modal"' in page
    assert "/api/game/settings" in script


def test_gameplay_settings_is_not_hidden_with_the_overview_view(client):
    """Fails if the gameplay settings view is nested inside the overview view."""

    class ViewParentParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []
            self.parents = {}

        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if attributes.get("id") == "settings-view":
                self.parents["settings-view"] = self.stack[-1] if self.stack else None
            self.stack.append((tag, attributes))

        def handle_endtag(self, tag):
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index][0] == tag:
                    del self.stack[index:]
                    return

    parser = ViewParentParser()
    parser.feed(client.get("/").text)

    assert parser.parents["settings-view"] == (
        "div",
        {"class": "dashboard-views"},
    )


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
    core.manual_login_lease = {
        "operator_id": "super_admin",
        "operator_name": "超级管理员",
        "expires_at": "2026-08-05T12:03:00+08:00",
    }

    response = client.post("/api/login/finish", headers=headers)

    assert response.status_code == 202
    assert core.commands == ["finish_auth"]


def test_login_console_is_proxied_only_during_auth(
    client, headers, core, console
):
    blocked = client.get("/login-console", headers=headers)
    core.login_state_value = "auth_in_progress"
    assign_super_login_lease(core)
    client.post("/api/session", headers=headers)
    allowed = client.get("/login-console")

    assert blocked.status_code == 401
    assert allowed.status_code == 200
    assert 'src="app/ui.js"' in allowed.text
    assert console.requests == ["/vnc.html"]


def test_console_rejects_token_without_current_console_session(client, headers, core):
    core.login_state_value = "auth_in_progress"
    assign_super_login_lease(core)

    response = client.get("/login-console", headers=headers)

    assert response.status_code == 401


def test_admin_token_creates_httponly_console_session_without_url_secret(
    client, headers, core
):
    core.manual_login_lease = {
        "operator_id": "super_admin",
        "operator_name": "超级管理员",
        "expires_at": "2026-08-05T12:03:00+08:00",
    }
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
    core.manual_login_lease = {
        "operator_id": "super_admin",
        "operator_name": "超级管理员",
        "expires_at": "2026-08-05T12:03:00+08:00",
    }
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
    assign_super_login_lease(core)
    client.post("/api/session", headers=headers)
    core.login_state_value = "auth_in_progress"

    response = client.get("/login-console/?path=websockify")

    assert response.status_code == 200
    assert response.url.params["path"] == "login-console/websockify"


def test_console_root_redirects_duplicate_attacker_first_path(
    client, headers, core, console
):
    assign_super_login_lease(core)
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
    assign_super_login_lease(core)
    client.post("/api/session", headers=headers)
    core.login_state_value = "ready"

    assert client.get("/login-console/app/ui.js").status_code == 409


def test_console_asset_proxy_preserves_upstream_not_found(client, headers, core):
    assign_super_login_lease(core)
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

    assign_super_login_lease(core)
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


def test_admin_configures_random_event_settings_and_creates_scene(client, headers, core):
    settings = client.patch(
        "/api/game/random-events/settings",
        headers=headers,
        json={
            "start_time": "10:00",
            "end_time": "24:00",
            "events_per_day": 2,
            "minimum_interval_minutes": 90,
            "signup_timeout_minutes": 15,
            "reminder_interval_minutes": 5,
        },
    )
    scene = client.post(
        "/api/game/random-events/scenes",
        headers={**headers, "Idempotency-Key": "scene-create", "If-Match": "1"},
        json={
            "name": "茶水间",
            "signup_text": "今天的公司茶水间随机事件来啦，快点加入吧。",
            "openings": ["咖啡机突然发出一声巨响。"],
            "reward": 4,
            "target_rounds": 10,
            "seats": [{"role": "员工", "capacity": 2}],
        },
    )

    assert settings.status_code == 200
    assert settings.json()["version"] == 1
    assert scene.status_code == 201
    assert scene.json()["name"] == "茶水间"
    assert scene.json()["openings"] == ["咖啡机突然发出一声巨响。"]
    assert client.get("/api/game/random-events/scenes", headers=headers).json()["items"]
