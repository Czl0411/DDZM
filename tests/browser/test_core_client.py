from datetime import UTC, datetime
import json

import httpx

from dzmm_bot.runtime.contracts import DirectChatRoom


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
