# 记忆考核 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persistent single-player and 1v1 “记忆考核” game with configurable difficulty, recalled answer text, coin settlement, and an operator-friendly admin configuration page.

**Architecture:** The core database owns all game state, answer text, money movements, and deadlines. The command handler creates a memory-answer round and returns a typed outbound directive; the Worker sends it, then claims and recalls it through Aikda before the core accepts answers. The admin app proxies narrowly scoped Core APIs and uses the existing versioned mutation and modal patterns.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, Alembic, PostgreSQL/SQLite test database, Socket.IO Aikda gateway, vanilla JavaScript/CSS, pytest.

## Global Constraints

- All calendar and deadline decisions use `Asia/Shanghai` / Beijing time.
- Only one waiting or active activity game can exist across random events and memory assessment games.
- Answer strings contain no whitespace; answer matching is exact and case-sensitive.
- Aikda recall is `message:recall` with `{chatroomId, messageId}`; only open the answer phase after its ACK succeeds.
- Default single levels are `(1, 5, 1)`, `(2, 7, 2)`, `(3, 9, 3)`, `(4, 11, 4)`, `(5, 13, 5)`.
- Default character set is `A-Z`, `a-z`, `0-9`, `!@#$%&*_-`; defaults must include no whitespace.
- Default multiplayer values are difficulty level `5`, base pool `5`, wrong-answer freeze `1`, maximum wrong answers `10`, answer timeout `10 minutes`.
- Preserve user-created command reply templates when migrations change only defaults.
- Use the existing versioned/idempotent admin mutation helper for configuration writes.

---

### Task 1: Persist settings, game states, participant state, answer rounds, and daily usage

**Files:**
- Create: `migrations/versions/20260806_19_memory_assessment.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/deploy/test_artifacts.py`

**Interfaces:**
- Produces immutable records `MemoryAssessmentSettings`, `MemoryAssessmentLevelRule`, `MemoryAssessmentGame`, `MemoryAssessmentParticipant`, and `MemoryAssessmentRound` in `core.repository`.
- Produces `CoreRepository.get_memory_assessment_settings()`, `set_memory_assessment_settings(single_daily_limit, single_recall_seconds, duel_recall_seconds, duel_difficulty_level, duel_base_pool, duel_wrong_freeze, duel_wrong_limit, duel_answer_timeout_minutes, character_set, levels)`, and `list_memory_assessment_levels()`.
- Subsequent tasks consume a game with `mode` (`single` or `duel`), game state, stored answer, stored per-round display deadline, and participant error/frozen amounts.

- [ ] **Step 1: Write failing schema and settings tests**

```python
def test_memory_assessment_defaults_are_seeded(repository):
    settings = repository.get_memory_assessment_settings()
    assert settings.single_daily_limit == 1
    assert settings.duel_base_pool == 5
    assert [(rule.level, rule.answer_length, rule.reward)
            for rule in repository.list_memory_assessment_levels()] == [
        (1, 5, 1), (2, 7, 2), (3, 9, 3), (4, 11, 4), (5, 13, 5)
    ]

def test_memory_assessment_rejects_whitespace_character_set(repository):
    with pytest.raises(ValueError, match="字符集不能包含空白字符"):
        repository.set_memory_assessment_settings(
            single_daily_limit=1, single_recall_seconds=3, duel_recall_seconds=3,
            duel_difficulty_level=5, duel_base_pool=5, duel_wrong_freeze=1,
            duel_wrong_limit=10, duel_answer_timeout_minutes=10,
            character_set="Ab 1",
            levels=[MemoryAssessmentLevelRule(1, 5, 1), MemoryAssessmentLevelRule(2, 7, 2),
                    MemoryAssessmentLevelRule(3, 9, 3), MemoryAssessmentLevelRule(4, 11, 4),
                    MemoryAssessmentLevelRule(5, 13, 5)],
        )
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `.venv/bin/pytest tests/core/test_repository.py -k memory_assessment -q`

Expected: FAIL because settings accessors and records do not exist.

- [ ] **Step 3: Add the Alembic migration and SQLAlchemy records**

Create the following tables and indexes:

```python
memory_assessment_settings(
    id, enabled, single_daily_limit, single_recall_seconds,
    duel_recall_seconds, duel_difficulty_level, duel_base_pool,
    duel_wrong_freeze, duel_wrong_limit, duel_answer_timeout_minutes,
    character_set
)
memory_assessment_level_rules(level PK, answer_length, reward)
memory_assessment_daily_plays(id, user_id FK, play_date, count,
                              UNIQUE(user_id, play_date))
memory_assessment_games(
    id, mode, state, play_date, level, reward, base_pool,
    answer_deadline, winner_user_id FK NULL, created_at, finished_at NULL
)
memory_assessment_participants(
    id, game_id FK, user_id FK, state, wrong_count, frozen_amount,
    UNIQUE(game_id, user_id)
)
memory_assessment_rounds(
    id, game_id FK, sequence, answer, display_seconds, state,
    UNIQUE(game_id, sequence)
)
```

Add an index permitting only one `memory_assessment_games` record in states `waiting_opponent`, `showing_answer`, `awaiting_answer`, or `awaiting_decision`; use PostgreSQL partial-index syntax with a matching SQLite predicate. Seed the singleton settings and five level rows in the migration. Add equivalent SQLAlchemy models and read/write validations: positive counts and seconds, non-empty unique character set with no whitespace, positive level length/reward, and a duel difficulty level that exists in the submitted level set. The outbound-message linkage, platform message ID, recall times, and leasing columns are deliberately deferred to Task 4 so migrations have no circular foreign-key dependency.

- [ ] **Step 4: Implement repository settings reads and writes**

Use the existing `HideAndSeekSettings` pattern. Return sorted levels by `level`, require levels to be consecutive starting at `1`, and replace the complete set atomically inside `set_memory_assessment_settings`.

- [ ] **Step 5: Run focused tests and migration artifact test**

Run: `.venv/bin/pytest tests/core/test_repository.py -k memory_assessment tests/deploy/test_artifacts.py -q`

Expected: PASS, including migration table/default checks.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/20260806_19_memory_assessment.py src/dzmm_bot/core/schema.py src/dzmm_bot/core/repository.py tests/core/test_repository.py tests/deploy/test_artifacts.py
git commit -m "feat: persist memory assessment game state"
```

### Task 2: Implement the single-player state machine and money settlement

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_commands.py`

**Interfaces:**
- Consumes the Task 1 settings and records.
- Produces `start_memory_assessment_single(platform_id, now)`, `answer_memory_assessment(platform_id, text, now)`, `continue_memory_assessment(platform_id, now)`, and `cash_out_memory_assessment(platform_id, now)`.
- Each transition returns `MemoryAssessmentResult(status, display_name, level, answer, reward, balance, round_id)`; the Worker task consumes `round_id` to bind the sent platform message to the answer round.

- [ ] **Step 1: Write failing single-player transition tests**

```python
def test_single_memory_assessment_only_credits_when_player_cashes_out(repository, now):
    repository.create_user("u1", "小明", now, 0)
    game = repository.start_memory_assessment_single("u1", now)
    repository.mark_memory_round_recalled(game.round_id, now)
    assert repository.answer_memory_assessment("u1", game.answer, now).status == "correct"
    result = repository.cash_out_memory_assessment("u1", now)
    assert result.status == "cashed_out"
    assert result.balance == 1

def test_single_memory_assessment_wrong_answer_loses_unclaimed_reward(repository, now):
    game = repository.start_memory_assessment_single("u1", now)
    repository.mark_memory_round_recalled(game.round_id, now)
    assert repository.answer_memory_assessment("u1", "wrong", now).status == "failed"
    assert repository.find_user("u1").balance == 0
```

Also cover daily limit, `/继续` creates a new answer at the next configured length, and the final level auto-credits only its configured reward.

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/core/test_repository.py tests/core/test_commands.py -k 'memory_assessment and single' -q`

Expected: FAIL because the state-transition methods and commands do not exist.

- [ ] **Step 3: Implement exact-answer generation and single transitions**

Generate answers with `secrets.choice(settings.character_set)` and reject generated whitespace defensively. On start, claim the Beijing daily-play slot and create a `showing_answer` round. Do not credit a level at answer time. On correct answer, move the game to `awaiting_decision`; `/继续` creates the next `showing_answer` round; `/收手` records one positive balance transaction using source `memory_assessment_single_reward`. Wrong text marks the game `failed` without a balance transaction. The final correct level calls the same settlement helper once and marks the game `settled`.

- [ ] **Step 4: Add command parsing and editable reply definitions**

Add `/记忆考核`, `/继续`, and `/收手` to `_COMMAND_DEFINITIONS` and the handler. Define reply scenarios for `started`, `answer_recalled`, `correct`, `cash_out`, `completed`, `failed`, `daily_limit`, `already_active`, `blocked`, `not_joined`, and `usage`. Templates include `{昵称}`, `{等级}`, `{奖励}`, `{余额}`, `{展示秒数}` and `{货币}` only where applicable. Do not include `{答案}` in editable templates; answer text is supplied by the typed outbound directive in Task 4.

- [ ] **Step 5: Run focused tests**

Run: `.venv/bin/pytest tests/core/test_repository.py tests/core/test_commands.py -k 'memory_assessment and single' -q`

Expected: PASS for all single-player transitions and command replies.

- [ ] **Step 6: Commit**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py src/dzmm_bot/core/reply_templates.py tests/core/test_repository.py tests/core/test_commands.py
git commit -m "feat: add single memory assessment challenge"
```

### Task 3: Implement 1v1 matchmaking, pool accounting, and activity exclusivity

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/service.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_commands.py`
- Test: `tests/core/test_service.py`

**Interfaces:**
- Consumes Task 1 records and the single-game activity predicate.
- Produces `start_memory_assessment_duel`, `join_memory_assessment_duel`, `surrender_memory_assessment`, and `expire_memory_assessments`.
- Extends `answer_memory_assessment` to choose the first correct participant under row locks and return one outbound reply per affected player/game state.

- [ ] **Step 1: Write failing duel and mutex tests**

```python
def test_first_correct_duel_answer_wins_full_pool(repository, now):
    repository.create_user("a", "甲", now, 20)
    repository.create_user("b", "乙", now, 20)
    repository.start_memory_assessment_duel("a", now)
    round_ = repository.join_memory_assessment_duel("b", now)
    repository.mark_memory_round_recalled(round_.round_id, now)
    result = repository.answer_memory_assessment("b", round_.answer, now)
    assert result.status == "won"
    assert repository.find_user("b").balance == 25  # 20 - 5 + 10

def test_second_active_game_is_rejected(repository, now):
    repository.start_memory_assessment_duel("a", now)
    assert repository.start_memory_assessment_single("b", now).status == "activity_active"
```

Also cover joiner balance deduction, wrong-answer freeze, 10-error ineligibility, surrender, both ineligible collection, ten-minute expiry collection, and a random-event signup blocking memory start.

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/core/test_repository.py tests/core/test_commands.py tests/core/test_service.py -k 'memory_assessment and (duel or active)' -q`

Expected: FAIL because duel methods and global activity checks do not exist.

- [ ] **Step 3: Implement guarded 1v1 transactions**

Lock the current active game and participant rows before any transition. On creation/join, immediately apply negative transactions `memory_assessment_duel_entry`; initialize `base_pool` as the sum of both freezes. On a wrong answer, add one negative `memory_assessment_duel_wrong_freeze` transaction and increment both `frozen_amount` and game pool. The first exact answer in `awaiting_answer` claims the game row, marks `settled`, credits the full pool once with `memory_assessment_duel_win`, and prevents later answers from changing it. Surrender or reaching the wrong-answer limit marks only that participant ineligible; if both are ineligible, mark `expired` and make no compensating transaction. Expiry is evaluated by `run_daily_jobs` and follows the same no-refund rule.

Implement `_active_activity_game(session)` that returns active random-event signup/running records or active memory states. Use it in random-event start, memory start, memory join, and hide-and-seek start only where the existing user-facing behavior already blocks an active random event; do not introduce an unrelated multi-game scheduler.

- [ ] **Step 4: Route `/加入`, `/投降`, and duel commands deterministically**

`/记忆考核 对战` starts the waiting duel. `/加入` without arguments joins only a waiting memory duel; `/加入 角色` retains the existing random-event behavior. `/投降` is handled only for a current memory duel. When any other activity is waiting or active, return a message that includes its display name and state.

- [ ] **Step 5: Run focused tests**

Run: `.venv/bin/pytest tests/core/test_repository.py tests/core/test_commands.py tests/core/test_service.py -k memory_assessment -q`

Expected: PASS, including idempotent first-answer and mutex cases.

- [ ] **Step 6: Commit**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py src/dzmm_bot/core/service.py tests/core/test_repository.py tests/core/test_commands.py tests/core/test_service.py
git commit -m "feat: add memory assessment duel settlement"
```

### Task 4: Persist outbound answer delivery and recall acknowledgment

**Files:**
- Modify: `src/dzmm_bot/core/schema.py`
- Create: `migrations/versions/20260806_20_memory_assessment_recall.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/core/service.py`
- Modify: `src/dzmm_bot/browser/core_client.py`
- Modify: `src/dzmm_bot/browser/worker.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_app.py`
- Test: `tests/browser/test_core_client.py`
- Test: `tests/browser/test_worker.py`

**Interfaces:**
- Adds nullable `memory_round_id` to `outbound_messages` and a typed `OutboundDirective(text, memory_round_id=None)` returned by command handling.
- Adds Core endpoints `POST /internal/memory-assessments/recalls/claim` and `POST /internal/memory-assessments/recalls/{round_id}/confirmed`.
- Extends `OutboundClaim` with optional `memory_round_id`; Worker claims due recall work independently from normal outbound sends.

- [ ] **Step 1: Write failing Worker/core contract tests**

```python
def test_worker_recalls_memory_answer_then_confirms_core(fake_core, gateway, now):
    fake_core.recall_claim = MemoryRecallClaim(round_id=ROUND_ID, platform_message_id="p1")
    worker.run_once()
    assert gateway.retracted == ["p1"]
    assert fake_core.confirmed_recalls == [ROUND_ID]

def test_core_only_opens_answer_phase_after_recall_confirmation(repository, now):
    repository.create_user("u1", "小明", now, 0)
    started = repository.start_memory_assessment_single("u1", now)
    round_ = repository.get_memory_assessment_round(started.round_id)
    repository.record_memory_round_sent(round_.id, "platform-1", now)
    assert repository.answer_memory_assessment("u1", round_.answer, now).status == "answer_not_ready"
    repository.confirm_memory_round_recalled(round_.id, now)
    assert repository.answer_memory_assessment("u1", round_.answer, now).status == "correct"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/core/test_repository.py tests/core/test_app.py tests/browser/test_core_client.py tests/browser/test_worker.py -k 'memory and recall' -q`

Expected: FAIL because no typed directive, recall claim, or confirmation endpoint exists.

- [ ] **Step 3: Add persistent send/recall handoff**

Add nullable `memory_round_id` to `outbound_messages`, then add nullable `outbound_message_id`, `platform_message_id`, `sent_at`, `recall_due_at`, `recalled_at`, `lease_token`, and `lease_expires_at` to `memory_assessment_rounds`. Update `enqueue_outbound`, claim/response models, and `confirm_sent`. For memory rounds, `confirm_sent` records the returned Aikda platform message ID and `recall_due_at = sent_at + display_seconds`, while the game remains `showing_answer`.

Add repository claim logic that leases one due, unsatisfied round with `FOR UPDATE SKIP LOCKED`; confirming `message:recall` ACK sets `recalled_at`, state `awaiting_answer`, and duel `answer_deadline = recalled_at + timeout`. A failed recall leaves the lease to expire and prevents all answers; after the normal retry ceiling, cancel the unshown round and return the daily slot or both duel entry freezes with explicit compensating balance transactions. Expose only the claim/confirm operations needed by the Worker.

- [ ] **Step 4: Implement Worker recall execution without blocking message intake**

After normal outbound processing, claim at most one due memory recall each `run_once`. Call `gateway.retract(platform_message_id)` and only then call the confirmation endpoint. Do not `sleep` for the display duration; the due time is persisted and is checked every Worker loop. Preserve the existing send failure behavior and never submit a player answer before the Core confirmation endpoint changes the round state.

- [ ] **Step 5: Run focused integration tests**

Run: `.venv/bin/pytest tests/core/test_repository.py tests/core/test_app.py tests/browser/test_core_client.py tests/browser/test_worker.py -k 'memory and recall' -q`

Expected: PASS, proving both successful recall gating and recovery from a failed/expired claim.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/20260806_20_memory_assessment_recall.py src/dzmm_bot/core/schema.py src/dzmm_bot/core/repository.py src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/core/service.py src/dzmm_bot/browser/core_client.py src/dzmm_bot/browser/worker.py tests/core/test_repository.py tests/core/test_app.py tests/browser/test_core_client.py tests/browser/test_worker.py
git commit -m "feat: recall memory assessment answers"
```

### Task 5: Expose settings and active-status APIs through Core and Admin

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Test: `tests/core/test_app.py`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Produces `GET/PATCH /internal/game/memory-assessment/settings` and `GET /internal/game/memory-assessment/status`.
- Produces corresponding authenticated admin routes at `/api/game/memory-assessment/settings` and `/api/game/memory-assessment/status`.
- Admin response includes levels, all settings, and either `active: null` or `{mode, state, participants, pool, expires_at}`.

- [ ] **Step 1: Write failing API tests**

```python
def test_memory_assessment_settings_are_versioned_for_admin(client, auth_headers):
    response = client.patch(
        "/api/game/memory-assessment/settings",
        headers={**auth_headers, "If-Match": "0", "Idempotency-Key": "memory-settings-1"},
        json={
            "single_daily_limit": 1, "single_recall_seconds": 3,
            "duel_recall_seconds": 3, "duel_difficulty_level": 5,
            "duel_base_pool": 5, "duel_wrong_freeze": 1,
            "duel_wrong_limit": 10, "duel_answer_timeout_minutes": 10,
            "character_set": "Ab1!", "levels": [
                {"level": 1, "answer_length": 5, "reward": 1},
                {"level": 2, "answer_length": 7, "reward": 2},
                {"level": 3, "answer_length": 9, "reward": 3},
                {"level": 4, "answer_length": 11, "reward": 4},
                {"level": 5, "answer_length": 13, "reward": 5},
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["levels"][4] == {"level": 5, "answer_length": 13, "reward": 5}
```

Also assert invalid whitespace/invalid difficulty produce 422 and status exposes no answer text.

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/core/test_app.py tests/admin/test_app.py -k memory_assessment -q`

Expected: FAIL because the routes and model types do not exist.

- [ ] **Step 3: Add request/response models and proxy methods**

Define Pydantic models that precisely mirror Task 1 settings/levels and cap numerical values consistently with other game APIs. Implement Core route validation via repository calls. Add protocol/client methods and the admin relay routes; use `versioned_configuration_response` with scope `memory-assessment-settings`. The status route is read-only and must omit answer strings and platform message IDs.

- [ ] **Step 4: Run API tests**

Run: `.venv/bin/pytest tests/core/test_app.py tests/admin/test_app.py -k memory_assessment -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py tests/core/test_app.py tests/admin/test_app.py
git commit -m "feat: expose memory assessment settings"
```

### Task 6: Add the admin “记忆考核” configuration UI and complete verification

**Files:**
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Test: `tests/admin/test_assets.py`
- Test: `tests/admin/test_app.py`
- Test: `tests/deploy/test_artifacts.py`

**Interfaces:**
- Consumes Task 5 settings/status JSON.
- Produces a navigation view named `memory-assessment`, a read-only active-game status card, and a modal for settings/level edits.

- [ ] **Step 1: Write failing asset and route-render tests**

```python
def test_admin_assets_include_memory_assessment_view():
    html = (ROOT / "src/dzmm_bot/admin/templates/index.html").read_text()
    script = (ROOT / "src/dzmm_bot/admin/static/admin.js").read_text()
    assert 'data-view="memory-assessment"' in html
    assert "loadMemoryAssessment" in script
    assert "/api/game/memory-assessment/settings" in script
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/admin/test_assets.py tests/admin/test_app.py tests/deploy/test_artifacts.py -k memory_assessment -q`

Expected: FAIL because the navigation and modal code do not exist.

- [ ] **Step 3: Implement a modal-first operator UI**

Add one sidebar item “记忆考核”. The main view shows concise single-player defaults, duel defaults, and an active-game status card. “编辑规则” opens one modal with fields for daily limit, both recall seconds, character set, five-or-more editable level rows, duel difficulty select, base pool, wrong freeze, wrong limit, and timeout. Use the existing `runMutation`/`requestGame` flow so the save button disables while pending, uses an idempotency key and `If-Match`, refreshes state after success, and shows one standard success/error toast only for the user action. Do not poll success toasts.

- [ ] **Step 4: Run admin and full regression suites**

Run: `.venv/bin/pytest tests/admin/test_assets.py tests/admin/test_app.py tests/deploy/test_artifacts.py -q`

Expected: PASS.

Run: `.venv/bin/pytest -q`

Expected: full suite PASS.

- [ ] **Step 5: Perform a production-like manual verification**

1. Start a single challenge and verify its answer message disappears only after the configured display time.
2. Verify a pre-recall answer is ignored and a post-recall exact answer advances the level.
3. Verify `/收手` credits exactly one configured reward.
4. Start a duel, join with `/加入`, submit one wrong answer, then have the other player win; verify both entry and wrong-answer frozen amounts form the winner payout.
5. Verify `/投降`, simultaneous correct submissions, timeout, daily limit, and random-event conflict leave exactly one terminal game record and no duplicate balance transaction.

- [ ] **Step 6: Commit**

```bash
git add src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/admin/test_assets.py tests/admin/test_app.py tests/deploy/test_artifacts.py
git commit -m "feat: add memory assessment admin controls"
```
