# Browser Worker Latency and Long-Message Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove full private-history scans from the outbound critical path and restore intact Bot API delivery for long group replies.

**Architecture:** Keep Playwright and Socket maintenance on the Browser Worker owner thread, but replace monolithic discovery/reconciliation with one-request maintenance steps that run after outbound scheduling. At Core enqueue time, strip the reply reference only for Bot-eligible long group replies so they remain one record and deterministically select the Bot API transport.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, python-socketio, Playwright, pytest.

## Global Constraints

- A main-loop maintenance step performs at most one `chat.listAll` or `chatroom.getMessages` request.
- Playwright and Socket reconnect operations stay on the owner thread.
- Group text over 1000 characters or over 10 newline characters uses Bot API when Bot support is configured.
- Bot-delivered long group text has no reply reference; short group replies retain their reference.
- Direct messages, recalled messages, and non-group deliveries never switch to Bot API.
- No database migration, environment variable, service, or message broker is added.

---

### Task 1: Restore deterministic long-message routing

**Files:**
- Modify: `src/dzmm_bot/core/repository.py:12160-12325`
- Modify: `tests/core/test_repository.py:5830-5900`
- Modify: `tests/browser/test_worker.py:685-785`

**Interfaces:**
- Consumes: `requires_bot_group_sender(text: str) -> bool` and `CoreRepository(..., preserve_long_group_messages=True)`.
- Produces: one unreferenced `OutboundRecord` for Bot-eligible long group replies; existing `BrowserWorker._send_outbound()` then selects `DzmmBotSender` without a new transport API.

- [ ] **Step 1: Change the repository regression test to require one intact, unreferenced long reply**

Replace the current split-behavior test with:

```python
def test_referenced_long_reply_uses_one_unreferenced_bot_record_when_enabled(
    session_factory, inbound
):
    repository = CoreRepository(session_factory, preserve_long_group_messages=True)
    stored, _ = repository.accept_inbound(inbound)

    repository.enqueue_outbound(stored.id, "字" * 1001)

    with session_factory() as session:
        records = list(session.scalars(select(OutboundRecord)))
    assert [record.text for record in records] == ["字" * 1001]
    assert [record.reference_message_id for record in records] == [None]
```

Add parameterized boundary coverage requiring 1000 characters and 10 newlines to retain references, while 1001 characters and 11 newlines produce one unreferenced record.

- [ ] **Step 2: Run the repository tests and verify the new expectation fails**

Run:

```bash
.venv/bin/pytest tests/core/test_repository.py -k 'long_reply or group_reply_intact or newline' -q
```

Expected: the 1001-character and 11-newline cases fail because the current code creates referenced chunks.

- [ ] **Step 3: Make Bot eligibility override the group reply reference before chunking**

In `CoreRepository.enqueue_outbound()`, calculate whether the complete reply is Bot-eligible using the same existing conditions as `_keeps_group_reply_intact()`:

```python
uses_bot_group_sender = (
    self._preserve_long_group_messages
    and recall_after_seconds is None
    and destination_chatroom_id is None
    and delivery_kind == "group"
    and requires_bot_group_sender(reply)
)
reference = (
    {}
    if uses_bot_group_sender
    else _outbound_reference_snapshot(inbound, destination_chatroom_id)
)
```

Keep the existing `_keeps_group_reply_intact()` call. With an empty reference and the existing Bot eligibility conditions, it keeps one record. Do not alter direct, recall, or non-group branches.

- [ ] **Step 4: Change the Browser Worker test to require referenced source text to route through Bot after Core has removed the stored reference**

Replace `test_worker_keeps_referenced_long_reply_on_socket_gateway` with a test whose long `OutboundClaim` has no reference fields and asserts:

```python
assert bot_sender.sent_to == [("group-1", text)]
assert gateway.sent == []
```

Retain the existing short, recalled, and direct-message transport tests.

- [ ] **Step 5: Run focused Core and Browser routing tests**

Run:

```bash
.venv/bin/pytest tests/core/test_repository.py -k 'long_reply or group_reply_intact or newline' tests/browser/test_worker.py -k 'bot_api or platform_limits or referenced_long or recalled_group or direct_messages' -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py tests/browser/test_worker.py
git commit -m "fix: restore bot delivery for long replies"
```

---

### Task 2: Time-slice private-room discovery and reconciliation

**Files:**
- Modify: `src/dzmm_bot/browser/session.py:10-55`
- Modify: `src/dzmm_bot/browser/aikda_socket.py:1-380`
- Modify: `src/dzmm_bot/browser/worker.py:135-176,398-412`
- Modify: `tests/browser/test_aikda_socket.py`
- Modify: `tests/browser/test_worker.py`

**Interfaces:**
- Produces: `ChatGateway.maintain_direct_chats(direct_chatroom_ids: tuple[str, ...] = ()) -> list[DirectChatRoom]`.
- Consumes: `CorePort.direct_inbound_chatroom_ids()` and `CorePort.sync_direct_chats(rooms, now)`.
- State: `AikdaSocketGateway` owns discovery and reconciliation deques plus their next-cycle timestamps; no state is shared with executor threads.

- [ ] **Step 1: Write a failing gateway test proving one maintenance step makes at most one platform request**

Create two known direct rooms and call `maintain_direct_chats(("direct-1", "direct-2"))` repeatedly. Assert that each call appends at most one of these request entries:

```python
("chat.listAll", None)
("chatroom.getMessages", {"chatroomId": room_id})
```

Also assert that the first reconciliation cycle eventually visits `room-1`, `direct-1`, and `direct-2`, and recovered messages still pass through the existing ID de-duplication.

- [ ] **Step 2: Write a failing gateway test proving known private rooms are not re-read by discovery**

Configure `chat.listAll` with two known room IDs and one new room ID. Pass the known IDs to `maintain_direct_chats()`, advance maintenance until discovery returns a mapping, and assert that `chatroom.getMessages` was called only for the new room during discovery.

- [ ] **Step 3: Run the new gateway tests and verify they fail because the API does not exist**

Run:

```bash
.venv/bin/pytest tests/browser/test_aikda_socket.py -k 'maintenance' -q
```

Expected: fail with `AttributeError: 'AikdaSocketGateway' object has no attribute 'maintain_direct_chats'`.

- [ ] **Step 4: Implement one-request maintenance state in `AikdaSocketGateway`**

Add owner-thread state:

```python
self._direct_discovery_queue: deque[str] = deque()
self._history_reconcile_queue: deque[str] = deque()
self._next_discovery_at: datetime | None = None
self._next_reconcile_at: datetime | None = None
self._reconcile_cycle_is_initial = True
```

Implement:

```python
def maintain_direct_chats(
    self, direct_chatroom_ids: tuple[str, ...] = ()
) -> list[DirectChatRoom]:
```

The method must:

1. ensure the Socket connection and update direct targets;
2. consume at most one queued unknown-room history request and return at most one mapping;
3. otherwise use one due `chat.listAll` request to populate only unknown direct room IDs;
4. otherwise consume at most one queued reconciliation history request;
5. otherwise start a due reconciliation queue and consume its first room;
6. schedule the next discovery/reconciliation cycle 30 seconds after the current queue finishes;
7. invalidate a connected-but-stale Socket when a non-initial reconciliation finds an unseen message.

Extract a private `_accept_history(chatroom_id: str) -> bool` helper that performs exactly one `chatroom.getMessages` request, feeds each message to `_accept_message()`, and reports whether the seen-ID set grew.

- [ ] **Step 5: Add the gateway method to the protocol and Playwright fallback**

Add the exact signature to `ChatGateway`. `_PlaywrightGateway.maintain_direct_chats()` raises `NotImplementedError`, matching its existing direct-message methods.

- [ ] **Step 6: Run gateway tests and make them pass**

Run:

```bash
.venv/bin/pytest tests/browser/test_aikda_socket.py -q
```

Expected: all gateway tests pass, including existing reconnect, history ordering, and direct-room joining tests.

- [ ] **Step 7: Write a failing Worker regression test proving outbound starts before blocked maintenance**

Extend `FakeGateway` with a maintenance start event and optional release event. Run `worker.run_once()` in a thread with maintenance blocked, and assert `core.confirmed_event.wait(timeout=1)` succeeds before releasing maintenance. The test must fail while `_sync_direct_chats()` still runs before `_start_outbound_if_idle()`.

- [ ] **Step 8: Move maintenance after outbound scheduling**

Replace `_sync_direct_chats()` with `_maintain_direct_chats()` that calls one gateway maintenance step and persists only the returned mappings:

```python
def _maintain_direct_chats(self, gateway: ChatGateway, now: datetime) -> None:
    try:
        rooms = gateway.maintain_direct_chats(
            self._core.direct_inbound_chatroom_ids()
        )
        if rooms:
            self._core.sync_direct_chats(rooms, now)
    except NotImplementedError:
        return
    except Exception:
        _LOGGER.exception("direct chat maintenance failed")
```

Call `_start_outbound_if_idle(gateway)` before `_maintain_direct_chats(gateway, now)` at the end of `run_once()`. Remove `_last_direct_chat_sync_at` because interval state now belongs to the gateway.

- [ ] **Step 9: Run all Browser Worker tests**

Run:

```bash
.venv/bin/pytest tests/browser/test_worker.py tests/browser/test_aikda_socket.py tests/browser/test_bot_api.py -q
```

Expected: all selected Browser tests pass.

- [ ] **Step 10: Commit Task 2**

```bash
git add src/dzmm_bot/browser/session.py src/dzmm_bot/browser/aikda_socket.py src/dzmm_bot/browser/worker.py tests/browser/test_aikda_socket.py tests/browser/test_worker.py
git commit -m "fix: time-slice browser chat maintenance"
```

---

### Task 3: Full verification and deployment readiness

**Files:**
- Verify only; modify production files only if a test exposes a requirement regression.

**Interfaces:**
- Consumes: the Task 1 routing behavior and Task 2 maintenance-step behavior.
- Produces: fresh repository-wide verification evidence and a clean, reviewable diff.

- [ ] **Step 1: Run the complete test suite**

```bash
.venv/bin/pytest -q
```

Expected: all tests pass with only the repository's known skips and warnings.

- [ ] **Step 2: Inspect the final diff and worktree**

```bash
git diff --check HEAD~2..HEAD
git status --short
git log --oneline -5
```

Expected: no whitespace errors; only pre-existing untracked user files remain outside committed changes.

- [ ] **Step 3: Report readiness without deploying**

Report focused and full test counts, commits, and the expected production validation metrics. Deployment requires a separate explicit user instruction.
