# Random Event Game Conflict Skip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure scheduled random events skip instead of interrupting any active game, while manual triggers reject active-game conflicts without changing the schedule.

**Architecture:** Add one repository predicate for active non-random games and one shared transaction gate backed by the existing `random_event_settings` singleton row. Scheduled and manual event triggers acquire the gate before checking activity; game creation paths acquire the same gate before checking for an active random event, making the winner deterministic under concurrency.

**Tech Stack:** Python 3.12+, SQLAlchemy 2, PostgreSQL/SQLite, pytest, FastAPI.

## Global Constraints

- Do not add a random-event queue, deferred-trigger state, new-game blocking prompt, table, or migration.
- A due scheduled event becomes `skipped` when any active game exists and is never replayed.
- A manual trigger returns `当前有游戏进行中` and leaves the schedule `pending` when any active game exists.
- Existing-game join, answer, selection, vote, exit, timeout, and settlement paths remain unchanged.
- Do not deploy after implementation; report local verification and wait for explicit user confirmation.

---

### Task 1: Detect every active game and skip due events

**Files:**
- Modify: `src/dzmm_bot/core/repository.py:2226-2235,3991-4047`
- Modify: `tests/core/test_repository.py:650-675,1098-1115`
- Modify: `rule.md:81-88`

**Interfaces:**
- Produces: `CoreRepository._has_active_game(session: Session) -> bool`
- Consumes: existing `MemoryAssessmentGameRecord.active_key`, `HideAndSeekGameRecord.state`, and `UndercoverSessionRecord.active_key` state contracts.

- [ ] **Step 1: Replace the old wait expectations with failing skip tests**

Add or update repository tests so each active game type produces `skipped`, for example:

```python
def test_due_random_event_is_skipped_while_memory_assessment_single_is_active(repository):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)
    assert repository.start_memory_assessment_single("u1", now).status == "started"
    repository.create_random_event_scene("茶水间", "报名", ["开场"], 1, 1, [("员工", 1)])
    repository.set_random_event_settings(["10:00"], "可选身份：{可选身份}", 15, 5)
    repository.schedule_random_events(now)

    repository.run_random_event_jobs(now)

    assert repository.list_today_random_event_schedules(now)[0].status == "skipped"
    assert repository.active_random_event_state() is None
```

Cover active single memory, duel memory, one `selecting` hide-and-seek game, and undercover signup. Rename the existing “waits while” tests to state the new skip behavior. Assert the active game remains active after the job.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/core/test_repository.py -k "due_random_event and (memory_assessment or hide_and_seek or undercover)"
```

Expected: the existing duel/undercover cases remain `pending`, and the new single/hide-and-seek cases start a random event instead of becoming `skipped`.

- [ ] **Step 3: Implement the unified active-game predicate**

Add one private method near the existing activity helpers:

```python
def _has_active_game(self, session: Session) -> bool:
    return any(
        (
            session.scalar(
                select(exists().where(MemoryAssessmentGameRecord.active_key == "global"))
            ),
            session.scalar(
                select(exists().where(HideAndSeekGameRecord.state == "selecting"))
            ),
            session.scalar(
                select(exists().where(UndercoverSessionRecord.active_key == _UNDERCOVER_ACTIVE_KEY))
            ),
        )
    )
```

In `run_random_event_jobs`, replace the special-case undercover/duel `continue` branch with:

```python
if self._has_active_game(session):
    schedule.status = "skipped"
    continue
```

Do not alter active random-event handling: an already active random event continues to make later due schedules `skipped`.

- [ ] **Step 4: Update the user-facing rules**

Add exact rules stating that any due random event is skipped when single/duel memory, selecting hide-and-seek, or undercover is active; the event does not interrupt or replay after the game.

- [ ] **Step 5: Run focused repository tests and verify GREEN**

Run:

```bash
.venv/bin/pytest -q tests/core/test_repository.py -k "random_event and (skipped or memory_assessment or hide_and_seek or undercover)"
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py rule.md
git commit -m "fix: skip random events during active games"
```

### Task 2: Reject manual triggers and serialize creation

**Files:**
- Modify: `src/dzmm_bot/core/repository.py:1725-1755,2575-2645,2695-2755,3420-3490,3777-3800,3991-4047`
- Modify: `tests/core/test_repository.py:1428-1445,2168-2440`
- Test: `tests/core/test_app.py:1125-1168`

**Interfaces:**
- Consumes: `CoreRepository._has_active_game(session: Session) -> bool` from Task 1.
- Produces: `CoreRepository._lock_gameplay_gate(session: Session) -> None`.
- Preserves: `CoreRepository.trigger_random_event(schedule_id: UUID, now: datetime) -> RandomEventSchedule`.

- [ ] **Step 1: Write failing manual-trigger tests**

Add repository tests for single memory, duel memory, selecting hide-and-seek, and undercover. Each test must assert both the exact error and unchanged schedule state:

```python
with pytest.raises(ValueError, match="当前有游戏进行中"):
    repository.trigger_random_event(schedule.id, now)

assert repository.list_today_random_event_schedules(now)[0].status == "pending"
assert repository.active_random_event_state() is None
```

Add one FastAPI test that posts to `/internal/game/random-events/today/{schedule_id}/trigger` while a game is active and asserts HTTP `422` with `当前有游戏进行中` in the response body. Reuse the real repository-backed client fixture rather than mocking the repository.

- [ ] **Step 2: Run manual-trigger tests and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/core/test_repository.py -k "manual_random_event and active_game" tests/core/test_app.py -k "trigger_random_event and active_game"
```

Expected: manual trigger starts the event or returns the old multiplayer-only error instead of the new exact error.

- [ ] **Step 3: Implement the shared transaction gate**

Add a helper that ensures and locks the existing random-event settings singleton:

```python
def _lock_gameplay_gate(self, session: Session) -> None:
    self.get_random_event_settings()
    if session.get(RandomEventSettingsRecord, 1, with_for_update=True) is None:
        raise RuntimeError("随机事件设置消失")
```

Call it as the first database lock inside these creation/trigger transactions:

- `start_undercover_signup`
- `start_memory_assessment_single`
- `start_memory_assessment_duel`
- `start_hide_and_seek`
- `trigger_random_event`
- `run_random_event_jobs`

Move each method's settings lookup or schedule-generation call below the gate acquisition when it currently runs earlier in the transaction. This keeps lock ordering consistent: gameplay gate first, then settings, user, schedule, or active-game rows.

Do not call it from join, answer, choose, vote, leave, timeout, or settlement methods.

After the active-random-event check in `trigger_random_event`, add:

```python
if self._has_active_game(session):
    raise ValueError("当前有游戏进行中")
```

- [ ] **Step 4: Run manual-trigger and game-creation regression tests**

Run:

```bash
.venv/bin/pytest -q \
  tests/core/test_repository.py -k "random_event or memory_assessment or hide_and_seek or undercover" \
  tests/core/test_app.py -k "random_event"
```

Expected: all selected tests pass; existing-game continuation tests remain unchanged.

- [ ] **Step 5: Add a PostgreSQL concurrency regression test**

Using `migrated_postgres_url`, create two repository instances sharing the migrated schema. Use `Barrier(2)` and `ThreadPoolExecutor(max_workers=2)` to race a game creation against `run_random_event_jobs(now)`. Assert exactly one outcome:

```python
assert (schedule_status, game_status) in {
    ("skipped", "started"),
    ("signup", "random_event_active"),
}
```

Also assert there is never both an active random event and an active newly created game. The test may skip when `TEST_DATABASE_URL` is not configured, matching existing PostgreSQL-only tests.

- [ ] **Step 6: Run the PostgreSQL test when available**

Run:

```bash
.venv/bin/pytest -q tests/core/test_repository.py -k "postgres and random_event_game_creation"
```

Expected with `TEST_DATABASE_URL`: PASS. Expected without it: one documented skip.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py tests/core/test_app.py
git commit -m "fix: serialize games with random event triggers"
```

### Task 3: Full verification and deployment handoff

**Files:**
- Verify only; do not modify production configuration or deployment files.

**Interfaces:**
- Consumes the completed repository, API, rules, and tests from Tasks 1-2.
- Produces local verification evidence and a deployment-ready commit range.

- [ ] **Step 1: Run formatting and diff checks**

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intentional tracked changes and pre-existing untracked local files are present.

- [ ] **Step 2: Run the complete test suite**

```bash
.venv/bin/pytest -q
```

Expected: all tests pass; only the established optional PostgreSQL/integration skips remain.

- [ ] **Step 3: Review final history and scope**

```bash
git log --oneline -5
git show --stat --oneline HEAD~2..HEAD
```

Expected: implementation commits touch only the repository, targeted tests, and `rule.md`; no environment files or unrelated handoff documents are committed.

- [ ] **Step 4: Stop before deployment**

Report the root cause, implemented behavior, exact test counts, and commit IDs to the user. Do not run the deploy script or mutate the production database until the user explicitly confirms deployment.
