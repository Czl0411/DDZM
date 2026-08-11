from datetime import UTC, datetime
import json

import httpx

from dzmm_bot.runtime.contracts import DirectChatRoom, InboundMessage, LoginState


def test_core_client_heartbeat_reports_actual_and_returns_desired_listener_state():
    from dzmm_bot.browser.core_client import CoreClient

    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["path"] = request.url.path
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "worker_id": "worker-a",
                "login_state": "ready",
                "recorded_at": "2026-08-05T20:00:00+08:00",
                "listening": True,
                "listening_desired": False,
            },
        )

    client = CoreClient(
        "http://core.test",
        "token",
        client=httpx.Client(
            base_url="http://core.test",
            transport=httpx.MockTransport(handler),
        ),
    )
    now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)

    desired = client.heartbeat("worker-a", LoginState.READY, True, now)

    assert observed == {
        "path": "/internal/heartbeat",
        "payload": {
            "worker_id": "worker-a",
            "login_state": "ready",
            "listening": True,
            "recorded_at": now.isoformat(),
        },
    }
    assert desired is False


def test_core_client_runs_daily_jobs():
    from dzmm_bot.browser.core_client import CoreClient

    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["method"] = request.method
        observed["path"] = request.url.path
        observed["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"accepted": True})

    client = CoreClient(
        "http://core.test",
        "token",
        client=httpx.Client(
            base_url="http://core.test",
            transport=httpx.MockTransport(handler),
        ),
    )
    now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)

    client.run_daily_jobs(now)

    assert observed == {
        "method": "POST",
        "path": "/internal/daily-jobs/run",
        "payload": {"now": now.isoformat()},
    }


def test_core_client_syncs_discovered_direct_chatrooms():
    from dzmm_bot.browser.core_client import CoreClient

    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["path"] = request.url.path
        observed["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"accepted": True})

    client = CoreClient(
        "http://core.test",
        "token",
        client=httpx.Client(
            base_url="http://core.test",
            transport=httpx.MockTransport(handler),
        ),
    )
    now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)

    client.sync_direct_chats([DirectChatRoom("employee-1", "direct-1")], now)

    assert observed == {
        "path": "/internal/direct-chats/sync",
        "payload": {
            "rooms": [{"platform_user_id": "employee-1", "chatroom_id": "direct-1"}],
            "now": now.isoformat(),
        },
    }


def test_core_client_releases_a_timed_out_outbound_for_immediate_retry():
    from dzmm_bot.browser.core_client import CoreClient
    from uuid import UUID

    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["path"] = request.url.path
        observed["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"accepted": True})

    client = CoreClient(
        "http://core.test",
        "token",
        client=httpx.Client(
            base_url="http://core.test",
            transport=httpx.MockTransport(handler),
        ),
    )
    message_id = UUID("00000000-0000-0000-0000-000000000001")
    lease_token = UUID("00000000-0000-0000-0000-000000000002")
    now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)

    client.release_outbound(message_id, "worker-a", lease_token, now)

    assert observed == {
        "path": f"/internal/outbound/{message_id}/retry",
        "payload": {
            "worker_id": "worker-a",
            "lease_token": str(lease_token),
            "now": now.isoformat(),
        },
    }


def test_core_client_serializes_provenance_and_fetches_direct_inbound_rooms():
    from dzmm_bot.browser.core_client import CoreClient

    observed = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
        if request.method == "GET":
            return httpx.Response(200, json={"chatroom_ids": ["direct-1"]})
        return httpx.Response(200, json={"accepted": True})

    client = CoreClient(
        "http://core.test",
        "token",
        client=httpx.Client(
            base_url="http://core.test",
            transport=httpx.MockTransport(handler),
        ),
    )
    now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)

    rooms = client.direct_inbound_chatroom_ids()
    client.submit_inbound(
        InboundMessage(
            "direct-message-1", "employee-1", "/报数 29", now,
            source_type="direct", chatroom_id="direct-1",
        )
    )

    assert rooms == ("direct-1",)
    assert observed == [
        ("GET", "/internal/direct-inbound/rooms", None),
        (
            "POST",
            "/internal/inbound",
            {
                "platform_message_id": "direct-message-1",
                "sender_platform_id": "employee-1",
                "content": "/报数 29",
                "received_at": now.isoformat(),
                "source_type": "direct",
                "chatroom_id": "direct-1",
            },
        ),
    ]
