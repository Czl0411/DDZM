# Socket Realtime Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep group and private game messages responsive when direct-chat reconciliation or outbound Socket.IO sends are slow.

**Architecture:** Socket.IO `message:new` remains the primary inbound path. Its handler enqueues messages into a dedicated serial dispatcher that persists them without waiting for the browser loop. The browser loop periodically discovers direct-room mappings and recovers history; because inbound dispatch is independent, that fallback work cannot delay live message acceptance. Outbound sending is a separate serial task. Durable platform-message IDs remain the only deduplication boundary.

**Tech Stack:** Python 3.12, python-socketio, Playwright, FastAPI internal API, pytest.

## Global Constraints

- Existing group commands, private `/报数`, listener control, and restart recovery keep their behavior.
- A valid Socket.IO event from an unknown private room persists its user-to-room mapping immediately.
- Only current report-capable players remain subscribed to private reports; `pending_join` and `left` are excluded, while `pending_exit` remains through the current round.
- Reconciliation is a 30-second fallback and never runs on the realtime inbound dispatcher.
- Socket and fallback messages rely on persisted `platform_message_id` de-duplication.
- Outbound Socket.IO calls remain serial.

---

### Task 1: Make Socket reads realtime-only

**Files:**
- Modify: `src/dzmm_bot/browser/aikda_socket.py:53-89,236-286`
- Test: `tests/browser/test_aikda_socket.py`

**Interfaces:**
- `read_new(direct_chatroom_ids)` joins active report rooms then drains only received Socket.IO events.
- `reconcile_history(direct_chatroom_ids)` performs fallback history recovery outside the inbound loop.
- Unknown valid direct Socket events produce `InboundMessage(source_type="direct")`.

- [ ] Write failing tests that prove an unknown direct `message:new` is returned, and that a second `read_new()` does not call `chatroom.getMessages`.
- [ ] Run: `PYTHONPATH=src .venv/bin/pytest tests/browser/test_aikda_socket.py -q -k 'unknown_private or does_not_fetch_history'`. Confirm failure because the current gateway filters unknown direct rooms and reconciles in `read_new()`.
- [ ] Implement `reconcile_history()`; remove history reconciliation from `read_new()`; classify valid non-group rooms as direct while retaining self-message and message-ID filtering.
- [ ] Run: `PYTHONPATH=src .venv/bin/pytest tests/browser/test_aikda_socket.py -q`. Confirm pass.
- [ ] Commit: `git commit -m "fix: keep socket reads realtime"`.

### Task 2: Isolate realtime dispatch and outbound sending

**Files:**
- Modify: `src/dzmm_bot/browser/worker.py:30-220`
- Test: `tests/browser/test_worker.py:15-505`

**Interfaces:**
- A one-worker inbound executor serially persists Socket and reconciliation messages as they arrive.
- A one-worker outbound executor claims and sends at most one record at a time.
- Finished futures are confirmed or failed by the main worker loop.
- Direct inbound messages sync `DirectChatRoom(sender_platform_id, chatroom_id)` before submission.

- [ ] Write failing tests that prove an unknown direct event is mapped before submission, and a second inbound event is submitted while a deliberately blocked outbound send is outstanding.
- [ ] Run: `PYTHONPATH=src .venv/bin/pytest tests/browser/test_worker.py -q -k 'persists_unknown or while_an_outbound_send'`. Confirm failure because direct mapping is periodic and outbound send is synchronous.
- [ ] Add two `ThreadPoolExecutor(max_workers=1)` instances. The inbound executor receives a gateway handler and performs direct-room upsert plus `submit_inbound()` in arrival order. The main browser loop performs 30-second discovery and `reconcile_history()` on its existing Playwright thread; recovered messages use the same inbound handler. The outbound executor claims and serially sends one record. The main loop must never wait for either executor.
- [ ] Run: `PYTHONPATH=src .venv/bin/pytest tests/browser/test_worker.py -q`. Confirm pass.
- [ ] Commit: `git commit -m "fix: isolate browser reconciliation and sending"`.

### Task 3: Verify active private-room subscription scope

**Files:**
- Inspect: `src/dzmm_bot/core/repository.py`
- Modify only if necessary: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- `direct_inbound_chatroom_ids()` returns only active report-capable game members.

- [ ] Write a failing test only if the existing query includes `pending_join` or `left` rooms.
- [ ] Run: `PYTHONPATH=src .venv/bin/pytest tests/core/test_repository.py -q -k 'direct_inbound_rooms'`.
- [ ] If needed, make the single state-filter correction; otherwise retain the current implementation without edits.
- [ ] Run: `PYTHONPATH=src .venv/bin/pytest tests/browser/test_aikda_socket.py tests/browser/test_worker.py tests/core/test_repository.py -q`.
- [ ] Run: `PYTHONPATH=src .venv/bin/pytest -q`.
- [ ] Commit all work, fast-forward merge to `main`, deploy through `deploy/scripts/deploy.sh`, and verify active services, stable restart count, empty pending outbound/AI queues, and 200 inbound/outbound core responses.

## Plan Review

The plan covers realtime Socket delivery, unknown private-room persistence, 30-second nonblocking compensation, active-room release, serial outbound isolation, durable de-duplication, and restart recovery. It requires no migration because the direct-room and message-ID records already persist.
