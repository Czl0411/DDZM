from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
        "recorded_at": (NOW - timedelta(seconds=12)).isoformat().replace(
            "+00:00", "Z"
        ),
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
