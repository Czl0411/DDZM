# Long Message Socket Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Join the Aikda destination room explicitly before every outbound message.

**Architecture:** `AikdaSocketGateway.send_to()` is the outbound boundary. It adds a successful `message:join-room` acknowledgement before its existing `message:send` acknowledgement, without changing outbound text.

**Tech Stack:** Python 3.12, python-socketio, pytest.

## Global Constraints

- Preserve text byte-for-character, including real line breaks.
- Do not add splitting or newline substitution.
- Do not log message bodies, authentication tokens, or cookies.

---

### Task 1: Join the destination room before sending

**Files:**

- Modify: `tests/browser/test_aikda_socket.py`
- Modify: `src/dzmm_bot/browser/aikda_socket.py`

**Interfaces:**

- `AikdaSocketGateway.send_to(chatroom_id, text) -> str` emits `message:join-room`, then `message:send`.

- [x] **Step 1: Write the failing test**

`test_send_joins_destination_before_sending_and_preserves_newlines` verifies the event ordering and an unchanged newline payload.

- [x] **Step 2: Verify the test fails**

The old implementation emitted only `message:send`.

- [x] **Step 3: Implement the minimal protocol change**

`send_to()` now requires a successful join acknowledgement immediately before sending.

- [x] **Step 4: Verify focused tests**

Run: `PYTHONPATH=src .venv/bin/pytest -q tests/browser/test_aikda_socket.py tests/browser/test_worker.py`

- [ ] **Step 5: Commit**

Commit production code, tests, and these design documents with message `fix: join room before outbound socket messages`.
