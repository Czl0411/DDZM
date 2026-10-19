# Group Member Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let selected employees remove only unregistered members from one group by replying `/ban 原因` and confirming `/是` within 60 seconds.

**Architecture:** Store a per-group employee UID allowlist and a durable pending removal record in Core. Core validates and queues a single worker command after confirmation; the browser Worker invokes the platform mutation and Core reports the final outcome in the originating group.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy/Alembic, pytest, existing vanilla-JS admin page, existing Aikda Socket.IO/browser session.

**Spec:** `docs/superpowers/specs/2026-10-10-group-member-removal-design.md`

## Global Constraints

- Authorization is per group, selected only from already-onboarded employees; default allowlist is empty.
- A target is removable only when its platform UID has **no** `users` row, including at confirmation and immediately before the platform call.
- `/ban` is a current-group removal, not a permanent platform ban, message deletion, account change, or coin transaction.
- `/是` is exact, from the same actor in the same group, within 60 seconds; the newest pending request for that actor/group replaces the old one.
- The platform mutation is `groupChat.removeMember` with `{chatroomId, memberId}` and a POST request; only its confirmed success permits “已移出”.
- No new product dependency or live test that removes a real member. Preserve unrelated code and local untracked files.

## Review Focus

1. A quoted text containing newlines or command-looking content must appear only as a bounded, escaped confirmation preview, never become a command or target selector. Task 2 tests this.
2. Missing platform nickname and renamed employees must not break the admin selector or change authorization identity. Task 1 tests this.
3. A `/是` received exactly at or after the 60-second deadline must do nothing. Task 2 tests this.
4. A target who joins the company between `/是` and execution must never be removed. Task 3 tests this.
5. A platform timeout after a possibly completed side effect must not claim success or automatically issue a second removal. Task 3 tests this.

---

### Task 1: Persist and edit per-group operator allowlists

**Files:**
- Create: `migrations/versions/20261010_102_group_ban_permissions.py`
- Modify: `src/dzmm_bot/core/schema.py`, `src/dzmm_bot/core/repository.py`, `src/dzmm_bot/core/api_models.py`, `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/admin/app.py`, `src/dzmm_bot/admin/templates/index.html`, `src/dzmm_bot/admin/static/admin.js`
- Test: `tests/core/test_repository.py`, `tests/core/test_app.py`, `tests/admin/test_app.py`

**Interfaces:**
- Produces: `GroupChatConfig.ban_operator_platform_ids: tuple[str, ...]` and `GroupChatResponse.ban_operator_platform_ids: list[str]`.
- Produces: `CoreRepository.create_group_chat(..., ban_operator_platform_ids: Sequence[str] = ())` and `update_group_chat(..., ban_operator_platform_ids: Sequence[str] | None = None)`; reject unknown employee UIDs and duplicates, while an omitted update leaves the value unchanged.
- Consumes: existing paginated `GET /api/game/users?page=&page_size=100` for the modal. Fetch pages when opening the modal; search/select by display name, platform nickname and employee number, while option values remain stable platform UIDs.

- [ ] **Step 1: Write failing repository/API/admin tests.** Name them `test_group_ban_operator_scope`, `test_group_ban_operator_validation`, and `test_admin_group_ban_operator_selector`. Assert a newly created group has `ban_operator_platform_ids == []`, updating group A leaves group B empty, unknown UIDs return 409, and the modal contains the renamed display name/employee number without printing the UID as a label; missing nickname stays selectable.
- [ ] **Step 2: Run `pytest tests/core/test_repository.py tests/core/test_app.py tests/admin/test_app.py -q -k 'group_chat or group_ban'`; verify the new assertions fail.**
- [ ] **Step 3: Add Alembic revision `20261010_102` after `20261010_101`, a non-null JSON list column defaulting to `[]`, then thread the allowlist through Core models, validation, APIs, and admin relay.**
- [ ] **Step 4: Add the multi-select to the existing group modal; load all employee pages through the existing API, label entries by names/nickname/number, and persist only selected UIDs.**
- [ ] **Step 5: Re-run the targeted tests and `git diff --check`; expect pass and no whitespace errors.**
- [ ] **Step 6: Commit only Task 1 files with `feat: configure group ban operators`.**

### Task 2: Record the two-step command without removing anyone yet

**Files:**
- Create: `migrations/versions/20261010_103_group_ban_requests.py`
- Modify: `src/dzmm_bot/core/schema.py`, `src/dzmm_bot/core/repository.py`, `src/dzmm_bot/core/commands.py`, `src/dzmm_bot/core/service.py`
- Test: `tests/core/test_repository.py`, `tests/core/test_group_commands.py`, `tests/core/test_app.py`

**Interfaces:**
- Produces: `CoreRepository.request_group_ban(message: InboundMessage, group_chat_id: UUID) -> GroupBanResult` and `confirm_group_ban(message: InboundMessage, group_chat_id: UUID) -> GroupBanResult`. `GroupBanResult` carries `status`, `target_platform_id`, `reason`, and `message_excerpt` for Chinese replies; success states are `pending` and `queued`, while rejection states distinguish `unauthorized`, `target_joined`, `invalid_reply`, `missing_reason`, `self_target`, `expired`, and `no_pending`.
- Produces: one `WorkerCommandRecord(command=f"ban:{request_id}")` on successful confirmation; `request_id` is the durable ban record UUID and the command is never created at `/ban` time.
- Consumes: `MessageReference.sender_platform_id`, `message_id`, `content_type`, and `text`; the stored request retains the source inbound ID for final feedback.

- [ ] **Step 1: Write failing tests for `/ban 原因` and `/是`.** In `test_group_ban_confirmation_is_one_shot`, assert `request.status == "pending"`, `confirmed.status == "queued"`, `repeated.status == "no_pending"`, and exactly one `ban:<UUID>` worker command exists. In `test_group_ban_rejections`, assert the explicit rejection states above; add text-preview (120 chars/newlines), `[图片]`, cross-actor/group, replacement, and `now == expires_at` tests.
- [ ] **Step 2: Add `test_group_ban_bypasses_gameplay_gates` with active random event, game and performance.** Assert both management commands reach their handler and do not add gameplay messages/rounds.
- [ ] **Step 3: Run `pytest tests/core/test_group_commands.py tests/core/test_repository.py tests/core/test_app.py -q -k 'group_ban'`; verify failures precede implementation.**
- [ ] **Step 4: Add `GroupBanRequestRecord` in Alembic revision `20261010_103` after `20261010_102` with group/actor/target/source message/reason/excerpt, 60-second expiry, status and audit timestamps. Implement atomic pending→queued transition and replacement per actor/group.**
- [ ] **Step 5: Register `/ban` and `/是` in command definitions; route them before performance/random-event/game interception in `CoreService`, and format prompt/error/queued replies in `GroupCommandHandler`.**
- [ ] **Step 6: Re-run targeted tests and `git diff --check`; expect pass and no whitespace errors.**
- [ ] **Step 7: Commit only Task 2 files with `feat: confirm group member removal requests`.**

### Task 3: Execute the platform removal and report an authoritative result

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`, `src/dzmm_bot/core/api_models.py`, `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/browser/core_client.py`, `src/dzmm_bot/browser/session.py`, `src/dzmm_bot/browser/aikda_socket.py`, `src/dzmm_bot/browser/worker.py`
- Test: `tests/core/test_repository.py`, `tests/core/test_app.py`, `tests/browser/test_core_client.py`, `tests/browser/test_session.py`, `tests/browser/test_aikda_socket.py`, `tests/browser/test_worker.py`

**Interfaces:**
- Produces: `CoreRepository.claim_group_ban_execution(request_id: UUID, now: datetime) -> GroupBanExecution | None` and `complete_group_ban_execution(request_id: UUID, outcome: str, detail: str | None, now: datetime) -> bool`; claim rechecks allowance and absence from `users`, then marks the request executing exactly once.
- Produces: `POST /internal/group-bans/{request_id}/begin-execution` and `POST /internal/group-bans/{request_id}/complete` for the worker; `GroupBanExecution` contains `chatroom_id` and `target_platform_id`.
- Produces: matching `CorePort`/`CoreClient` methods and `ChatGateway.remove_member(chatroom_id: str, member_id: str) -> None`.
- Consumes: the `ban:<UUID>` worker command from Task 2. `BrowserSession._request` uses POST for `groupChat.removeMember`; `AikdaSocketGateway` submits `{chatroomId, memberId}` and rejects the signed-in account or configured long-message Bot as target.

- [ ] **Step 1: Write failing `test_group_ban_execution_rechecks_target_and_operator`, `test_remove_member_uses_platform_mutation`, and `test_group_ban_completion_reports_once`.** Assert no platform call after target onboarding or grant revocation, the request is POST `groupChat.removeMember` with exactly `{chatroomId, memberId}`, one success reply after success, and a platform rejection yields failure rather than “已移出”.
- [ ] **Step 2: Write failing `test_group_ban_uncertain_attempt_is_not_repeated`.** Once an attempt is marked executing, a reclaimed worker command must not call `remove_member` again; a timeout or abandoned execution produces an uncertain/failure notice, never “已移出”.
- [ ] **Step 3: Run `pytest tests/core/test_app.py tests/browser/test_core_client.py tests/browser/test_session.py tests/browser/test_aikda_socket.py tests/browser/test_worker.py -q -k 'group_ban or remove_member'`; verify failures precede implementation.**
- [ ] **Step 4: Implement Core begin/complete endpoints and one-shot final outbox reply; make stale/duplicate completion idempotent, and mark an abandoned prior execution `uncertain` on reclaim rather than reissuing the platform call.**
- [ ] **Step 5: Implement the gateway POST mutation and Worker `ban:<UUID>` branch using the Core methods; always complete its worker command, without automatic retry of an uncertain platform call.**
- [ ] **Step 6: Re-run targeted tests, then `pytest tests/core tests/browser tests/admin -q`, `alembic heads`, and `git diff --check`; expect all passing and a single migration head.**
- [ ] **Step 7: Commit only Task 3 files with `feat: execute confirmed group member removal`.**

## Handoff

No production deployment or real-member removal is part of this plan. After local tests, report the commits, test results, and any unverified live-platform behavior; deployment is a separate user decision.
