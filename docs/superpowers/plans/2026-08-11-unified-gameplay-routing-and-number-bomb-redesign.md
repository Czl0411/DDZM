# Unified Gameplay Routing and Number Bomb Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route shared lifecycle commands to the player's real active game, release every stalled signup, and redesign “蹦蹦数字炸弹” around manual start, private prompts, reminders, and permanent skips without regressing the production memory-duel hotfix.

**Architecture:** Add only the persistent fields needed by the approved state machines, then expose one repository-owned `ActiveGameplaySummary` consumed by commands and admin APIs. Keep number-bomb rules in the existing repository and pure calculation module, deliver per-player prompts through the existing outbound queue, and accelerate that queue with bounded sequential draining plus joined-room reuse.

**Tech Stack:** Python 3.12+, SQLAlchemy 2, Alembic, PostgreSQL/SQLite, FastAPI, Pydantic 2, python-socketio, pytest, vanilla JavaScript/HTML/CSS.

## Global Constraints

- Implement `docs/superpowers/specs/2026-08-11-unified-gameplay-routing-and-number-bomb-redesign.md` exactly.
- Execute in an isolated worktree created with `superpowers:using-git-worktrees`.
- Base the worktree on main commit `986be74`; preserve production hotfix `09a2275` and its `multiplayer_active` reply template.
- Add migration `20260811_35` with `down_revision = "20260810_34"`; do not edit deployed migration 34.
- `/加入`, `/退出`, `/继续`, and `/结束游戏` must resolve the player's actual game before dispatch and must never fall through to an unrelated game reply.
- `/退出` has no confirmation. Number-bomb participants still leave on the next round; memory-duel participants surrender after the duel starts.
- All signup waits release once and notify once. Defaults: random event 15 minutes; memory duel, undercover, blame game, and number bomb 2 minutes each.
- Number-bomb creation is exactly `/蹦蹦数字炸弹`, manual `/开始` requires at least 3 participants, and no maximum player count exists.
- Every accepted number-bomb participant must have a known direct chat before start. Every round privately sends `请按这个格式报数给我 /报数 数字` once per participant.
- Number-bomb reminders default to 15 seconds. `/跳过 2 4` opens only after the first reminder and permanently removes only unreported targets from the entire game.
- Number-bomb `collecting` and `waiting_continue` never auto-expire. Only `signup` has an inactivity deadline.
- Preserve exact number-bomb arithmetic, distinct deviation bands, truth/truth/dare rotation, result rendering, and fact-only memory behavior.
- Outbound optimization remains ordered and sequential: no parallel Socket send flood, bounded batch size, bounded time budget, and per-message ack.
- Do not deploy, push, or merge during implementation. Stop after verified commits for explicit approval.

## File Structure

- Create `migrations/versions/20260811_35_gameplay_routing_number_bomb.py`: add settings/deadline/reminder/skip fields and update the seeded number-bomb knowledge card.
- Modify `src/dzmm_bot/core/schema.py`: map migration 35 fields.
- Modify `src/dzmm_bot/core/repository.py`: authoritative gameplay summary, independent signup expiry, number-bomb manual start/reminders/skips, admin force end, and settings.
- Modify `src/dzmm_bot/core/commands.py`: shared lifecycle router plus `/当前游戏`, `/开始`, and `/跳过` handlers.
- Modify `src/dzmm_bot/core/reply_templates.py`: add editable templates for routing, expiry, direct-chat gates, reminders, skips, and force-end messages.
- Modify `src/dzmm_bot/core/api_models.py` and `src/dzmm_bot/core/app.py`: typed settings, gameplay summary, and force-end endpoints.
- Modify `src/dzmm_bot/core/ai_knowledge.py`: expose only the approved primary commands and current number-bomb rules.
- Modify `src/dzmm_bot/browser/aikda_socket.py`: reuse joined rooms across sends until reconnect.
- Modify `src/dzmm_bot/browser/worker.py`: drain a bounded sequential outbound batch per loop.
- Modify `src/dzmm_bot/admin/core_client.py`, `src/dzmm_bot/admin/app.py`, `src/dzmm_bot/admin/templates/index.html`, and `src/dzmm_bot/admin/static/admin.js`: relay/render unified current-game state, settings, and force end.
- Modify focused tests under `tests/core`, `tests/browser`, `tests/admin`, and `tests/deploy` before each implementation slice.

---

### Task 1: Persist independent signup and reminder state

**Files:**
- Create: `migrations/versions/20260811_35_gameplay_routing_number_bomb.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/deploy/test_artifacts.py`

**Interfaces:**
- Extends: `MemoryAssessmentSettingsRecord.duel_signup_timeout_minutes: int`.
- Extends: `MemoryAssessmentGameRecord.signup_deadline: datetime | None`.
- Extends: `UndercoverSettingsRecord.signup_timeout_minutes: int`.
- Extends: `NumberBombSettingsRecord.enabled: bool`, `signup_timeout_minutes: int`, and `reminder_interval_seconds: int`.
- Extends: `NumberBombGameRecord.signup_deadline`, `next_reminder_at`, and `skip_enabled`.
- Extends: `NumberBombRoundPlayerRecord.skipped_at: datetime | None`.
- Keeps: deployed `inactivity_timeout_minutes` and `target_player_count` columns for migration compatibility, but new runtime logic no longer uses them.

- [ ] **Step 1: Write failing schema and migration tests**

Add metadata assertions:

```python
memory_settings = Base.metadata.tables["memory_assessment_settings"]
memory_games = Base.metadata.tables["memory_assessment_games"]
undercover = Base.metadata.tables["undercover_settings"]
number_settings = Base.metadata.tables["number_bomb_settings"]
number_games = Base.metadata.tables["number_bomb_games"]
round_players = Base.metadata.tables["number_bomb_round_players"]
assert "duel_signup_timeout_minutes" in memory_settings.c
assert "signup_deadline" in memory_games.c
assert "signup_timeout_minutes" in undercover.c
assert {"enabled", "signup_timeout_minutes", "reminder_interval_seconds"} <= set(number_settings.c.keys())
assert {"signup_deadline", "next_reminder_at", "skip_enabled"} <= set(number_games.c.keys())
assert "skipped_at" in round_players.c
```

Extend the deploy migration test to upgrade through revision 35 and assert seeded defaults `(2, 2, True, 2, 15)` for memory signup, undercover signup, number enabled/signup/reminder.

- [ ] **Step 2: Run tests and verify RED**

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/core/test_repository.py -k "schema or settings" \
  tests/deploy/test_artifacts.py -k "migration"
```

Expected: migration 35 and the mapped columns do not exist.

- [ ] **Step 3: Add migration 35 and matching records**

Use:

```python
revision = "20260811_35"
down_revision = "20260810_34"
```

Add non-null settings columns with temporary server defaults, nullable deadlines, `skip_enabled=False`, and nullable `skipped_at`. Backfill active number-bomb signup deadlines from `created_at + 2 minutes`; backfill active collecting reminders from `COALESCE(started_at, last_activity_at) + 15 seconds`. Update only the migration-34 seeded `number_bomb` knowledge card to the new no-count/manual-start wording; preserve administrator-created cards.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: selected tests pass.

- [ ] **Step 5: Commit persistence changes**

```bash
git add migrations/versions/20260811_35_gameplay_routing_number_bomb.py \
  src/dzmm_bot/core/schema.py tests/core/test_repository.py \
  tests/deploy/test_artifacts.py
git commit -m "feat: persist gameplay signup and reminder state"
```

### Task 2: Add the authoritative current-game query and router

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_group_commands.py`

**Interfaces:**
- Produces: `ActiveGameplaySummary(game_type: str | None, game_id: UUID | None, state: str | None, actor_role: str, participant_names: tuple[str, ...], available_commands: tuple[str, ...], signup_deadline: datetime | None, next_reminder_at: datetime | None)`.
- Produces: `CoreRepository.active_gameplay_summary(platform_id: str, now: datetime) -> ActiveGameplaySummary`.
- Produces: handlers `_current_game`, `_shared_join`, `_shared_leave`, `_shared_continue`, and `_shared_end`.
- Keeps: legacy command handlers as aliases that call the same repository operations.

- [ ] **Step 1: Write failing repository summary tests**

Seed one state at a time and assert exact identity:

```python
summary = repository.active_gameplay_summary("number-p1", now)
assert (summary.game_type, summary.state, summary.actor_role) == (
    "number_bomb", "signup", "participant"
)
assert summary.available_commands == ("/退出", "/开始", "/结束游戏")
```

Cover memory waiting initiator, memory active participant, undercover participant, blame participant, random-event participant, number-bomb next-round candidate, nonparticipant with an open signup, no game, and deliberately inconsistent multiple-active fixtures returning `game_type="conflict"`.

- [ ] **Step 2: Write failing command routing regressions**

Add table-driven tests proving `/加入`, `/退出`, `/继续`, and `/结束游戏` dispatch to the seeded game. Include the screenshot regression: while a number-bomb game exists, `/结束游戏` from a participant returns the number-bomb ending template and never contains `谁是卧底`.

Add `/当前游戏` expectations:

```python
_receive(service, "current-1", "number-p1", "/当前游戏", now)
reply = _latest_reply(factory)
assert "蹦蹦数字炸弹" in reply
assert "报名中" in reply
assert "/开始" in reply
```

- [ ] **Step 3: Run tests and verify RED**

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/core/test_repository.py tests/core/test_group_commands.py \
  -k "active_gameplay or shared_route or current_game or routes_end_to_number_bomb"
```

- [ ] **Step 4: Implement one query and explicit dispatch**

Add `/当前游戏`, `/开始`, and `/跳过` to `_COMMANDS`. Replace the existing `number_bomb -> blame -> undercover` trial chains with:

```python
summary = self._repository.active_gameplay_summary(
    message.sender_platform_id, received_at
)
if summary.game_type == "conflict":
    return self._reply(command, "game_state_conflict", received_at)
return self._dispatch_shared_game_command(
    command, summary, message.sender_platform_id, content, received_at
)
```

`/结束游戏` on an active memory duel must return a memory-specific instruction to use `/退出`; it must not surrender automatically and must not call an unrelated end handler. Render `/当前游戏` from the summary's exact game/state/role/commands.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Step 3 command, then:

```bash
PYTHONPATH=src .venv/bin/pytest -q tests/core/test_group_commands.py
```

- [ ] **Step 6: Commit authoritative routing**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py \
  src/dzmm_bot/core/reply_templates.py tests/core/test_repository.py \
  tests/core/test_group_commands.py
git commit -m "fix: route lifecycle commands to current game"
```

### Task 3: Release memory and undercover signups with independent settings

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_group_commands.py`
- Test: `tests/core/test_app.py`

**Interfaces:**
- Extends: `MemoryAssessmentSettings.duel_signup_timeout_minutes`.
- Extends: `UndercoverSettings.signup_timeout_minutes`.
- Produces: `CoreRepository.cancel_waiting_memory_assessment_duel(platform_id, now)`.
- Extends: `expire_memory_assessment_duels(now)` to distinguish signup cancellation from active answer timeout.

- [ ] **Step 1: Write failing expiry and cancellation tests**

Verify memory waiting creation writes `signup_deadline=now+2m`, does not expire early, expires once at the deadline, releases `active_key`, sends one cancellation notice through daily jobs, and changes no balances or activity facts. Verify waiting initiator `/退出` and `/结束游戏` cancel; noninitiators cannot cancel. Verify active `/退出` still surrenders with the existing settlement.

Change an undercover setting to 3 minutes, create a signup, and assert its persisted deadline uses 3 minutes rather than `_UNDERCOVER_SIGNUP_TIMEOUT`.

- [ ] **Step 2: Run tests and verify RED**

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/core/test_repository.py tests/core/test_group_commands.py tests/core/test_app.py \
  -k "memory_duel_signup or waiting_duel_cancel or undercover_signup_setting"
```

- [ ] **Step 3: Implement minimal settings and expiry paths**

Create waiting duels with:

```python
game = MemoryAssessmentGameRecord(
    mode="duel",
    state="waiting_opponent",
    active_key="global",
    signup_deadline=now + timedelta(
        minutes=settings.duel_signup_timeout_minutes
    ),
    # existing fields unchanged
)
```

In `expire_memory_assessment_duels`, select waiting games by `signup_deadline` and active games by `answer_deadline` in separate branches. Cancellation sets `state="cancelled"`, clears `active_key`, records `finished_at`, and creates no economy or memory event. Replace the undercover constant at signup creation with its setting.

- [ ] **Step 4: Extend core settings APIs**

Add validated fields to the existing response/request models and relay helpers. Use `Field(ge=1, le=60)` for both new minute settings. Keep existing settings fields and response shapes otherwise unchanged.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Step 2 command, then all core repository tests:

```bash
PYTHONPATH=src .venv/bin/pytest -q tests/core/test_repository.py
```

- [ ] **Step 6: Commit signup timeout fixes**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/api_models.py \
  src/dzmm_bot/core/app.py src/dzmm_bot/core/commands.py \
  src/dzmm_bot/core/reply_templates.py tests/core/test_repository.py \
  tests/core/test_group_commands.py tests/core/test_app.py
git commit -m "fix: release stalled multiplayer signups"
```

### Task 4: Replace number-bomb target counts with manual start and direct prompts

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_group_commands.py`
- Modify: `tests/core/test_service.py`

**Interfaces:**
- Changes: `start_number_bomb_game(platform_id: str, now: datetime) -> NumberBombGameResult`.
- Produces: `start_number_bomb_round(platform_id: str, now: datetime) -> NumberBombGameResult` for `/开始`.
- Produces: `NumberBombPlayer.direct_chatroom_id: str | None` in command-facing results.
- Keeps: `join_number_bomb_game`, `leave_number_bomb_game`, `submit_number_bomb`, `continue_number_bomb_game`, and `end_number_bomb_game` with revised unlimited/manual-start behavior.

- [ ] **Step 1: Rewrite tests for the new lobby contract**

Assert:

```python
created = repository.start_number_bomb_game("p1", now)
assert (created.status, created.player_count) == ("signup_started", 1)
for index in range(2, 13):
    assert repository.join_number_bomb_game(f"p{index}", now).status == "joined"
assert repository.number_bomb_game_summary().state == "signup"
assert repository.start_number_bomb_round("p2", now).status == "started"
```

Create fixtures with and without `DirectChatRecord`. Creation and join without a mapping must return `direct_chat_required`. Starting with one missing mapping must return `missing_direct_chats`, list that player's stable number/name, keep `signup`, and enqueue no private prompts.

Update command tests so `/蹦蹦数字炸弹 6` returns the new usage, `/蹦蹦数字炸弹` opens signup, joins never auto-start, any participant `/开始` works at 3+, and nonparticipants cannot start.

- [ ] **Step 2: Run tests and verify RED**

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/core/test_repository.py tests/core/test_group_commands.py tests/core/test_service.py \
  -k "number_bomb and (manual or direct_chat or unlimited or private_prompt)"
```

- [ ] **Step 3: Implement the manual lobby**

Use sentinel `target_player_count=0` for newly created rows while retaining the deployed column. Set `signup_deadline=now + settings.signup_timeout_minutes`. Remove every count-10 branch and every join-triggered `_start_number_bomb_round` call. Validate a direct mapping for the creator and each joining/candidate player.

Reject new creation with the editable disabled template when `settings.enabled` is false. Disabling the setting must not end an already active game.

`start_number_bomb_round` must lock the game, verify signup state and actor membership, require at least 3 current members, re-query every direct mapping, then create the collecting round atomically with `next_reminder_at=now+reminder_interval` and `skip_enabled=False`.

- [ ] **Step 4: Return ordered private prompt replies**

For successful `/开始`, return one group reply plus one `CommandReply` per participant:

```python
replies = [CommandReply(group_started_text)]
replies.extend(
    CommandReply(
        "请按这个格式报数给我 /报数 数字",
        destination_chatroom_id=player.direct_chatroom_id,
        delivery_kind="number_bomb_private",
    )
    for player in result.players
)
```

Invalid-round retry and `/继续` must use the same helper so every new collecting attempt prompts all current players once. Existing inbound message idempotency and outbound ordering remain unchanged.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Step 2 command, then:

```bash
PYTHONPATH=src .venv/bin/pytest -q tests/core/test_group_commands.py tests/core/test_service.py
```

- [ ] **Step 6: Commit manual start and prompts**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py \
  src/dzmm_bot/core/reply_templates.py tests/core/test_repository.py \
  tests/core/test_group_commands.py tests/core/test_service.py
git commit -m "feat: manually start number bomb with private prompts"
```

### Task 5: Add restart-safe number-bomb reminders and permanent skips

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_group_commands.py`

**Interfaces:**
- Produces: `run_number_bomb_jobs(now: datetime) -> list[str]` for signup expiry and due reminders only.
- Produces: `skip_number_bomb_players(platform_id: str, targets: tuple[str, ...], now: datetime) -> NumberBombGameResult`.
- Produces: parser accepting numeric tokens first and one unique exact display name as compatibility.
- Changes: settlement queries ignore round players whose `skipped_at` is non-null.

- [ ] **Step 1: Write failing clock-driven reminder tests**

With a 15-second interval, assert no reminder at `14.999s`, one reminder at `15s`, `skip_enabled=True`, `next_reminder_at=30s`, no duplicate at the same time from a second repository instance, and a second reminder at `30s`. Restart by constructing a new `CoreRepository` and prove it uses persisted deadlines.

Assert signup expires at its 2-minute deadline exactly once, while `collecting` and `waiting_continue` remain active after hours.

- [ ] **Step 2: Write failing skip behavior tests**

Cover `/跳过` before first reminder, unauthorized actor, `/跳过 2 4`, unique name, duplicate name rejection, already-submitted rejection, permanent member removal, no activity fact for removed players, immediate settlement when remaining players all submitted, and whole-game ending below 3 players.

- [ ] **Step 3: Run tests and verify RED**

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/core/test_repository.py tests/core/test_group_commands.py \
  -k "number_bomb and (reminder or skip or signup_expiry or no_active_expiry)"
```

- [ ] **Step 4: Implement atomic reminder claiming**

Under the gameplay transaction lock, require `state="collecting"` and `next_reminder_at <= now`, load only `submitted_number IS NULL AND skipped_at IS NULL`, set `skip_enabled=True`, advance `next_reminder_at` before returning the rendered reminder, and set it to `None` when no targets remain.

Replace the old all-state inactivity job with:

```python
if game.state == "signup" and game.signup_deadline <= now:
    return [finish_signup_once(...)]
if game.state == "collecting" and game.next_reminder_at <= now:
    return [claim_unreported_reminder_once(...)]
return []
```

- [ ] **Step 5: Implement permanent skip and shared settlement**

Resolve all targets before mutation. For every accepted target, set the current round player's `skipped_at=now` and member `state="left"`; never renumber or reuse `roster_order`. Recompute active round player count. If it is below 3, finish. If every remaining player has a number, call one extracted `_settle_number_bomb_round(...)` used by both submit and skip; otherwise continue collecting.

- [ ] **Step 6: Run tests and verify GREEN**

Run the Step 3 command.

- [ ] **Step 7: Commit reminders and skips**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py \
  src/dzmm_bot/core/reply_templates.py tests/core/test_repository.py \
  tests/core/test_group_commands.py
git commit -m "feat: remind and skip stalled number bomb players"
```

### Task 6: Batch outbound sends and reuse joined rooms

**Files:**
- Modify: `src/dzmm_bot/browser/aikda_socket.py`
- Modify: `src/dzmm_bot/browser/worker.py`
- Test: `tests/browser/test_aikda_socket.py`
- Test: `tests/browser/test_worker.py`

**Interfaces:**
- Produces: `BrowserWorker._drain_outbound(gateway, started_at) -> None`.
- Uses: constants `_OUTBOUND_BATCH_SIZE = 20` and `_OUTBOUND_BATCH_BUDGET_SECONDS = 2.0`.
- Keeps: existing `claim_outbound`, `confirm_sent`, `mark_outbound_failed`, ordering, ack, and reconnect behavior.

- [ ] **Step 1: Write failing joined-room cache tests**

Send twice to one direct room and assert one `message:join-room` call plus two `message:send` calls. Simulate disconnect/reconnect, send again, and assert a second join occurs because `_joined_direct_chatroom_ids` was cleared.

- [ ] **Step 2: Write failing bounded-drain worker tests**

Queue 25 outbounds. One `run_once()` must send and confirm exactly 20 in order. A budget-clock test must stop before 20 when elapsed time reaches 2 seconds. A failure test must preserve existing failure/recovery semantics and return control instead of busy looping.

- [ ] **Step 3: Run tests and verify RED**

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/browser/test_aikda_socket.py tests/browser/test_worker.py \
  -k "joined_room or outbound_batch or outbound_budget"
```

- [ ] **Step 4: Reuse `_join_direct_room` in `send_to`**

Replace the unconditional join with:

```python
if chatroom_id not in self._joined_direct_chatroom_ids:
    self._join_direct_room(chatroom_id)
```

The existing disconnect and stale-socket paths already clear the set and remain the only cache invalidation points.

- [ ] **Step 5: Drain a bounded sequential batch**

Move the existing single-message send/ack body into `_send_one_outbound`. Loop claim/send/ack sequentially until queue empty, 20 messages sent, the monotonic budget is reached, or a send requests recovery. Do not add threads, async fan-out, sleeps, or a new queue.

- [ ] **Step 6: Run tests and verify GREEN**

Run the Step 3 command, then:

```bash
PYTHONPATH=src .venv/bin/pytest -q tests/browser
```

- [ ] **Step 7: Commit transport optimization**

```bash
git add src/dzmm_bot/browser/aikda_socket.py src/dzmm_bot/browser/worker.py \
  tests/browser/test_aikda_socket.py tests/browser/test_worker.py
git commit -m "perf: drain outbound messages in bounded batches"
```

### Task 7: Expose typed gameplay administration APIs

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_app.py`

**Interfaces:**
- Changes: `NumberBombSettingsResponse(enabled: bool, signup_timeout_minutes: int, reminder_interval_seconds: int)`.
- Produces: `GameplaySummaryResponse` mirroring `ActiveGameplaySummary` without private submitted numbers.
- Produces: `GET /internal/gameplay/current`.
- Produces: `POST /internal/gameplay/{game_type}/{game_id}/force-end`.

- [ ] **Step 1: Write failing API tests**

Verify number-bomb settings default to `{enabled: true, signup_timeout_minutes: 2, reminder_interval_seconds: 15}`, validate enabled and positive bounded values, and no longer expose `inactivity_timeout_minutes`.

Verify current-game API returns participant names plus reported/unreported names but never submitted numbers. Verify force end requires the exact active game type and ID, changes it to ended, returns 409 for stale/mismatched IDs, enqueues one administrator termination message, and creates no balance or activity fact.

- [ ] **Step 2: Run tests and verify RED**

```bash
PYTHONPATH=src .venv/bin/pytest -q tests/core/test_app.py \
  -k "number_bomb_settings or gameplay_current or force_end_gameplay"
```

- [ ] **Step 3: Implement typed settings and summary routes**

Use `Field(ge=1, le=60)` for signup minutes and `Field(ge=5, le=300)` for reminder seconds. The summary route calls the same repository summary/query helpers as `/当前游戏`; number-bomb progress includes stable number/name and boolean `reported`, never `submitted_number`.

- [ ] **Step 4: Implement force end by exact identity**

Within the gameplay lock, re-read the requested row by type and UUID, verify it is still active, finish it with `finish_reason="admin_forced"`, and enqueue the editable force-end group notice in the same transaction.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Step 2 command.

- [ ] **Step 6: Commit core administration API**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py \
  src/dzmm_bot/core/repository.py tests/core/test_app.py
git commit -m "feat: expose unified gameplay administration"
```

### Task 8: Update the admin console and settings relays

**Files:**
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Adds: admin relay `GET /api/gameplay/current`.
- Adds: admin relay `POST /api/gameplay/{game_type}/{game_id}/force-end`.
- Updates: `/api/game/number-bomb/settings`, memory settings, and undercover settings payload whitelists.

- [ ] **Step 1: Write failing relay and static-surface tests**

Extend `FakeCore` with gameplay summary and force-end recording. Assert relays preserve auth/versioning/idempotency. Assert HTML contains `gameplay-current-card`, `force-end-current-game`, `number-bomb-enabled`, `number-bomb-signup-minutes`, and `number-bomb-reminder-seconds`; remove the old inactivity input assertion.

Assert memory and undercover settings forms include their independent signup timeout fields.

- [ ] **Step 2: Run tests and verify RED**

```bash
PYTHONPATH=src .venv/bin/pytest -q tests/admin/test_app.py \
  -k "gameplay_current or force_end or number_bomb_settings_surface or signup_timeout_surface"
```

- [ ] **Step 3: Update relays and strict payload validation**

Forward exactly the typed fields accepted by core. Force-end relays use an `Idempotency-Key`, preserve `If-Match`, and return the standard versioned configuration response.

- [ ] **Step 4: Render the unified current-game card**

Display game name/state/ID, duration, participants, candidates, current round, signup deadline, next reminder, and number-bomb reported/unreported status. Hide the force-end button when no game exists. Require the existing confirmation modal before the administrator action; this confirmation is admin-only and does not alter the no-confirmation player `/退出` rule.

- [ ] **Step 5: Replace number-bomb configuration controls**

Render enabled/disabled, signup timeout minutes, and reminder seconds. Update copy to “不限人数，参与者手动 `/开始`；开局后不因无操作解散.” Extend existing memory and undercover settings modals with their new timeout fields.

- [ ] **Step 6: Run tests and verify GREEN**

Run the Step 2 command, then:

```bash
PYTHONPATH=src .venv/bin/pytest -q tests/admin
```

- [ ] **Step 7: Commit admin console changes**

```bash
git add src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py \
  src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js \
  src/dzmm_bot/admin/static/admin.css tests/admin/test_app.py
git commit -m "feat: manage active gameplay from admin console"
```

### Task 9: Align templates, help, AI knowledge, and full verification

**Files:**
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/ai_knowledge.py`
- Modify: `rule.md`
- Modify: `tests/core/test_group_commands.py`
- Modify: `tests/core/test_ai_knowledge.py`
- Modify: `tests/core/test_app.py`

**Interfaces:**
- Keeps: legacy aliases executable.
- Shows: only `/当前游戏`, `/加入`, `/退出`, `/继续`, `/结束游戏`, `/开始`, and game-specific deep actions as primary help.
- Updates: number-bomb authoritative knowledge to no-count/manual-start/unlimited/reminder/skip behavior.

- [ ] **Step 1: Write failing help/template/knowledge tests**

Assert `/帮助 游戏` and `/帮助 蹦蹦数字炸弹` contain `/蹦蹦数字炸弹`, `/加入`, `/开始`, private `/报数 数字`, `/跳过 编号`, `/继续`, and `/结束游戏`; they must not contain `人数`, `3-10`, or the old inactivity release claim. Verify old aliases still route.

Assert every newly referenced scenario exists in `TEMPLATE_DEFINITIONS` and templates expose only their declared variables.

- [ ] **Step 2: Run tests and verify RED**

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/core/test_group_commands.py tests/core/test_ai_knowledge.py tests/core/test_app.py \
  -k "help or number_bomb or template or answer_enable_gate"
```

- [ ] **Step 3: Update final copy and rule documentation**

Add the approved rules to `rule.md`, change the seeded/default knowledge text, and keep AI behavior explanatory only. Templates must cover current-game conflict/no-game, memory waiting cancellation/expiry, number-bomb direct-chat requirement, signup expiry, missing direct chats, reminders, skip outcomes, insufficient players, and administrator force end.

- [ ] **Step 4: Run focused suites**

```bash
PYTHONPATH=src .venv/bin/pytest -q tests/core tests/browser tests/admin tests/deploy
```

Expected: all focused suites pass.

- [ ] **Step 5: Run the full suite**

```bash
PYTHONPATH=src .venv/bin/pytest -q
```

Expected: all tests pass; only the repository's documented skips remain.

- [ ] **Step 6: Audit scope and production-hotfix preservation**

```bash
git status --short
git log --oneline --decorate -15
git merge-base --is-ancestor 09a2275 HEAD
git diff --check 986be74..HEAD
git diff --stat 986be74..HEAD
```

Expected: only intentional feature files differ, `09a2275` is an ancestor, and no whitespace errors exist. User-owned `.env`, `.DS_Store`, and `docs/BOT_MESSAGE_TRANSPORT_HANDOFF.md` remain untouched.

- [ ] **Step 7: Commit final documentation and compatibility changes**

```bash
git add src/dzmm_bot/core/reply_templates.py src/dzmm_bot/core/commands.py \
  src/dzmm_bot/core/ai_knowledge.py rule.md tests/core/test_group_commands.py \
  tests/core/test_ai_knowledge.py tests/core/test_app.py
git commit -m "docs: align gameplay help with unified commands"
```

- [ ] **Step 8: Report without deployment**

Report commit range, focused/full test counts, migration revision, preserved hotfix ancestry, and any warnings. Do not deploy until the user explicitly approves the verified implementation.
