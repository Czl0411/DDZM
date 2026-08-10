# Bengbeng Number Bomb Game Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the persistent “蹦蹦数字炸弹” multiplayer game with private integer submissions, exact average-times-0.8 ranking, continuous truth-or-dare rounds, configurable inactivity release, and restart-safe delivery.

**Architecture:** Extend the existing inbound contract with explicit group/direct provenance and let the Browser Worker subscribe only to direct rooms required by the active round. Keep the game state machine in the existing SQLAlchemy repository, isolate exact arithmetic and rendering in a small pure module, and reuse the shared gameplay gate, outbound queue, reply templates, activity facts, FastAPI core, and vanilla admin UI.

**Tech Stack:** Python 3.12+, SQLAlchemy 2, Alembic, PostgreSQL/SQLite, FastAPI, Pydantic 2, python-socketio, pytest, vanilla JavaScript/HTML/CSS.

## Global Constraints

- Implement `docs/superpowers/specs/2026-08-10-bengbeng-number-bomb-game-design.md` exactly.
- Execute in an isolated worktree created with `superpowers:using-git-worktrees`.
- The execution branch must contain main commit `030ae7e` and blame-settlement commit `cdd551d`; migration `20260810_34` therefore has `down_revision = "20260810_33"`.
- After the execution worktree contains both prerequisite commits, record its pre-feature SHA with `git config --local codex.numberBombBase "$(git rev-parse HEAD)"` for the final scope audit.
- Creation syntax is exactly `/蹦蹦数字炸弹 人数`; creation and every playable round allow `3–10` current players.
- Integers are exactly `1–100`; the first valid private submission per player and round attempt is immutable.
- Compute and rank with exact integers using `|5N × x - 4S|`; round only for two-decimal display with `ROUND_HALF_UP`.
- All minimum-deviation players win; all players in the second-largest distinct deviation band are punished; fewer than three bands invalidates and reopens the same round.
- Round types repeat truth, truth, dare. A valid result waits for `/继续`; an invalid result immediately reopens the same round and attempt number increases.
- Mid-game `/加入` and `/退出` affect only the next valid round. Candidate joins are FIFO and projected next-round size never exceeds 10.
- Any current participant can `/继续` after settlement or `/结束游戏` while active. Applying roster changes below 3 players ends the game.
- Only state-changing valid commands refresh inactivity. Default timeout is 10 minutes, configurable from 1 through 60 and immediately effective.
- No balance changes, guarantees, rank limits, daily start limits, AI-generated punishments, or punishment library.
- Direct `/报数` never enters ordinary activity, AI chat, impression extraction, or memory-message batching. Ordinary group chat remains eligible for existing observation rules.
- Do not push, merge to main, or deploy during implementation; stop with a clean verified branch for explicit approval.

## File Structure

- Create `migrations/versions/20260810_34_bengbeng_number_bomb.py`: inbound provenance columns, activity-event detail, four game tables, settings seed, constraints, and the AI knowledge card.
- Create `src/dzmm_bot/core/number_bomb.py`: exact arithmetic, distinct-band ranking, two-decimal formatting, and fixed result rendering.
- Create `tests/core/test_number_bomb.py`: pure calculation and rendering tests.
- Modify `src/dzmm_bot/runtime/contracts.py`: add `source_type` and `chatroom_id` to immutable inbound messages with compatible group defaults.
- Modify `src/dzmm_bot/browser/aikda_socket.py`: maintain selected direct subscriptions and reconcile only `/报数` messages from them.
- Modify `src/dzmm_bot/browser/session.py`: expose the extended read signature while preserving the Playwright fallback.
- Modify `src/dzmm_bot/browser/core_client.py`: serialize inbound provenance and fetch direct-inbound target rooms.
- Modify `src/dzmm_bot/browser/worker.py`: sync direct rooms, fetch active targets, and submit group/direct inbound through the same dedupe path.
- Modify `src/dzmm_bot/core/schema.py`: add inbound provenance, activity detail, and number-bomb records.
- Modify `src/dzmm_bot/core/repository.py`: settings, lobby, roster queues, round state machine, timeout jobs, direct-room targets, activity facts, shared gating, and live AI facts.
- Modify `src/dzmm_bot/core/service.py`: isolate direct commands from activity/random-event/AI/memory processing and support per-reply destinations.
- Modify `src/dzmm_bot/core/commands.py`: route all number-bomb group and direct commands.
- Modify `src/dzmm_bot/core/reply_templates.py`: editable status, validation, round-start, timeout, and terminal messages.
- Modify `src/dzmm_bot/core/ai_knowledge.py`: add the number-bomb topic, aliases, and exact commands.
- Modify `src/dzmm_bot/core/api_models.py` and `src/dzmm_bot/core/app.py`: inbound provenance, direct-target endpoint, and typed settings API.
- Modify `src/dzmm_bot/admin/core_client.py`, `src/dzmm_bot/admin/app.py`, `src/dzmm_bot/admin/templates/index.html`, and `src/dzmm_bot/admin/static/admin.js`: authenticated timeout configuration UI.
- Modify `tests/runtime/test_contracts.py`, `tests/browser/test_aikda_socket.py`, `tests/browser/test_core_client.py`, `tests/browser/test_worker.py`, `tests/core/test_repository.py`, `tests/core/test_service.py`, `tests/core/test_group_commands.py`, `tests/core/test_app.py`, `tests/core/test_ai_knowledge.py`, `tests/admin/test_app.py`, and `tests/deploy/test_artifacts.py`: focused regressions and product verification.

---

### Task 1: Persist provenance and the number-bomb domain

**Files:**
- Create: `migrations/versions/20260810_34_bengbeng_number_bomb.py`
- Modify: `src/dzmm_bot/runtime/contracts.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Test: `tests/runtime/test_contracts.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/deploy/test_artifacts.py`

**Interfaces:**
- Produces: `InboundMessage(platform_message_id: str, sender_platform_id: str, content: str, received_at: datetime, source_type: str = "group", chatroom_id: str | None = None)`.
- Produces: `NumberBombSettingsRecord`, `NumberBombGameRecord`, `NumberBombMemberRecord`, `NumberBombRoundRecord`, and `NumberBombRoundPlayerRecord`.
- Extends: `InboundRecord.source_type`, `InboundRecord.chatroom_id`, and `AIActivityEventRecord.detail`.
- Consumes: existing `UserRecord`, `BeijingDateTime`, UUID, partial-index, and SQLite/PostgreSQL migration conventions.

- [ ] **Step 1: Write failing contract and metadata tests**

Add a compatibility assertion and a direct-message assertion:

```python
group = InboundMessage("g-1", "u-1", "/帮助", NOW)
direct = InboundMessage(
    "d-1", "u-1", "/报数 29", NOW,
    source_type="direct", chatroom_id="direct-1",
)
assert (group.source_type, group.chatroom_id) == ("group", None)
assert (direct.source_type, direct.chatroom_id) == ("direct", "direct-1")
```

Add `test_number_bomb_schema_contains_restart_and_idempotency_constraints` requiring the four game tables plus settings, partial index `ux_number_bomb_one_active`, unique `(game_id, user_id)` members, unique `(game_id, round_number, attempt_number)` rounds, and unique `(round_id, user_id)` round players. Assert inbound provenance defaults to group and activity detail is nullable. Extend the deployment artifact test to assert revision `20260810_34` descends from `20260810_33` and contains all five table names.

- [ ] **Step 2: Run tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/runtime/test_contracts.py -k "inbound_message"
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_repository.py -k "number_bomb_schema"
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/deploy/test_artifacts.py -k "number_bomb"
```

Expected: the new dataclass fields, records, and migration are absent.

- [ ] **Step 3: Add the contract and SQLAlchemy records**

Keep positional compatibility by appending the fields:

```python
@dataclass(frozen=True)
class InboundMessage:
    platform_message_id: str
    sender_platform_id: str
    content: str
    received_at: datetime
    source_type: str = "group"
    chatroom_id: str | None = None
```

Use these table responsibilities:

```text
number_bomb_settings: id=1, inactivity_timeout_minutes
number_bomb_games: active_key, state, target_player_count, round_number,
                   attempt_number, last_activity_at, timestamps, finish_reason
number_bomb_members: game_id, user_id, roster_order, state, queued_at
number_bomb_rounds: game_id, round_number, attempt_number, punishment_type,
                    state, total, player_count, target_numerator,
                    target_denominator, timestamps
number_bomb_round_players: round_id, user_id, display_order,
                           submitted_number, deviation_numerator, result
```

Game states are `signup`, `collecting`, `waiting_continue`, and `ended`, with initial `round_number=0` and `attempt_number=0`. Member states are `current`, `pending_join`, `pending_exit`, and `left`; round states are `collecting`, `settled`, `invalid`, and `abandoned`.

- [ ] **Step 4: Add migration 34**

Use:

```python
revision = "20260810_34"
down_revision = "20260810_33"
```

Add non-null `inbound_messages.source_type` with temporary server default `group`, nullable `chatroom_id`, and nullable `ai_activity_events.detail`. Create the five tables and seed settings row `(1, 10)`. Seed exactly this enabled knowledge card at priority 100:

```python
(
    "number_bomb",
    "蹦蹦数字炸弹",
    ["蹦蹦数字炸弹", "平均数炸弹", "报数", "真心话", "大冒险"],
    "3至10人报名后，每轮玩家私聊发送 /报数 1-100；全员提交后按平均数乘0.8计算。有效轮结算后由当前参与者发送 /继续，具体状态与超时以实时数据为准。",
)
```

Command definitions and templates remain lazy-seeded by the existing repository bootstrap from the exact Task 6 runtime constants. The downgrade deletes only this seeded card, drops game tables in foreign-key order, then drops the three added columns.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 6: Commit the persistence foundation**

```bash
git add migrations/versions/20260810_34_bengbeng_number_bomb.py \
  src/dzmm_bot/runtime/contracts.py src/dzmm_bot/core/schema.py \
  tests/runtime/test_contracts.py tests/core/test_repository.py \
  tests/deploy/test_artifacts.py
git commit -m "feat: add number bomb persistence"
```

### Task 2: Receive only targeted private report commands

**Files:**
- Modify: `src/dzmm_bot/browser/aikda_socket.py`
- Modify: `src/dzmm_bot/browser/session.py`
- Modify: `src/dzmm_bot/browser/core_client.py`
- Modify: `src/dzmm_bot/browser/worker.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/browser/test_aikda_socket.py`
- Test: `tests/browser/test_core_client.py`
- Test: `tests/browser/test_worker.py`
- Test: `tests/core/test_app.py`

**Interfaces:**
- Produces: `ChatGateway.read_new(direct_chatroom_ids: tuple[str, ...] = ()) -> list[InboundMessage]`.
- Produces: `CorePort.direct_inbound_chatroom_ids() -> tuple[str, ...]` and matching `CoreClient` GET call.
- Produces: `CoreRepository.number_bomb_direct_chatroom_ids() -> tuple[str, ...]`.
- Produces: authenticated `GET /internal/direct-inbound/rooms` returning `DirectInboundRoomsResponse(chatroom_ids: list[str])`.
- Consumes: active collecting-round rows and `DirectChatRecord` mappings from Task 1.

- [ ] **Step 1: Write failing gateway tests**

Cover live and history messages for one selected direct room, rejection of an unselected room, rejection of ordinary private text, bot-self filtering, and preserved group behavior:

```python
assert gateway.read_new(("direct-1",)) == []
socket.trigger("message:new", {
    "chatroomId": "direct-1",
    "message": message("dm-1", "employee-1", "/报数 29"),
})
assert gateway.read_new(("direct-1",)) == [
    InboundMessage(
        "dm-1", "employee-1", "/报数 29", SHANGHAI_NOW,
        source_type="direct", chatroom_id="direct-1",
    )
]
```

Assert `message:join-room` is called once per newly selected room, repeated reads do not rejoin, and reconnect/history reconciliation recovers an unseen `/报数` exactly once.

- [ ] **Step 2: Write failing client, worker, and core endpoint tests**

Assert serialized inbound JSON contains `source_type` and `chatroom_id`. Extend `FakeCore` with `direct_rooms_to_read`; verify the worker performs direct-chat discovery first, fetches target IDs, calls `gateway.read_new(targets)`, and submits a direct inbound once. Seed a collecting round plus `DirectChatRecord` in the core test and assert:

```python
response = client.get("/internal/direct-inbound/rooms", headers=headers)
assert response.json() == {"chatroom_ids": ["direct-1"]}
```

Terminal or `waiting_continue` games must return an empty list.

- [ ] **Step 3: Run tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/browser/test_aikda_socket.py tests/browser/test_core_client.py \
  tests/browser/test_worker.py tests/core/test_app.py \
  -k "direct_inbound or targeted_private or inbound_provenance"
```

- [ ] **Step 4: Extend the socket gateway and session protocol**

Store `_direct_chatroom_ids: set[str]`. At each `read_new(targets)`, join newly selected rooms, replace the active target set, reconcile group history plus each selected direct history, and accept messages using:

```python
if chatroom_id == self.chatroom_id:
    source_type = "group"
elif chatroom_id in self._direct_chatroom_ids and text.strip().startswith("/报数"):
    source_type = "direct"
else:
    return
```

Attach the accepted room ID to every Aikda inbound. `_PlaywrightGateway.read_new(...)` keeps reading group messages and ignores nonempty direct targets because direct input requires the socket gateway.

- [ ] **Step 5: Add target lookup and worker orchestration**

`number_bomb_direct_chatroom_ids()` joins the active collecting round players through `UserRecord` and `DirectChatRecord`, ordered by round display order. Add `DirectInboundRoomsResponse`, the core GET route, client method, and `_get` helper. In `BrowserWorker.run_once`, keep this order:

```python
self._sync_direct_chats(gateway, now)
direct_targets = self._core.direct_inbound_chatroom_ids()
messages = gateway.read_new(direct_targets)
```

The existing platform-message dedupe remains shared by both source types.

- [ ] **Step 6: Run tests and verify GREEN**

Run the Step 3 command, then the complete browser suite:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q tests/browser
```

- [ ] **Step 7: Commit targeted direct inbound**

```bash
git add src/dzmm_bot/browser src/dzmm_bot/core/api_models.py \
  src/dzmm_bot/core/app.py src/dzmm_bot/core/repository.py \
  tests/browser tests/core/test_app.py
git commit -m "feat: receive targeted private game commands"
```

### Task 3: Implement exact calculation and fixed result rendering

**Files:**
- Create: `src/dzmm_bot/core/number_bomb.py`
- Create: `tests/core/test_number_bomb.py`

**Interfaces:**
- Produces: `NumberBombEntry(platform_id: str, display_name: str, number: int, display_order: int)`.
- Produces: `NumberBombStanding(entry: NumberBombEntry, deviation_numerator: int, result: str | None)`.
- Produces: `NumberBombCalculation(total: int, player_count: int, target_numerator: int, target_denominator: int, standings: tuple[NumberBombStanding, ...], valid: bool)`.
- Produces: `calculate_number_bomb(entries: Sequence[NumberBombEntry]) -> NumberBombCalculation`.
- Produces: `render_number_bomb_result(round_number: int, punishment_type: str, calculation: NumberBombCalculation) -> str`.

- [ ] **Step 1: Write failing exact-arithmetic tests**

Cover a unique result, tied winners, tied punished players, one/two distinct bands, and values whose two-decimal displays collide while exact numerators differ. Assert the invariant:

```python
calculation = calculate_number_bomb(entries)
assert calculation.target_numerator == 4 * sum(item.number for item in entries)
assert calculation.target_denominator == 5 * len(entries)
assert standing.deviation_numerator == abs(
    5 * len(entries) * standing.entry.number - calculation.target_numerator
)
```

Winner result is `winner`, punished result is `punished`, and all others are `neutral`. Fewer than three exact numerator bands sets `valid is False` and every result to `None`.

- [ ] **Step 2: Write failing rendering tests**

Assert the exact title and three sections, all player numbers, sum/count/average/F, descending deviations, annotations, multiple names in the final result, and truth/dare copy. For invalid calculations assert the third section contains the replay instruction and no winner/punished annotation. Decimal examples must use two digits, including trailing zeros.

- [ ] **Step 3: Run tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q tests/core/test_number_bomb.py
```

Expected: module import fails.

- [ ] **Step 4: Implement exact ranking and formatting**

Use integer numerators for all comparisons:

```python
deviation = abs(5 * player_count * entry.number - 4 * total)
bands = sorted({item.deviation_numerator for item in standings}, reverse=True)
punished_band = bands[1] if len(bands) >= 3 else None
winner_band = bands[-1] if len(bands) >= 3 else None
```

Within equal bands order by `display_order`. Map `truth` to `真心话` and `dare` to `大冒险`. Format rational values with `Decimal(numerator) / Decimal(denominator)` and `quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Step 3 command. Expected: all calculation and format tests pass without database fixtures.

- [ ] **Step 6: Commit the pure domain calculator**

```bash
git add src/dzmm_bot/core/number_bomb.py tests/core/test_number_bomb.py
git commit -m "feat: calculate number bomb results"
```

### Task 4: Manage settings, signup, and next-round rosters

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `NumberBombSettings`, `NumberBombPlayer`, `NumberBombGameSummary`, and `NumberBombGameResult` dataclasses.
- Produces: `get_number_bomb_settings()`, `set_number_bomb_settings(inactivity_timeout_minutes: int)`, and `number_bomb_game_summary()`.
- Produces: `start_number_bomb_game(platform_id: str, target_player_count: int, now: datetime) -> NumberBombGameResult`.
- Produces: `join_number_bomb_game(platform_id: str, now: datetime) -> NumberBombGameResult`, `leave_number_bomb_game(platform_id: str, now: datetime) -> NumberBombGameResult`, `continue_number_bomb_game(platform_id: str, now: datetime) -> NumberBombGameResult`, and `end_number_bomb_game(platform_id: str, now: datetime) -> NumberBombGameResult`.
- Produces: `_start_number_bomb_round(session: Session, game: NumberBombGameRecord, round_number: int, attempt_number: int, now: datetime) -> NumberBombGameResult` and `_finish_number_bomb_game(session: Session, game: NumberBombGameRecord, reason: str, now: datetime) -> NumberBombGameResult`.
- Consumes: records from Task 1, calculator entry snapshots from Task 3, users, `_lock_gameplay_gate`, and existing game-conflict helpers.

- [ ] **Step 1: Write failing settings and initial-lobby tests**

Assert lazy/default settings equal 10, updates accept 1 and 60, and 0/61 raise `ValueError`. Cover target counts 2, 3, 10, 11; missing employee; initiator auto-join; duplicate creation; duplicate join; signup `/退出`; last signup member leaving; and full signup automatically creating round 1 attempt 1 with all players snapshotted in signup order. Snapshot balances before every path and assert they never change; assert no daily-start record is created.

```python
created = repository.start_number_bomb_game("p1", 3, now)
assert created.status == "signup_started"
assert repository.join_number_bomb_game("p2", now).status == "joined"
started = repository.join_number_bomb_game("p3", now)
assert (started.status, started.round_number, started.punishment_type) == (
    "started", 1, "truth",
)
```

- [ ] **Step 2: Write failing roster-queue tests**

During collecting and waiting states, assert nonmembers become FIFO `pending_join`, current members become `pending_exit` but remain in the current round snapshot, candidates can cancel with `/退出`, pending exits cannot be cancelled, projected size 10 rejects another candidate, and duplicate actions do not change `last_activity_at`.

After a valid round fixture, assert `/继续` is restricted to current participants, applies exits before joins, preserves existing roster order, appends candidates FIFO, increments the round, and ends the game when the resulting roster has fewer than 3 players.

- [ ] **Step 3: Run tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_repository.py \
  -k "number_bomb and (settings or signup or join or leave or roster or continue or end)"
```

- [ ] **Step 4: Implement settings, summaries, and lobby start**

Normalize `now` to Beijing time. `start_number_bomb_game` acquires the gameplay gate before checking any active game/event, creates `active_key="global"`, state `signup`, and the initiator member. `_start_number_bomb_round(session, game, round_number, attempt_number, now)` stores the supplied round/attempt values, derives `truth` unless the round is divisible by 3, creates a collecting round and one round-player snapshot per current member, and updates `last_activity_at`.

- [ ] **Step 5: Implement queued membership transitions**

Calculate capacity exactly as:

```python
projected = current_count - pending_exit_count + pending_join_count
if projected >= 10:
    return NumberBombGameResult("next_round_full")
```

Only successful state transitions update `last_activity_at`. `/继续` accepts only `waiting_continue`, marks exits `left`, promotes joins to `current` in `queued_at` order, and calls `_start_number_bomb_round(session, game, game.round_number + 1, 1, now)`; below three calls `_finish_number_bomb_game(session, game, "insufficient_players", now)`.

- [ ] **Step 6: Run tests and verify GREEN**

Run the Step 3 command. Expected: all selected state tests pass.

- [ ] **Step 7: Commit lobby and roster behavior**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: manage number bomb rosters"
```

### Task 5: Submit numbers, settle rounds, and record bounded facts

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `submit_number_bomb(platform_id: str, number: int, now: datetime) -> NumberBombGameResult`.
- Extends: `_record_ai_activity_fact(session: Session, *, event_key: str, user_id: UUID, activity_type: str, result: str, occurred_at: datetime, detail: str | None = None) -> bool` without changing existing callers.
- Consumes: `calculate_number_bomb` and `render_number_bomb_result` from Task 3, collecting rounds from Task 4, and activity-event detail from Task 1.
- `NumberBombGameResult` carries `status`, optional `round_number`, `punishment_type`, `submitted_count`, `player_count`, and `public_message`.

- [ ] **Step 1: Write failing private-submission tests**

Cover no game, wrong state, nonparticipant, values 0/1/100/101, immutable first submission, pending-exit player still eligible, pending-join player ineligible, and successful count progression. Assert only successful first submissions update `last_activity_at`.

- [ ] **Step 2: Write failing valid and invalid settlement tests**

For a valid set, submit all players and assert the last result has `status == "settled"`, stores exact numerators/results, moves the game to `waiting_continue`, and returns the exact public message. For tied winners and tied punished players, assert every affected round-player state. Submit an invalid one/two-band set and assert:

```python
assert result.status == "invalid_round"
assert summary.state == "collecting"
assert (summary.round_number, summary.attempt_number) == (1, 2)
assert all(player.submitted_number is None for player in new_attempt_players)
```

Pending roster changes must survive the invalid attempt untouched.

- [ ] **Step 3: Write failing activity-fact tests**

For each valid round, assert one idempotent activity event per player using key `number_bomb:{game_id}:{round_number}:{attempt_number}:{user_id}`. Winners record `win`, punished players `loss`, neutral players `ended`, and every event stores detail `truth` or `dare`. Invalid rounds and unfinished/timeout games create no activity event.

- [ ] **Step 4: Run tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_repository.py \
  -k "number_bomb and (submit or settlement or invalid_round or activity_fact)"
```

- [ ] **Step 5: Implement locked immutable submissions**

Lock the active game, collecting round, and submitting round-player. Reject when `submitted_number is not None`. After each successful assignment, count submitted snapshots. Before the last submission return `submitted`; on the last submission build ordered `NumberBombEntry` values and calculate exactly once inside the same transaction.

- [ ] **Step 6: Implement valid and invalid terminal paths**

For valid calculations, persist round totals, target ratio, deviations and results; set round `settled`, game `waiting_continue`, and return rendered text. Record activity facts with detail. For invalid calculations, persist the invalid attempt, increment `game.attempt_number`, create a fresh collecting round for the same `round_number`, preserve member queues, and return the invalid rendering.

- [ ] **Step 7: Run tests and verify GREEN**

Run the Step 4 command, then repeat the last-submission test twice to verify database idempotency.

- [ ] **Step 8: Commit round settlement**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: settle number bomb rounds"
```

### Task 6: Route group/direct commands and destination-aware replies

**Files:**
- Modify: `src/dzmm_bot/core/service.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/browser/core_client.py`
- Test: `tests/core/test_service.py`
- Test: `tests/core/test_group_commands.py`
- Test: `tests/core/test_app.py`
- Test: `tests/browser/test_core_client.py`

**Interfaces:**
- Extends: `CommandReply` with `destination_chatroom_id: str | None = None` and `delivery_kind: str = "group"`.
- Consumes: repository statuses from Tasks 4–5 and inbound provenance from Task 1.
- Produces: `/蹦蹦数字炸弹`, `/报数`, number-bomb-aware `/加入`, `/退出`, `/继续`, and `/结束游戏` routing.

- [ ] **Step 1: Write failing direct-service isolation tests**

Post a direct inbound payload with `source_type="direct"` and `chatroom_id="direct-1"`. Assert it is stored with provenance, does not call `record_activity`, `record_random_event_round`, AI mention handling, or memory batching, and queues its acknowledgement with destination `direct-1` and delivery kind `number_bomb_private`.

Before the last report assert no group outbound contains any submitted number or progress. For the last report assert two outbounds in order: direct acknowledgement at reply index 0 and the complete group result at reply index 1 with `destination_chatroom_id is None` and `delivery_kind == "group"`. The private acknowledgement must contain no other player's number or submission state. Duplicate platform message IDs create neither duplicate acknowledgement nor result.

- [ ] **Step 2: Write failing group-command tests**

Cover exact creation syntax, missing/invalid counts, auto-joined initiator, initial `/加入`, queued `/加入`, initial and queued `/退出`, `/继续`, participant and nonparticipant `/结束游戏`, and group `/报数 29` rejection. Assert round-start copy includes player names, round number/type, and private submission instruction.

Verify routing precedence when a number-bomb game is active:

```text
/加入 -> number bomb before blame/undercover/memory/random event
/退出 -> number bomb before random event
/继续 -> number bomb when waiting_continue
/结束游戏 -> number bomb before blame/undercover
```

- [ ] **Step 3: Run tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_service.py tests/core/test_group_commands.py \
  tests/core/test_app.py tests/browser/test_core_client.py \
  -k "number_bomb or direct_inbound"
```

- [ ] **Step 4: Isolate direct handling in `CoreService`**

Persist every accepted direct `/报数`, then bypass activity, random events, mentions, and memory. A direct inbound whose command token is not `/报数` must return without invoking any group command or business method, even if posted directly to the internal API. Enqueue handler replies with their explicit destinations:

```python
self._repository.enqueue_outbound(
    stored.id,
    reply.text,
    reply_index,
    destination_chatroom_id=reply.destination_chatroom_id,
    delivery_kind=reply.delivery_kind,
)
```

Guard against a direct handler reply without a destination so it can never leak into the group. Group processing remains unchanged and sets `ai_memory_eligible=False` for slash commands.

- [ ] **Step 5: Add commands and templates**

Register these exact command definitions:

```python
("/蹦蹦数字炸弹", "/蹦蹦数字炸弹 人数", "创建3至10人蹦蹦数字炸弹报名局"),
("/报数", "/报数 1-100（仅私聊）", "提交蹦蹦数字炸弹本轮整数"),
```

Add these exact template defaults; variables are the brace tokens shown in each value:

```python
NUMBER_BOMB_TEMPLATE_DEFAULTS = {
    ("/蹦蹦数字炸弹", "usage"): "请用 /蹦蹦数字炸弹 3-10 创建报名局。",
    ("/蹦蹦数字炸弹", "signup_started"): "【蹦蹦数字炸弹】{昵称} 发起了 {人数} 人局，当前 {当前人数}/{人数} 人，请发送 /加入 报名。",
    ("/蹦蹦数字炸弹", "not_joined"): "请先用 /入职 名字 加入摸鱼公司。",
    ("/蹦蹦数字炸弹", "multiplayer_active"): "当前已有游戏或随机事件进行中。",
    ("/蹦蹦数字炸弹", "already_active"): "当前已有蹦蹦数字炸弹对局。",
    ("/蹦蹦数字炸弹", "idle_timeout"): "蹦蹦数字炸弹长时间无人操作，本场已自动结束。",
    ("/加入", "number_bomb_joined"): "{昵称} 已加入蹦蹦数字炸弹，当前 {当前人数}/{人数} 人。",
    ("/加入", "number_bomb_started"): "【蹦蹦数字炸弹】第 {轮次} 轮 - {惩罚类型}\n参与者：{玩家列表}\n请各位私聊总监事发送 /报数 1-100。",
    ("/加入", "number_bomb_queued"): "你已进入蹦蹦数字炸弹下一轮候选名单。",
    ("/加入", "number_bomb_next_round_full"): "蹦蹦数字炸弹下一轮人数已满。",
    ("/加入", "number_bomb_already_joined"): "你已经在当前蹦蹦数字炸弹对局中。",
    ("/加入", "number_bomb_not_joined"): "请先用 /入职 名字 加入摸鱼公司。",
    ("/退出", "number_bomb_signup_left"): "你已退出蹦蹦数字炸弹报名。",
    ("/退出", "number_bomb_exit_queued"): "你将在本轮结算后退出，当前轮仍需私聊报数。",
    ("/退出", "number_bomb_candidate_cancelled"): "你已取消加入蹦蹦数字炸弹下一轮。",
    ("/退出", "number_bomb_cannot_leave"): "当前没有你可以退出的蹦蹦数字炸弹对局。",
    ("/报数", "group_only"): "请私聊总监事发送 /报数 1-100，群内报数不会生效。",
    ("/报数", "submitted"): "报数成功，本轮数字已锁定。",
    ("/报数", "invalid_number"): "请发送 /报数 1-100，数字必须是范围内的整数。",
    ("/报数", "duplicate"): "你本轮已经报过数，不能修改。",
    ("/报数", "not_participant"): "你不是当前轮参与者，无法报数。",
    ("/报数", "not_collecting"): "当前没有正在收集数字的蹦蹦数字炸弹轮次。",
    ("/报数", "result"): "{结果正文}",
    ("/继续", "number_bomb_started"): "【蹦蹦数字炸弹】第 {轮次} 轮 - {惩罚类型}\n参与者：{玩家列表}\n请各位私聊总监事发送 /报数 1-100。",
    ("/继续", "number_bomb_insufficient"): "下一轮参与者不足3人，本场游戏结束。",
    ("/继续", "number_bomb_cannot_continue"): "当前没有等待继续的蹦蹦数字炸弹对局。",
    ("/结束游戏", "number_bomb_ended"): "【蹦蹦数字炸弹】本场已由参与者结束。",
    ("/结束游戏", "number_bomb_cannot_end"): "当前没有你可以结束的蹦蹦数字炸弹对局。",
}
```

Map every repository status to one of these scenarios. Use the pure rendered body as `{结果正文}` for both settled and invalid results. A direct `_number_bomb_submit` returns `CommandReply` objects targeted to `message.chatroom_id`; its last result appends a group `CommandReply`.

- [ ] **Step 6: Serialize provenance through core HTTP**

Add optional/defaulted `source_type: Literal["group", "direct"] = "group"` and `chatroom_id: str | None = None` to `InboundRequest`; validate that direct messages have a room. CoreClient always sends both values, and the app constructs the complete `InboundMessage`.

- [ ] **Step 7: Run tests and verify GREEN**

Run the Step 3 command, then:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_service.py tests/core/test_group_commands.py tests/browser/test_core_client.py
```

- [ ] **Step 8: Commit command integration**

```bash
git add src/dzmm_bot/core/service.py src/dzmm_bot/core/commands.py \
  src/dzmm_bot/core/reply_templates.py src/dzmm_bot/core/repository.py \
  src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py \
  src/dzmm_bot/browser/core_client.py tests/core/test_service.py \
  tests/core/test_group_commands.py tests/core/test_app.py \
  tests/browser/test_core_client.py
git commit -m "feat: expose number bomb commands"
```

### Task 7: Enforce inactivity, restart recovery, and shared game exclusion

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/service.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_service.py`

**Interfaces:**
- Produces: `run_number_bomb_jobs(now: datetime) -> list[str]` and its call from `run_daily_jobs`.
- Consumes: latest settings, `last_activity_at`, shared gameplay gate, system outbound queue, and all number-bomb states.

- [ ] **Step 1: Write failing timeout tests for all active states**

Parametrize `signup`, `collecting`, and `waiting_continue`. At `last_activity_at + configured minutes`, assert one timeout group outbound, state ended, active key cleared, open collecting round abandoned, and no activity fact. Run jobs twice and reconstruct a second repository on the same session factory; assert no duplicate message or transition.

Change settings from 10 to 1 after nine idle minutes and assert the next job immediately expires the game. Assert ordinary group text, malformed/duplicate/unauthorized game commands, and group `/报数` do not refresh; successful join/exit/private report/continue do refresh.

- [ ] **Step 2: Write failing mutual-exclusion tests**

Assert random event, hide-and-seek selecting, memory assessment, undercover, and blame prevent number-bomb creation. Assert number-bomb signup/collecting/waiting prevents each conflicting game and causes due random-event schedules to be marked `skipped`, not queued or started. Add a PostgreSQL-only race between number-bomb creation and a random-event trigger using two repositories and `Barrier(2)`; exactly one may become active.

- [ ] **Step 3: Write failing ordinary-memory boundary test**

While a player is in number bomb, send normal group text and assert existing ordinary observation eligibility remains true. Send direct `/报数` and group game commands and assert their `InboundRecord.ai_memory_eligible` remains false and pending memory counts do not increase.

- [ ] **Step 4: Run tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_repository.py tests/core/test_service.py \
  -k "number_bomb and (timeout or restart or conflict or random_event or memory_boundary)"
```

- [ ] **Step 5: Implement idempotent jobs and shared gate checks**

Calculate expiry from the current settings every run:

```python
deadline = game.last_activity_at + timedelta(
    minutes=settings.inactivity_timeout_minutes
)
```

When due, lock and finish once, abandon a collecting round, enqueue the fixed group timeout template, and clear `active_key`. Call `run_number_bomb_jobs(now)` before random-event scheduling in `run_daily_jobs`.

Add `NumberBombGameRecord.active_key == "global"` to `_has_active_game` and to explicit conflict checks used by hide-and-seek, memory assessment, undercover, and blame starts. Number-bomb start acquires `_lock_gameplay_gate` first. Do not add number-bomb membership to `user_has_active_game_context`; slash/direct filtering already excludes game commands while ordinary group speech must remain observable.

- [ ] **Step 6: Run tests and verify GREEN**

Run the Step 4 command and existing conflict suites:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_repository.py tests/core/test_service.py \
  -k "random_event or hide_and_seek or memory_assessment or undercover or blame or number_bomb"
```

- [ ] **Step 7: Commit recovery and exclusion**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/service.py \
  tests/core/test_repository.py tests/core/test_service.py
git commit -m "feat: recover and release number bomb games"
```

### Task 8: Expose timeout settings in the core and admin console

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Test: `tests/core/test_app.py`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Produces: `GET/PATCH /internal/game/number-bomb/settings`.
- Produces: `GET/PATCH /api/game/number-bomb/settings` with existing version and idempotency headers.
- Consumes: `get_number_bomb_settings()` and `set_number_bomb_settings(...)` from Task 4.

- [ ] **Step 1: Write failing typed core API tests**

Assert authenticated GET returns `{"inactivity_timeout_minutes": 10}`, PATCH accepts 1 and 60, 0/61 returns 422, and missing core token returns 401. Use Pydantic:

```python
class NumberBombSettingsResponse(ApiModel):
    inactivity_timeout_minutes: int

class SetNumberBombSettingsRequest(ApiModel):
    inactivity_timeout_minutes: int = Field(ge=1, le=60)
```

- [ ] **Step 2: Write failing admin proxy and static-surface tests**

Extend `FakeCore` with get/set methods. Assert authenticated admin GET/PATCH, `If-Match`, `Idempotency-Key`, version increment, conflict handling, and relay of core validation. Assert HTML/JS contain `number-bomb-settings-card`, `edit-number-bomb-settings`, `number-bomb-timeout-minutes`, the settings endpoints, and the displayed `1–60` bounds.

- [ ] **Step 3: Run tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_app.py tests/admin/test_app.py -k "number_bomb_settings"
```

- [ ] **Step 4: Add core and admin APIs**

Core routes use existing `X-Core-Token` authorization and return the typed model. Add `AdminCorePort.get_number_bomb_settings() -> dict` and `AdminCorePort.set_number_bomb_settings(settings: dict) -> dict` plus HTTP implementations. Admin PATCH requires only `inactivity_timeout_minutes` and calls `versioned_configuration_response(identity, idempotency_key, if_match, mutation, scope="number-bomb-settings")`.

- [ ] **Step 5: Add the minimal gameplay-settings UI**

Add a third “小游戏” tab under `settings-view`, with a rule summary, settings card, and one edit button. Reuse the existing modal/card CSS; the modal contains exactly one numeric input (`min="1"`, `max="60"`) and Save/Cancel controls. Extend settings-view loading to fetch economy, activity, and number-bomb settings; save with current configuration version and refresh the server value.

- [ ] **Step 6: Run tests and verify GREEN**

Run the Step 3 command, then all admin tests:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q tests/admin
```

- [ ] **Step 7: Commit settings management**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py \
  src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py \
  src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js \
  tests/core/test_app.py tests/admin/test_app.py
git commit -m "feat: configure number bomb timeout"
```

### Task 9: Add authoritative guidance and verify the complete feature

**Files:**
- Modify: `src/dzmm_bot/core/ai_knowledge.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Test: `tests/core/test_ai_knowledge.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Adds topic: `number_bomb`.
- Adds exact commands: `/蹦蹦数字炸弹`, `/报数`, `/加入`, `/退出`, `/继续`, `/结束游戏`.
- Consumes: settings/summary and activity facts from earlier tasks.
- Produces: deployment-ready local verification evidence.

- [ ] **Step 1: Write failing AI routing and live-fact tests**

Assert questions containing “蹦蹦数字炸弹”“平均数炸弹”“报数” route to `number_bomb`; `/报数` maps exactly. Build authoritative context and assert it contains the timeout, player/number ranges, current state, exact command syntax, private-report instruction, and no private numbers or room IDs. Extend the API knowledge-topic literal, add `number_bomb` to the admin knowledge-card topic select and activity-type label, and map activity result `ended` to “已参与”.

- [ ] **Step 2: Implement topic and live facts**

Add:

```python
"number_bomb": (
    "/蹦蹦数字炸弹", "/报数", "/加入", "/退出", "/继续", "/结束游戏",
)
```

Use aliases `("蹦蹦数字炸弹", "平均数炸弹", "报数", "真心话", "大冒险")`. Live facts state only `3–10` players, `1–100` integers, timeout, truth/truth/dare cycle, and current public state. It must never include submitted values.

- [ ] **Step 3: Run focused guidance tests**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_ai_knowledge.py tests/core/test_repository.py \
  tests/admin/test_app.py -k "number_bomb or authoritative_context"
```

- [ ] **Step 4: Run migration and static checks**

Use a disposable SQLite database, not production:

```bash
dzmm_tmp_db="$(mktemp -d)/number-bomb.db"
DZMM_DATABASE_URL="sqlite+pysqlite:///$dzmm_tmp_db" \
  PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/alembic upgrade head
git diff --check
```

Expected: Alembic reaches `20260810_34` and `git diff --check` is silent.

- [ ] **Step 5: Run all targeted feature tests**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/runtime/test_contracts.py tests/browser tests/core/test_number_bomb.py \
  tests/core/test_repository.py tests/core/test_service.py \
  tests/core/test_group_commands.py tests/core/test_app.py \
  tests/core/test_ai_knowledge.py tests/admin/test_app.py \
  tests/deploy/test_artifacts.py -k "number_bomb or direct_inbound or inbound_provenance"
```

- [ ] **Step 6: Run the complete suite**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q
```

Expected: zero failures; only existing optional external-integration skips remain.

- [ ] **Step 7: Review scope and commit final guidance**

```bash
git status --short
number_bomb_base="$(git config --get codex.numberBombBase)"
test -n "$number_bomb_base"
git diff --name-only "$number_bomb_base"..HEAD
git log --oneline --decorate -12
```

Changed files must be limited to the migration, number-bomb design/plan, listed runtime/browser/core/admin files, and targeted tests. Then commit:

```bash
git add src/dzmm_bot/core/ai_knowledge.py src/dzmm_bot/core/repository.py \
  src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js \
  tests/core/test_ai_knowledge.py tests/core/test_repository.py \
  tests/admin/test_app.py
git commit -m "feat: guide players through number bomb"
```

- [ ] **Step 8: Stop before integration or deployment**

Report the worktree path, branch, commit range, full test count, skipped optional tests, migration head, and unchanged user-owned files. Wait for explicit approval before merging, pushing, or deploying to port `18090`.
