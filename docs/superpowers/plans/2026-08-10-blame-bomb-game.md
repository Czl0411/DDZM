# Blame Bomb Game Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete persistent `/甩锅游戏` single-round bomb game, including economy, timers, commands, internal APIs, and the admin console.

**Architecture:** Add focused blame-game tables and repository state transitions while retaining the project's existing monolithic repository, command router, FastAPI core, and vanilla admin UI patterns. All creation and terminal transitions use the existing shared gameplay gate plus row locks; absolute deadlines and player guarantee states make restarts and repeated jobs idempotent.

**Tech Stack:** Python 3.12+, SQLAlchemy 2, Alembic, PostgreSQL/SQLite, FastAPI, pytest, vanilla JavaScript/HTML/CSS.

## Global Constraints

- Implement the approved behavior in `rule.md` section 12 and `docs/superpowers/specs/2026-08-10-blame-bomb-game-design.md`.
- Player count is exactly `2–10`; signup defaults to `120` seconds and each turn defaults to `30` seconds.
- The hidden explosion deadline never resets after a successful transfer and is never exposed by the API or admin UI.
- Every successful reason must contain all `1–4` snapshotted keywords; matching is deterministic and never calls DeepSeek.
- Two-player games permit immediate return transfers; games with three or more players reject them.
- The loser nets `-(N-1)` and each other player nets `+1`; cancellation refunds all held guarantees.
- Only the initiator consumes their rank's Beijing-calendar-day multiplayer start allowance; a created signup consumes one and never returns it.
- Any current participant may use `/结束游戏`; nonparticipants may not.
- Do not add a next-game queue, private game messages, or unrelated refactors.
- Do not push or deploy after implementation; stop with local verification evidence.

## File Structure

- Create `migrations/versions/20260810_30_blame_bomb_game.py`: all blame-game tables, constraints, and seeded timing defaults.
- Modify `src/dzmm_bot/core/schema.py`: SQLAlchemy records only.
- Modify `src/dzmm_bot/core/repository.py`: dataclasses, validation helpers, state machine, jobs, balance changes, and game-lock integration.
- Modify `src/dzmm_bot/core/reply_templates.py`: editable group reply scenarios.
- Modify `src/dzmm_bot/core/commands.py`: parse and route `/甩锅游戏`, `/甩锅`, `/退出甩锅`, `/加入`, and `/结束游戏`.
- Modify `src/dzmm_bot/core/api_models.py` and `src/dzmm_bot/core/app.py`: typed internal management API.
- Modify `src/dzmm_bot/admin/app.py`, `src/dzmm_bot/admin/templates/index.html`, and `src/dzmm_bot/admin/static/admin.js`: authenticated proxy routes and the management page.
- Modify `tests/core/test_repository.py`, `tests/core/test_commands.py`, `tests/core/test_app.py`, and `tests/admin/test_app.py`: behavior, API, concurrency, and UI regressions.

---

### Task 1: Persist the blame-game domain

**Files:**
- Create: `migrations/versions/20260810_30_blame_bomb_game.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `BlameGameSettingsRecord`, `BlameGameDurationRuleRecord`, `BlameIncidentCardRecord`, `BlameGameRecord`, `BlameGamePlayerRecord`, `BlameGameTransferRecord`, and `BlameGameDailyStartRecord`.
- Consumes: existing `UserRecord`, `BeijingDateTime`, and PostgreSQL/SQLite partial-index conventions.

- [ ] **Step 1: Write failing metadata and migration tests**

Add `test_blame_game_schema_contains_state_and_idempotency_constraints` to assert all seven table names, the partial unique active-game index, player/game uniqueness, normalized-reason uniqueness, and daily user/date uniqueness. Extend `test_migration_creates_all_runtime_tables` to require the seven names. Add `test_blame_game_migration_seeds_duration_defaults` using `migrated_postgres_url` and assert:

```python
assert rows == [
    (2, 45, 75), (3, 60, 90), (4, 75, 120),
    (5, 90, 135), (6, 90, 150), (7, 105, 165),
    (8, 120, 180), (9, 135, 210), (10, 150, 240),
]
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_repository.py -k "blame_game_schema or blame_game_migration"
```

Expected: missing table/classes and migration assertions fail.

- [ ] **Step 3: Add schema records and migration**

Use revision `20260810_30` with down revision `20260809_29`. Define the active game index exactly as:

```python
Index(
    "ux_blame_game_one_active",
    "active_key",
    unique=True,
    sqlite_where=text("active_key IS NOT NULL"),
    postgresql_where=text("active_key IS NOT NULL"),
)
```

Use `JSON` for `keywords_snapshot` and card `keywords`. Give players `signup_order`, nullable `seat_number`, `state`, `guarantee_amount`, and `guarantee_state`. Give games absolute Beijing datetimes for signup, explosion, turn, start, and finish; nullable current/previous/loser user foreign keys; `settlement_complete`; and frozen incident fields. Give transfers `reason`, `normalized_reason`, `from_user_id`, `to_user_id`, and `created_at` with `UniqueConstraint("game_id", "normalized_reason")`.

- [ ] **Step 4: Run schema and migration tests and verify GREEN**

Run the Step 2 command. Expected locally: metadata test passes and PostgreSQL migration test skips only when `TEST_DATABASE_URL` is unset.

- [ ] **Step 5: Commit the persistence foundation**

```bash
git add migrations/versions/20260810_30_blame_bomb_game.py src/dzmm_bot/core/schema.py tests/core/test_repository.py
git commit -m "feat: add blame bomb game schema"
```

### Task 2: Manage settings and incident cards

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `BlameGameSettings`, `BlameGameDurationRule`, `BlameIncidentCard` dataclasses.
- Produces: `get_blame_game_settings()`, `set_blame_game_settings(...)`, `list_blame_incident_cards_page(...)`, `create_blame_incident_card(...)`, `update_blame_incident_card(...)`, and `delete_blame_incident_card(...)`.
- Consumes: records from Task 1.

- [ ] **Step 1: Write failing settings and card tests**

Add tests that assert lazy defaults, all nine duration rows, invalid min/max rejection, 1–4 trimmed unique keywords, case-insensitive duplicate English keywords, pagination, update/disable, and deletion. Use these calls:

```python
settings = repository.get_blame_game_settings()
card = repository.create_blame_incident_card(
    "咖啡事故", "咖啡泼到了季度报表", ["咖啡", "报表", "deadline"]
)
updated = repository.update_blame_incident_card(
    card.id, "咖啡事故", "描述更新", ["咖啡", "报表"], False
)
assert repository.delete_blame_incident_card(card.id) is True
```

- [ ] **Step 2: Run focused tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_repository.py -k "blame_settings or blame_incident"
```

Expected: repository interfaces do not exist.

- [ ] **Step 3: Implement dataclasses, defaults, and validation**

Add constants for the approved defaults and `_validate_blame_keywords`. Normalize each keyword with `.strip()`, reject blanks, reject counts outside 1–4, and compare `casefold()` values for uniqueness. `set_blame_game_settings` must require the exact player-count set `set(range(2, 11))`, positive integers, and `minimum_seconds <= maximum_seconds`.

Define signatures:

```python
def set_blame_game_settings(
    self,
    enabled: bool,
    signup_timeout_seconds: int,
    turn_timeout_seconds: int,
    durations: list[tuple[int, int, int]],
) -> BlameGameSettings: ...

def list_blame_incident_cards_page(
    self, page: int, page_size: int
) -> tuple[list[BlameIncidentCard], int]: ...
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit configuration management**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: manage blame bomb rules and incidents"
```

### Task 3: Create, join, and start a lobby

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `BlameGameResult` and `BlameGameSummary` dataclasses.
- Produces: `start_blame_game(platform_id: str, player_count: int, now: datetime)`, `join_blame_game(platform_id: str, now: datetime)`, `leave_blame_game(platform_id: str, now: datetime)`, and `blame_game_summary()`.
- Consumes: `_lock_gameplay_gate`, settings/cards from Task 2, rank `multiplayer_game_limit`, users, and Task 1 records.

- [ ] **Step 1: Write failing lobby tests**

Cover invalid 1/11 players, disabled game, missing user, no enabled incident, initiator balance below `N-1`, rank limit zero, daily limit consumption only after creation, duplicate creation, duplicate join, join balance, signup leave, and active-game join rejection. Add parametrized 2–10 player start tests and assert:

```python
assert result.status == "started"
assert [player.seat_number for player in summary.players] == list(range(1, count + 1))
assert summary.incident_keywords == ("咖啡", "报表")
assert summary.current_holder_number in range(1, count + 1)
assert all(repository.find_user(pid).balance == opening_balance - (count - 1) for pid in ids)
```

Add a test that spends one registrant's balance after joining; when the last player joins, the insufficient player is removed, no guarantees remain held, and the signup continues.

- [ ] **Step 2: Run lobby tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_repository.py -k "blame and (start or signup or join or daily_limit)"
```

Expected: lobby methods are missing.

- [ ] **Step 3: Implement creation and daily allowance**

Acquire `_lock_gameplay_gate(session)` before any other row lock. Resolve the initiator's current `RankRecord`; treat a missing rank as the seeded default rank. Lock/create `BlameGameDailyStartRecord`, compare its count with `multiplayer_game_limit`, create the `signup` game and initiator player, then increment only after all creation checks pass.

Return stable statuses including `signup_started`, `invalid_player_count`, `not_joined`, `disabled`, `insufficient_balance`, `daily_limit`, `incident_unavailable`, `multiplayer_active`, and `already_active`.

- [ ] **Step 4: Implement join, leave, and atomic start**

`join_blame_game` locks the active game and registrants. On reaching the target, remove every insufficient player, then either remain `signup` or call `_start_blame_game_round(session, game, players, settings, now)`. That helper freezes one enabled card, assigns continuous seats, applies each `-(N-1)` balance transaction with source `blame_guarantee`, chooses inclusive duration using `randbelow(maximum - minimum + 1) + minimum`, chooses a holder, and sets both deadlines.

- [ ] **Step 5: Run lobby tests and verify GREEN**

Run the Step 2 command and the existing rank tests:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_repository.py -k "blame or rank"
```

- [ ] **Step 6: Commit the lobby state machine**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: add blame bomb lobby and start"
```

### Task 4: Validate and transfer the bomb

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `_normalize_blame_reason(reason: str) -> str`, `_blame_temperature(game, now) -> str`, and `transfer_blame(platform_id: str, target_number: int, reason: str, now: datetime) -> BlameGameResult`.
- Consumes: active game/player records and snapshotted keywords from Tasks 1 and 3.

- [ ] **Step 1: Write failing deterministic-rule tests**

Add tests for all keywords, missing keyword list, English case-insensitivity, continuous Chinese matching, punctuation/whitespace/case normalization, exact duplicate rejection, changed word order acceptance, self target, nonexistent seat, nonholder, and retry after invalid input. Explicitly assert invalid requests preserve holder and both deadlines.

Add a two-player immediate-return test and a three-player rejection test:

```python
first = repository.transfer_blame(holder_id, target, valid_reason_1, now)
second = repository.transfer_blame(target_id, original_holder, valid_reason_2, now + timedelta(seconds=1))
assert second.status == expected_status  # transferred for 2, immediate_return_blocked for 3
```

- [ ] **Step 2: Run transfer tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_repository.py -k "blame and (transfer or keyword or reason or return)"
```

- [ ] **Step 3: Implement normalization, keyword matching, and temperature**

Use `unicodedata.category(character).startswith("P")` to remove Unicode punctuation, `casefold()` for letters, `re.sub(r"\s+", " ", value.strip())` for whitespace, and case-folded containment for each keyword. Calculate temperature from `(explosion_deadline - now) / total_duration_seconds` with exact stage boundaries `> .70`, `> .40`, `> .15`, else final.

- [ ] **Step 4: Implement locked transfer**

Lock the active game before selecting users/transfers. Successful transfers insert the unique normalized reason, set `previous_holder_user_id`, set the target holder, and set:

```python
game.turn_deadline = min(
    now + timedelta(seconds=settings.turn_timeout_seconds),
    game.explosion_deadline,
)
```

- [ ] **Step 5: Run transfer tests and verify GREEN**

Run the Step 2 command. Expected: all deterministic rule tests pass.

- [ ] **Step 6: Commit transfer behavior**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: validate blame bomb transfers"
```

### Task 5: Settle, cancel, and recover games

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `_settle_blame_game(session, game, loser_user_id, reason, now)`, `_cancel_blame_game(session, game, reason, now)`, active-state behavior in `leave_blame_game(...)`, `end_blame_game(...)`, `admin_end_blame_game(...)`, and `run_blame_game_jobs(now)`.
- Consumes: guarantee/player records, `_apply_balance_change`, `_blame_temperature`, and `transfer_blame` from Task 4.

- [ ] **Step 1: Write failing economy and timeout tests**

For 2–10 players, snapshot balances before signup and assert after settlement that the loser changed by `-(N-1)`, every winner by `+1`, and the total is unchanged. Cover global explosion, turn timeout, a transfer received after either deadline, active `/退出甩锅`, participant `/结束游戏`, nonparticipant rejection, admin cancellation, signup timeout, and cancellation refund.

Run each terminal method twice and call `run_blame_game_jobs` twice; assert balances and transaction counts do not change on the second call. Add a restart-style test that constructs a second repository over the same session factory after deadlines and settles once.

- [ ] **Step 2: Run settlement tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_repository.py -k "blame and (settle or timeout or cancel or refund or leave or jobs)"
```

- [ ] **Step 3: Implement idempotent settlement and cancellation**

Normal settlement leaves the loser's held guarantee untouched, credits each winner `N` with source `blame_win`, marks player guarantee states `settled`, writes the loser/reason, sets `settlement_complete`, clears `active_key`, and moves to `settled`. Cancellation credits each held guarantee with source `blame_refund`, marks it `refunded`, clears the key, and moves to `cancelled`. Return without balance changes when the game is already terminal.

At the beginning of `transfer_blame`, after locking the game, compare the request receive time with both deadlines. If either deadline has passed, call `_settle_blame_game` with the current holder and return the settled result without validating or inserting the requested transfer.

- [ ] **Step 4: Implement jobs and automatic messages**

`run_blame_game_jobs` locks the one active game. For signup expiry set `dissolved`. For active games, settle if either deadline is due; otherwise compare current temperature with `last_announced_temperature` and enqueue only newly crossed stage text. Add `self.run_blame_game_jobs(now)` to `run_daily_jobs` before random-event scheduling so the shared gate sees a freshly released terminal game.

- [ ] **Step 5: Run settlement and existing job tests**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_repository.py -k "blame or daily_jobs or random_event_jobs or undercover_jobs"
```

- [ ] **Step 6: Commit terminal behavior**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: settle and recover blame bomb games"
```

### Task 6: Integrate mutual exclusion, commands, and replies

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_commands.py`

**Interfaces:**
- Produces group command routing and editable reply scenarios.
- Consumes all repository result statuses from Tasks 3–5.

- [ ] **Step 1: Write failing mutual-exclusion tests**

Assert an active blame signup/round blocks random-event manual and scheduled starts, memory duel, and undercover. Assert each of those active games blocks blame creation. Verify single memory and hide-and-seek do not block blame. Add a PostgreSQL-only race between blame creation and random-event jobs using `Barrier(2)`; assert exactly one becomes active.

- [ ] **Step 2: Write failing command tests**

Add command tests for parsing `/甩锅游戏 6`, invalid usage, no-argument `/加入`, active-game join rejection, `/退出甩锅`, `/甩锅 3 理由`, participant `/结束游戏`, and nonparticipant rejection. Assert replies render fixed seat lists, incident text, missing keywords, temperature, winner/loser values, currency, and balances.

- [ ] **Step 3: Run tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_repository.py -k "blame and (random_event or memory or undercover or postgres)" \
  tests/core/test_commands.py -k "blame"
```

- [ ] **Step 4: Extend shared gate checks**

Add `BlameGameRecord.active_key == "global"` to the random-event `_has_active_game` predicate. Add `_active_blame_game(session)` checks after the shared gate in undercover and memory-duel creation. `start_blame_game` must use the same gate before checking random event, memory duel, or undercover. Keep joins/progress outside the shared gate.

- [ ] **Step 5: Add commands and reply templates**

Add command definitions for `/甩锅游戏`, `/甩锅`, and `/退出甩锅`, and include them in `_RANDOM_EVENT_CONFIGURABLE_COMMANDS`. Route no-argument `/加入` to an active blame game before undercover/memory duel. Route `/结束游戏` to blame when a blame game is active; otherwise retain undercover behavior. Map every repository status to a named template rather than hard-coded command copy.

- [ ] **Step 6: Run command and mutual-exclusion tests and verify GREEN**

Run the Step 3 commands separately so each `-k` expression applies to its own file. Expected: all selected tests pass; PostgreSQL race skips only without `TEST_DATABASE_URL`.

- [ ] **Step 7: Commit group integration**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py \
  src/dzmm_bot/core/reply_templates.py tests/core/test_repository.py tests/core/test_commands.py
git commit -m "feat: expose blame bomb group commands"
```

### Task 7: Expose typed core management APIs

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Test: `tests/core/test_app.py`

**Interfaces:**
- Produces: `/internal/game/blame-bomb/settings`, `/incidents`, `/session`, and `/end` routes.
- Consumes: repository settings/cards/summary/admin cancellation methods.

- [ ] **Step 1: Write failing API tests**

Cover authenticated read/update settings, invalid duration maps, paginated card CRUD, public session state, hidden deadline fields, and admin end/refund. Assert session JSON contains `state`, `target_player_count`, `players`, `incident`, `current_holder`, and `temperature`, and does not contain `total_duration_seconds`, `explosion_deadline`, or `turn_deadline`.

- [ ] **Step 2: Run API tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_app.py -k "blame_bomb"
```

- [ ] **Step 3: Add request/response models**

Use Pydantic bounds: settings seconds `ge=1, le=3600`, player counts `ge=2, le=10`, card fields `1–2000` characters, and keywords `min_length=1, max_length=4`. Model durations as a list of objects with `player_count`, `minimum_seconds`, and `maximum_seconds` so duplicate counts can be rejected by the repository.

- [ ] **Step 4: Add core routes and response conversion**

Use the existing `X-Core-Token` dependency and convert repository `ValueError` to HTTP 422. Card create returns 201; update returns 200; delete returns `AcceptedResponse`; session returns only public data; `/end` calls `admin_end_blame_game(clock())`.

- [ ] **Step 5: Run API tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 6: Commit core APIs**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py tests/core/test_app.py
git commit -m "feat: add blame bomb management api"
```

### Task 8: Build the admin management page

**Files:**
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Produces authenticated `/api/game/blame-bomb/*` admin proxy routes and browser controls.
- Consumes Task 7 core API client methods and existing versioned configuration helpers.

- [ ] **Step 1: Write failing admin proxy and HTML tests**

Test list/update settings, incident create/update/delete, session fetch, and force end through authenticated admin routes. Assert the rendered HTML contains `data-view="blame-bomb"`, `blame-bomb-settings-card`, `blame-bomb-session-card`, `blame-incident-list`, `edit-blame-bomb-settings`, and `create-blame-incident`.

- [ ] **Step 2: Run admin tests and verify RED**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/admin/test_app.py -k "blame_bomb"
```

- [ ] **Step 3: Add versioned proxy routes**

Use `versioned_configuration_response` with scopes `blame-bomb:settings`, `blame-bomb:incidents`, and `blame-bomb:incident:{id}` for mutations. Session read and force end relay directly, while force end remains authenticated and idempotent through the admin repository helper.

- [ ] **Step 4: Add the management view and modals**

Add a sidebar entry and three tabs: current game, incident cards, and game rules. Settings modal edits enabled/signup/turn values and nine min/max rows. Incident modal edits name, description, one keyword per line, and enabled state. Current-game card renders public fields and a force-end button only when a state exists.

- [ ] **Step 5: Add JavaScript loading, rendering, and saves**

Follow existing `api`, `versionHeaders`, `showNotification`, pagination, and modal patterns. Parse keyword lines with `split("\n").map(value => value.trim()).filter(Boolean)`. Never render hidden deadline or total-duration fields. Refresh settings/cards/session after successful mutations.

- [ ] **Step 6: Run admin tests and verify GREEN**

Run the Step 2 command, then:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q tests/admin
```

- [ ] **Step 7: Commit the admin UI**

```bash
git add src/dzmm_bot/admin/app.py src/dzmm_bot/admin/templates/index.html \
  src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css \
  tests/admin/test_app.py
git commit -m "feat: add blame bomb admin console"
```

### Task 9: Verify concurrency, migration, and the complete product

**Files:**
- Modify only if a failing requirement test exposes a defect in files already listed.
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_commands.py`
- Test: `tests/core/test_app.py`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Consumes the complete feature from Tasks 1–8.
- Produces local verification evidence and a clean deployment-ready branch.

- [ ] **Step 1: Add final concurrency regressions**

Use two repository instances and `ThreadPoolExecutor` to race two transfers from the same holder and to race a valid pre-deadline transfer against `run_blame_game_jobs`. Assert only one transfer persists, no duplicate balance transaction occurs, and the result follows the locked server-receive timestamp. Keep PostgreSQL-only lock tests behind `migrated_postgres_url`.

- [ ] **Step 2: Run all blame-game tests**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q \
  tests/core/test_repository.py tests/core/test_commands.py \
  tests/core/test_app.py tests/admin/test_app.py -k "blame"
```

Expected: all selected SQLite tests pass; only documented PostgreSQL tests skip without `TEST_DATABASE_URL`.

- [ ] **Step 3: Run migration and diff checks**

```bash
git diff --check
git status --short
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/alembic upgrade head
```

Use a disposable database URL for the Alembic command if the configured URL points at a shared environment. Do not migrate production.

- [ ] **Step 4: Run the complete test suite**

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q
```

Expected: zero failures; optional external-integration skips remain documented.

- [ ] **Step 5: Review scope and commit any final test-only correction**

```bash
git status --short
git log --oneline -12
git diff --name-only 5a5801a..HEAD
```

The changed paths must be limited to the design/rules, migration, core/admin feature files, and targeted tests. If Step 1 required a correction, commit it with:

```bash
git add migrations/versions/20260810_30_blame_bomb_game.py src tests rule.md docs/superpowers
git commit -m "test: cover blame bomb concurrency"
```

- [ ] **Step 6: Stop before deployment**

Report the commit range, full test count, skipped optional tests, and the preserved branch/worktree. Wait for explicit user confirmation before merge, push, or deployment.
