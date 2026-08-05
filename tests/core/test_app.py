from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from dzmm_bot.core.schema import OutboundRecord, WorkerCommandRecord


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


@dataclass
class AppContext:
    client: TestClient
    repository: object
    engine: object
    session_factory: object


@pytest.fixture
def app_context():
    from dzmm_bot.core.app import create_app
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import Base

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    repository = CoreRepository(session_factory)
    app = create_app(repository, "test-core-token", clock=lambda: NOW)
    return AppContext(TestClient(app), repository, engine, session_factory)


@pytest.fixture
def client(app_context):
    return app_context.client


@pytest.fixture
def headers():
    return {"X-Core-Token": "test-core-token"}


@pytest.fixture
def payload():
    return {
        "platform_message_id": "platform-1",
        "sender_platform_id": "sender-1",
        "content": "hello",
        "received_at": NOW.isoformat(),
    }


def test_internal_inbound_rejects_missing_core_token(client, payload):
    assert client.post("/internal/inbound", json=payload).status_code == 401


def test_internal_inbound_is_idempotent(client, headers, payload):
    first = client.post("/internal/inbound", headers=headers, json=payload)
    second = client.post("/internal/inbound", headers=headers, json=payload)

    assert first.status_code == 200
    assert first.json()["accepted"] is True
    assert second.status_code == 200
    assert second.json()["accepted"] is False
    assert second.json()["message_id"] == first.json()["message_id"]


def test_internal_inbound_executes_enabled_group_commands(app_context, headers, payload):
    payload["content"] = "/入职 小明"

    response = app_context.client.post(
        "/internal/inbound", headers=headers, json=payload
    )

    assert response.status_code == 200
    with app_context.session_factory() as session:
        reply = session.scalar(select(OutboundRecord.text))
    assert reply == "小明，欢迎入职摸鱼公司。当前余额：0 摸鱼币。"


def test_heartbeat_response_uses_beijing_time(client, headers):
    response = client.post(
        "/internal/heartbeat",
        headers=headers,
        json={
            "worker_id": "worker-a",
            "login_state": "ready",
            "recorded_at": NOW.isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.json()["recorded_at"] == "2026-08-04T20:00:00+08:00"


def test_manual_login_api_allows_one_operator_and_any_cancellation(client, headers):
    started = client.post(
        "/internal/admin/login/start",
        headers=headers,
        json={"operator_id": "alice-id", "operator_name": "alice"},
    )
    blocked = client.post(
        "/internal/admin/login/start",
        headers=headers,
        json={"operator_id": "bob-id", "operator_name": "bob"},
    )
    cancelled = client.post("/internal/admin/login/cancel", headers=headers)

    assert started.status_code == 200
    assert started.json()["operator_name"] == "alice"
    assert blocked.status_code == 409
    assert cancelled.status_code == 200
    assert client.get("/internal/admin/login/lease", headers=headers).json() is None


def test_game_management_lists_commands_employees_and_shop_items(client, headers):
    commands = client.get("/internal/game/commands", headers=headers)
    disabled = client.patch(
        "/internal/game/commands",
        headers=headers,
        json={"command": "/打卡", "enabled": False},
    )
    employees = client.get("/internal/game/users", headers=headers)
    created_item = client.post(
        "/internal/game/items",
        headers=headers,
        json={"name": "工位午睡券", "description": "眯十分钟。", "price": 5, "stock": 3},
    )
    items = client.get("/internal/game/items", headers=headers)

    assert commands.status_code == 200
    assert {record["command"] for record in commands.json()} == {
        "/入职", "/我的物品", "/打卡", "/余额", "/我", "/商店", "/帮助", "/加入", "/退出"
    }
    assert disabled.json()["enabled"] is False
    assert employees.json() == {
        "items": [],
        "page": 1,
        "page_size": 20,
        "total": 0,
        "pages": 0,
    }
    assert created_item.status_code == 201
    assert items.json() == {
        "items": [
            {
                "name": "工位午睡券",
                "description": "眯十分钟。",
                "price": 5,
                "stock": 3,
                "enabled": True,
            }
        ],
        "page": 1,
        "page_size": 20,
        "total": 1,
        "pages": 1,
    }


def test_game_management_returns_paginated_employees_and_items(
    app_context, client, headers
):
    for index in range(21):
        app_context.repository.create_user(
            f"u-{index}", f"员工{index}", NOW + timedelta(minutes=index), 0
        )
        app_context.repository.add_item(f"物品{index}", "说明", index, 1)

    employees = client.get("/internal/game/users?page=2&page_size=20", headers=headers)
    items = client.get("/internal/game/items?page=2&page_size=20", headers=headers)

    assert employees.status_code == 200
    assert employees.json()["page"] == 2
    assert employees.json()["page_size"] == 20
    assert employees.json()["total"] == 21
    assert employees.json()["pages"] == 2
    assert len(employees.json()["items"]) == 1
    assert items.status_code == 200
    assert items.json()["total"] == 21
    assert len(items.json()["items"]) == 1


def test_game_settings_can_be_read_and_updated(client, headers):
    initial = client.get("/internal/game/settings", headers=headers)
    updated = client.patch(
        "/internal/game/settings",
        headers=headers,
        json={"currency_name": "工分", "onboarding_bonus": 3, "checkin_reward": 7},
    )

    assert initial.json() == {
        "currency_name": "摸鱼币",
        "onboarding_bonus": 0,
        "checkin_reward": 5,
        "reset_time_label": "北京时间 00:00",
    }
    assert updated.json() == {
        "currency_name": "工分",
        "onboarding_bonus": 3,
        "checkin_reward": 7,
        "reset_time_label": "北京时间 00:00",
    }


def test_activity_settings_can_be_read_and_updated(client, headers):
    initial = client.get("/internal/game/activity-settings", headers=headers)
    updated = client.patch(
        "/internal/game/activity-settings",
        headers=headers,
        json={
            "rules": [
                {
                    "level": level,
                    "character_threshold": level * 10,
                    "reward": level,
                }
                for level in range(1, 11)
            ],
            "report_times": ["09:30", "18:00"],
        },
    )

    assert initial.status_code == 200
    assert initial.json()["report_times"] == ["12:00", "16:00", "20:00", "23:59"]
    assert updated.status_code == 200
    assert updated.json()["report_times"] == ["09:30", "18:00"]


def test_daily_jobs_require_the_core_token(client, headers):
    assert client.post("/internal/daily-jobs/run", json={"now": NOW.isoformat()}).status_code == 401

    response = client.post(
        "/internal/daily-jobs/run", headers=headers, json={"now": NOW.isoformat()}
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": True}


def test_game_commands_list_templates_and_update_a_valid_template(client, headers):
    commands = client.get("/internal/game/commands", headers=headers).json()
    balance = next(command for command in commands if command["command"] == "/余额")

    response = client.patch(
        "/internal/game/command-templates",
        headers=headers,
        json={
            "command": "/余额",
            "scenario": "shown",
            "template": "{昵称}：{余额}",
        },
    )

    assert balance["templates"] == [
        {
            "scenario": "shown",
            "label": "查询成功",
            "template": "{昵称}，当前余额：{余额} {货币}。",
            "variables": ["{昵称}", "{余额}", "{货币}", "{日期}"],
        },
        {
            "scenario": "not_joined",
            "label": "未入职",
            "template": "请先用 /入职 名字 加入摸鱼公司。",
            "variables": ["{日期}"],
        },
    ]
    assert response.status_code == 200
    assert response.json()["template"] == "{昵称}：{余额}"


def test_game_command_template_rejects_an_unsupported_variable(client, headers):
    response = client.patch(
        "/internal/game/command-templates",
        headers=headers,
        json={
            "command": "/余额",
            "scenario": "shown",
            "template": "{商店列表}",
        },
    )

    assert response.status_code == 422


def test_core_server_factory_enforces_local_settings_port(app_context):
    from dzmm_bot.core.app import create_server
    from dzmm_bot.runtime.settings import Settings

    settings = Settings(
        database_url="postgresql+psycopg://dzmm@localhost/dzmm",
        core_token="test-core-token",
        admin_token=None,
        browser_profile=Path("/var/lib/dzmm/browser"),
        login_url=None,
        core_api_port=18120,
        browser_cdp_port=19222,
        admin_web_port=18090,
        novnc_port=16080,
    )

    server = create_server(app_context.repository, settings)

    assert server.config.host == "127.0.0.1"
    assert server.config.port == settings.core_api_port


def test_database_backed_identifiers_reject_more_than_255_characters(
    client, headers, payload
):
    oversized = "x" * 256
    payload["platform_message_id"] = oversized

    inbound = client.post("/internal/inbound", headers=headers, json=payload)
    heartbeat = client.post(
        "/internal/heartbeat",
        headers=headers,
        json={
            "worker_id": oversized,
            "login_state": "ready",
            "recorded_at": NOW.isoformat(),
        },
    )
    sent = client.post(
        "/internal/outbound/00000000-0000-0000-0000-000000000000/sent",
        headers=headers,
        json={
            "worker_id": "worker-a",
            "lease_token": "00000000-0000-0000-0000-000000000000",
            "platform_sent_id": oversized,
            "now": NOW.isoformat(),
        },
    )

    assert inbound.status_code == 422
    assert heartbeat.status_code == 422
    assert sent.status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/internal/outbound/claim"),
        ("post", "/internal/outbound/00000000-0000-0000-0000-000000000000/sent"),
        ("post", "/internal/heartbeat"),
        ("get", "/internal/login-state"),
        ("get", "/internal/status"),
        ("get", "/internal/game/activity-settings"),
        ("patch", "/internal/game/activity-settings"),
        ("patch", "/internal/game/command-templates"),
        ("post", "/internal/daily-jobs/run"),
        ("post", "/internal/worker-commands"),
        ("post", "/internal/worker-commands/claim"),
        (
            "post",
            "/internal/worker-commands/00000000-0000-0000-0000-000000000000/complete",
        ),
    ],
)
def test_every_internal_route_requires_core_token(client, method, path):
    assert client.request(method, path, json={}).status_code == 401


def test_outbound_claim_and_fenced_sent_acknowledgement(
    app_context, headers, payload
):
    inbound = app_context.client.post(
        "/internal/inbound", headers=headers, json=payload
    ).json()
    outbound = app_context.repository.enqueue_outbound(
        inbound["message_id"], "reply"
    )

    first = app_context.client.post(
        "/internal/outbound/claim",
        headers=headers,
        json={"worker_id": "worker-a", "now": NOW.isoformat(), "lease_seconds": 30},
    ).json()
    second = app_context.client.post(
        "/internal/outbound/claim",
        headers=headers,
        json={
            "worker_id": "worker-b",
            "now": (NOW + timedelta(seconds=31)).isoformat(),
            "lease_seconds": 30,
        },
    ).json()

    stale = app_context.client.post(
        f"/internal/outbound/{outbound.id}/sent",
        headers=headers,
        json={
            "worker_id": "worker-a",
            "lease_token": first["lease_token"],
            "platform_sent_id": "stale-send",
            "now": (NOW + timedelta(seconds=32)).isoformat(),
        },
    )
    with app_context.session_factory() as session:
        persisted_after_stale = session.scalar(
            select(OutboundRecord).where(OutboundRecord.id == outbound.id)
        )
        assert persisted_after_stale.status == "leased"
        assert persisted_after_stale.lease_worker_id == "worker-b"
        assert persisted_after_stale.lease_token == UUID(second["lease_token"])
        assert persisted_after_stale.platform_sent_id is None

    fresh = app_context.client.post(
        f"/internal/outbound/{outbound.id}/sent",
        headers=headers,
        json={
            "worker_id": "worker-b",
            "lease_token": second["lease_token"],
            "platform_sent_id": "sent-1",
            "now": (NOW + timedelta(seconds=32)).isoformat(),
        },
    )

    assert first["id"] == str(outbound.id)
    assert second["id"] == str(outbound.id)
    assert stale.status_code == 200
    assert stale.json() == {"accepted": False}
    assert fresh.json() == {"accepted": True}
    assert (
        app_context.client.post(
            "/internal/outbound/claim",
            headers=headers,
            json={
                "worker_id": "worker-c",
                "now": (NOW + timedelta(seconds=63)).isoformat(),
                "lease_seconds": 30,
            },
        ).json()
        is None
    )


def test_outbound_sent_requires_all_fencing_fields(client, headers):
    response = client.post(
        "/internal/outbound/00000000-0000-0000-0000-000000000000/sent",
        headers=headers,
        json={"platform_sent_id": "sent-1"},
    )

    assert response.status_code == 422
    assert {error["loc"][-1] for error in response.json()["detail"]} == {
        "worker_id",
        "lease_token",
        "now",
    }


def test_heartbeat_updates_login_state_and_health_age(app_context, headers):
    before = app_context.client.get("/healthz")
    heartbeat = app_context.client.post(
        "/internal/heartbeat",
        headers=headers,
        json={
            "worker_id": "worker-a",
            "login_state": "ready",
            "recorded_at": (NOW - timedelta(seconds=12)).isoformat(),
        },
    )
    login_state = app_context.client.get(
        "/internal/login-state", headers=headers
    )
    after = app_context.client.get("/healthz")

    assert before.json() == {
        "database_available": True,
        "latest_worker_heartbeat_age_seconds": None,
    }
    assert heartbeat.status_code == 200
    assert heartbeat.json() == {
        "worker_id": "worker-a",
        "login_state": "ready",
        "recorded_at": "2026-08-04T19:59:48+08:00",
    }
    assert login_state.json() == heartbeat.json()
    assert after.json() == {
        "database_available": True,
        "latest_worker_heartbeat_age_seconds": 12.0,
    }
    assert "token" not in after.text.lower()


def test_health_reports_database_unavailability_without_details(app_context):
    app_context.engine.dispose()

    response = app_context.client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {
        "database_available": False,
        "latest_worker_heartbeat_age_seconds": None,
    }


def test_internal_status_returns_real_queue_counts_and_latest_heartbeat(
    app_context, headers, payload
):
    inbound = app_context.client.post(
        "/internal/inbound", headers=headers, json=payload
    ).json()
    app_context.repository.enqueue_outbound(inbound["message_id"], "reply")
    app_context.repository.enqueue_worker_command("pause_listening")
    app_context.client.post(
        "/internal/heartbeat",
        headers=headers,
        json={
            "worker_id": "worker-a",
            "login_state": "auth_required",
            "recorded_at": NOW.isoformat(),
        },
    )

    response = app_context.client.get("/internal/status", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "state": "auth_required",
        "last_heartbeat": "2026-08-04T20:00:00+08:00",
        "queue_counts": {
            "inbound_accepted": 1,
            "outbound_pending": 1,
            "worker_commands_pending": 1,
        },
    }


@pytest.mark.parametrize(
    "command",
    [
        "pause_listening",
        "resume_listening",
        "restart_browser",
        "start_auth",
        "finish_auth",
    ],
)
def test_allowed_worker_command_can_be_enqueued(client, headers, command):
    response = client.post(
        "/internal/worker-commands", headers=headers, json={"command": command}
    )

    assert response.status_code == 200
    assert response.json()["command"] == command
    assert response.json()["status"] == "pending"


def test_unknown_worker_command_is_rejected(client, headers):
    response = client.post(
        "/internal/worker-commands",
        headers=headers,
        json={"command": "delete_profile"},
    )

    assert response.status_code == 422


def test_worker_command_claim_and_fenced_completion(app_context, headers):
    command = app_context.client.post(
        "/internal/worker-commands",
        headers=headers,
        json={"command": "restart_browser"},
    ).json()
    first = app_context.client.post(
        "/internal/worker-commands/claim",
        headers=headers,
        json={"worker_id": "worker-a", "now": NOW.isoformat(), "lease_seconds": 30},
    ).json()
    second = app_context.client.post(
        "/internal/worker-commands/claim",
        headers=headers,
        json={
            "worker_id": "worker-b",
            "now": (NOW + timedelta(seconds=31)).isoformat(),
            "lease_seconds": 30,
        },
    ).json()

    stale = app_context.client.post(
        f"/internal/worker-commands/{command['id']}/complete",
        headers=headers,
        json={
            "worker_id": "worker-a",
            "lease_token": first["lease_token"],
            "status": "completed",
            "now": (NOW + timedelta(seconds=32)).isoformat(),
        },
    )
    with app_context.session_factory() as session:
        persisted_after_stale = session.scalar(
            select(WorkerCommandRecord).where(
                WorkerCommandRecord.id == UUID(command["id"])
            )
        )
        assert persisted_after_stale.status == "leased"
        assert persisted_after_stale.lease_worker_id == "worker-b"
        assert persisted_after_stale.lease_token == UUID(second["lease_token"])
        assert persisted_after_stale.completed_at is None

    fresh = app_context.client.post(
        f"/internal/worker-commands/{command['id']}/complete",
        headers=headers,
        json={
            "worker_id": "worker-b",
            "lease_token": second["lease_token"],
            "status": "completed",
            "now": (NOW + timedelta(seconds=32)).isoformat(),
        },
    )

    assert first["id"] == command["id"]
    assert second["id"] == command["id"]
    assert stale.json() == {"accepted": False}
    assert fresh.json() == {"accepted": True}
    assert (
        app_context.client.post(
            "/internal/worker-commands/claim",
            headers=headers,
            json={
                "worker_id": "worker-c",
                "now": (NOW + timedelta(seconds=63)).isoformat(),
                "lease_seconds": 30,
            },
        ).json()
        is None
    )


def test_worker_command_completion_requires_all_fencing_fields(client, headers):
    response = client.post(
        "/internal/worker-commands/00000000-0000-0000-0000-000000000000/complete",
        headers=headers,
        json={"status": "completed"},
    )

    assert response.status_code == 422
    assert {error["loc"][-1] for error in response.json()["detail"]} == {
        "worker_id",
        "lease_token",
        "now",
    }


def test_random_event_settings_are_available_through_internal_api(client, headers):
    response = client.patch(
        "/internal/game/random-events/settings",
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

    assert response.status_code == 200
    assert response.json()["events_per_day"] == 2


def test_random_event_scene_is_created_through_internal_api(client, headers):
    response = client.post(
        "/internal/game/random-events/scenes",
        headers=headers,
        json={
            "name": "茶水间",
            "signup_text": "今天的公司茶水间随机事件来啦，快点加入吧。",
            "openings": ["咖啡机突然发出一声巨响。"],
            "reward": 4,
            "target_rounds": 10,
            "seats": [{"role": "员工", "capacity": 2}],
        },
    )

    assert response.status_code == 201
    assert response.json()["signup_text"] == "今天的公司茶水间随机事件来啦，快点加入吧。"
    assert response.json()["openings"] == ["咖啡机突然发出一声巨响。"]
    assert response.json()["seats"] == [{"role": "员工", "capacity": 2}]


def test_random_event_scene_requires_a_formal_opening(client, headers):
    response = client.post(
        "/internal/game/random-events/scenes",
        headers=headers,
        json={
            "name": "茶水间",
            "signup_text": "今天的公司茶水间随机事件来啦，快点加入吧。",
            "openings": [],
            "reward": 4,
            "target_rounds": 10,
            "seats": [{"role": "员工", "capacity": 2}],
        },
    )

    assert response.status_code == 422


def test_random_event_scene_api_returns_named_events(client, headers):
    response = client.post(
        "/internal/game/random-events/scenes",
        headers=headers,
        json={
            "name": "茶水间",
            "signup_text": "报名",
            "events": [{"name": "咖啡事故", "opening_text": "开场"}],
            "reward": 1,
            "target_rounds": 1,
            "seats": [{"role": "员工", "capacity": 1}],
        },
    )

    assert response.status_code == 201
    assert response.json()["events"] == [{"name": "咖啡事故", "opening_text": "开场"}]
