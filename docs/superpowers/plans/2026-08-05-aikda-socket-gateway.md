# Aikda Socket Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace DOM-based Aikda group message reading and sending with Socket.IO plus authenticated history reconciliation.

**Architecture:** `BrowserSession` supplies authenticated same-origin API calls from the persistent browser page. `AikdaSocketGateway` owns a Socket.IO client, converts live events and history into `InboundMessage`, and emits `message:send` with ACK confirmation. `BrowserWorker` remains responsible for core submission, leases, and authentication state.

**Tech Stack:** Python 3.12, Playwright sync API, httpx, python-socketio client, pytest.

## Global Constraints

- Use `DZMM_CHAT_URL`’s `c` parameter as the only accepted chatroom ID.
- Use `Asia/Shanghai` for all application-facing `datetime` values.
- Do not inspect or persist browser cookies, profile files, or access tokens.
- Do not use DOM message parsing or DOM send as a fallback.
- Confirm an outbound message only after Socket.IO ACK `success: true`.

---

### Task 1: Add isolated Socket.IO protocol gateway

**Files:**
- Create: `src/dzmm_bot/browser/aikda_socket.py`
- Modify: `pyproject.toml`
- Test: `tests/browser/test_aikda_socket.py`

**Interfaces:**
- Consumes: `token_provider() -> str`, `request(method: str, path: str, input: dict | None) -> dict`, and a `socketio.Client`-compatible factory.
- Produces: `AikdaSocketGateway(chat_url, token_provider, request, socket_factory, clock)` implementing `read_new()`, `send(text)`, `is_authenticated()`, and `close()`.

- [x] **Step 1: Write failing gateway tests**

```python
def test_live_target_room_text_event_is_read_once():
    socket.trigger("message:new", {"chatroomId": "room-1", "message": message("m-1", "u-1", "/余额")})
    assert gateway.read_new() == [InboundMessage("m-1", "u-1", "/余额", SHANGHAI_TIME)]

def test_self_and_other_room_events_are_ignored():
    socket.trigger("message:new", {"chatroomId": "room-1", "message": message("m-self", "bot-1", "/余额")})
    socket.trigger("message:new", {"chatroomId": "room-2", "message": message("m-other", "u-1", "/余额")})
    assert gateway.read_new() == []

def test_history_reconciles_unseen_text_messages_in_timestamp_order():
    request.messages = [message("m-2", "u-2", "/打卡", "2026-08-05T04:00:01Z"), message("m-1", "u-1", "/余额", "2026-08-05T04:00:00Z")]
    assert [item.platform_message_id for item in gateway.read_new()] == ["m-1", "m-2"]

def test_send_requires_successful_ack():
    socket.call_result = {"success": True}
    assert gateway.send("余额：5 摸鱼币")
    assert socket.calls[0][0] == "message:send"
```

- [x] **Step 2: Run the targeted tests and verify they fail**

Run: `pytest tests/browser/test_aikda_socket.py -v`

Expected: FAIL because `dzmm_bot.browser.aikda_socket` does not exist.

- [x] **Step 3: Add the minimal dependency and gateway implementation**

Add `python-socketio[client]>=5,<6` to `[project].dependencies`. Implement:

The implementation exposes `AikdaSocketGateway(chat_url, token_provider,
request, socket_factory, clock)`. Its `read_new()` returns
`list[InboundMessage]`; `send(text)` returns the generated platform message
ID; `is_authenticated()` returns a boolean; and `close()` disconnects the
Socket.IO client.

Use `socket.connect(origin, socketio_path="ws/matching", auth={"token": token}, transports=["websocket", "polling"])`; register `message:new`; run `user.getMe` and `chatroom.getMessages` through the supplied request callable; convert only `content.type == "text"`; create send IDs with `uuid4()` and timestamps with the injected clock.

- [x] **Step 4: Run gateway tests and verify they pass**

Run: `pytest tests/browser/test_aikda_socket.py -v`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add pyproject.toml src/dzmm_bot/browser/aikda_socket.py tests/browser/test_aikda_socket.py
git commit -m "feat: add Aikda Socket.IO gateway"
```

### Task 2: Provide authenticated browser API access

**Files:**
- Modify: `src/dzmm_bot/browser/session.py`
- Modify: `tests/browser/test_session.py`

**Interfaces:**
- Consumes: the authenticated active Playwright page and configured chat URL.
- Produces: `BrowserSession.start_headless()` / `attach_existing()` returning the Socket gateway rather than the DOM gateway.

- [x] **Step 1: Write failing session tests**

```python
def test_session_supplies_same_origin_token_to_socket_gateway():
    gateway = session.start_headless()
    assert gateway.token_provider() == "short-lived-token"

def test_session_uses_group_id_from_configured_chat_url():
    session.start_headless()
    assert socket_gateway.chatroom_id == "group-1"
```

- [x] **Step 2: Run the targeted tests and verify they fail**

Run: `pytest tests/browser/test_session.py -v`

Expected: FAIL because the session still returns `_PlaywrightGateway`.

- [x] **Step 3: Implement same-origin token and tRPC bridge**

Keep browser launch, login state, and group navigation unchanged. Replace
`_PlaywrightGateway` creation with an `AikdaSocketGateway` constructed from:

```python
def token_provider() -> str:
    return active_page.evaluate("""async () => {
        const response = await fetch('/api/auth/token');
        const body = await response.json();
        if (!response.ok || !body.access_token) throw new Error('token unavailable');
        return body.access_token;
    }""")
```

and a page-evaluated same-origin `fetch` helper that encodes tRPC `input`,
checks `response.ok`, and returns JSON. Do not return cookies or browser
storage values to Python. Remove `DzmmMessageSource` and DOM textarea usage
from this path.

- [x] **Step 4: Run session tests and verify they pass**

Run: `pytest tests/browser/test_session.py -v`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/dzmm_bot/browser/session.py tests/browser/test_session.py
git commit -m "feat: bridge browser authentication to socket gateway"
```

### Task 3: Preserve Worker delivery and lifecycle guarantees

**Files:**
- Modify: `src/dzmm_bot/browser/worker.py`
- Modify: `tests/browser/test_worker.py`

**Interfaces:**
- Consumes: `ChatGateway.read_new()` and `ChatGateway.send()` exceptions from the Socket gateway.
- Produces: core inbound submission exactly once per Worker process and outbound confirmation only after ACK-backed `send()` succeeds.

- [ ] **Step 1: Write failing Worker tests**

```python
def test_worker_retries_unconfirmed_outbound_after_socket_ack_failure(context):
    worker, gateway, _, _, core, _ = context
    core.pending = [OutboundClaim(OUTBOUND_ID, "in-1", "reply", LEASE)]
    gateway.send_error = RuntimeError("socket acknowledgement failed")
    worker.run_once()
    assert core.confirmed == []

def test_worker_submits_history_and_live_duplicates_once(context):
    gateway.messages = [InboundMessage("m-1", "u-1", "/余额", NOW)]
    worker.run_once()
    worker.run_once()
    assert core.submitted_ids == ["m-1"]
```

- [ ] **Step 2: Run Worker tests and verify the intended failure**

Run: `pytest tests/browser/test_worker.py -v`

Expected: the ACK-specific test fails until socket errors are surfaced by the gateway contract.

- [ ] **Step 3: Make only the contract-compatible Worker changes needed**

Keep command, login desktop, heartbeat, lease, and core-client behavior
unchanged. Amend error handling only if required to mark a failed Socket
gateway unauthenticated before the next loop; do not add a DOM fallback.

- [ ] **Step 4: Run the full test suite**

Run: `pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/browser/worker.py tests/browser/test_worker.py
git commit -m "fix: preserve delivery guarantees for socket gateway"
```

### Task 4: Deploy without destroying the active browser session

**Files:**
- Modify only if deployment needs a declared dependency update: `pyproject.toml`

- [ ] **Step 1: Run package and test verification**

Run: `python -m pip install -e '.[test]' && pytest -q`

Expected: package installs and all tests pass.

- [ ] **Step 2: Deploy code and migrate normally**

Run the existing release deployment script, then restart only `dzmm-core` and
`dzmm-admin-web` first. Confirm the remote browser worker remains attached to
the existing persistent profile before restarting it.

- [ ] **Step 3: Verify the live adapter**

Check Worker logs for successful Socket.IO `message:joined`, target room ID,
and history reconciliation. Send one user-approved group command and confirm
exactly one inbound record and one ACK-confirmed outbound reply.

- [ ] **Step 4: Commit any deployment-only source change**

```bash
git status --short
```

Expected: no uncommitted source changes; `docs/HANDOFF.md` remains untouched.
