# 蹦蹦数字炸弹随机倍率 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed `×0.8` number-bomb calculation with one hidden, persisted, equally random multiplier per round from `×0.8` through `×1.2`, revealed only at settlement.

**Architecture:** Store the selected multiplier as an integer tenth on each round, calculate all targets and deviations with integer ratios, and inject a random source into the repository for deterministic tests. A newly started round samples once; an invalid retry copies the prior attempt's multiplier. An Alembic migration backfills historical rounds to `8` and updates the authoritative AI knowledge card without overwriting administrator-customized content.

**Tech Stack:** Python 3.13, SQLAlchemy 2, Alembic, PostgreSQL/SQLite tests, pytest.

## Global Constraints

- The allowed multiplier tenths are exactly `8, 9, 10, 11, 12`, with equal probability through `choice`.
- Each new round samples once; service or Worker restarts must not change the stored value.
- Reporting prompts, reminders, active-game summaries, and administrator live state must not reveal the multiplier before settlement.
- Valid and invalid settlements reveal the multiplier and show `F = average × multiplier`.
- An invalid retry keeps the same multiplier; `/继续` starts a new round and samples again.
- Historical rounds are backfilled to `8`, preserving the former `×0.8` rule.
- The multiplier set and weights are not administrator-configurable.
- Do not alter reporting range, punishment cadence, joining, leaving, skipping, or timeout behavior.
- Build on the complete personal-profile branch so migration `20260812_40` follows `20260812_39`; do not mutate the preserved `codex/personal-profile` branch.
- Preserve `.env`, `.DS_Store`, and `docs/BOT_MESSAGE_TRANSPORT_HANDOFF.md`; do not deploy in this plan.

---

### Task 1: Exact multiplier-aware calculation and rendering

**Files:**
- Modify: `src/dzmm_bot/core/number_bomb.py`
- Test: `tests/core/test_number_bomb.py`

**Interfaces:**
- Produces: `NUMBER_BOMB_MULTIPLIER_TENTHS: tuple[int, ...] = (8, 9, 10, 11, 12)`.
- Produces: `calculate_number_bomb(entries, multiplier_tenths) -> NumberBombCalculation`.
- Produces: `NumberBombCalculation.multiplier_tenths: int`.
- Consumes: `render_number_bomb_result(round_number, punishment_type, calculation)` and reveals the multiplier only because rendering happens at settlement.

- [ ] **Step 1: Write failing calculation and rendering tests**

Add parameterized coverage that calls `calculate_number_bomb(entries(10, 50, 90), multiplier)` for every allowed value and asserts:

```python
assert calculation.target_numerator == multiplier * 150
assert calculation.target_denominator == 10 * 3
assert calculation.multiplier_tenths == multiplier
```

Add rejection cases for `7`, `13`, `8.0`, and `True`. Update rendering assertions to require:

```python
assert "本轮随机倍率：×1.1" in rendered
assert "最终数 F：平均值 × 1.1 = 55.00" in rendered
```

Cover `×1.0` formatting and verify invalid settlements also reveal their stored multiplier.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_number_bomb.py -q`

Expected: FAIL because the calculator has no multiplier parameter or multiplier result field.

- [ ] **Step 3: Implement exact integer calculation and settlement copy**

Validate membership in `NUMBER_BOMB_MULTIPLIER_TENTHS`, compute `target_numerator = multiplier_tenths * total`, `target_denominator = 10 * player_count`, and retain the current exact deviation-band logic. Add a helper that formats an integer tenth with one decimal place and render both the random multiplier line and formula line.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_number_bomb.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the calculation slice**

```bash
git add src/dzmm_bot/core/number_bomb.py tests/core/test_number_bomb.py
git commit -m "feat: calculate number bomb with round multiplier"
```

### Task 2: Persist the round multiplier and migrate historical data

**Files:**
- Create: `migrations/versions/20260812_40_number_bomb_random_multiplier.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `tests/deploy/test_personal_profile_migration.py`
- Test: `tests/deploy/test_number_bomb_random_multiplier_migration.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Consumes: Alembic revision `20260812_39` from the personal-profile feature.
- Produces: `NumberBombRoundRecord.multiplier_tenths: int`, non-null with default `8` and a check constraint for `8..12`.
- Produces: Alembic revision `20260812_40`.

- [ ] **Step 1: Write failing schema and migration tests**

Assert the ORM column and check constraint exist. In a temporary database stamped at `20260812_39`, create a historical round, upgrade to `20260812_40`, and assert:

```python
assert migrated_multiplier == 8
assert alembic_head == "20260812_40"
assert "每轮结算时公布随机倍率" in migrated_knowledge_content
```

Then downgrade to `20260812_39` and assert the column is removed. Change the existing personal-profile migration test to upgrade explicitly to `20260812_39` so it remains isolated from later revisions.

- [ ] **Step 2: Run migration and schema tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/deploy/test_number_bomb_random_multiplier_migration.py tests/core/test_repository.py -k 'random_multiplier or number_bomb_schema' -q`

Expected: FAIL because revision `40` and the ORM column do not exist.

- [ ] **Step 3: Implement the schema and migration**

Add `multiplier_tenths` with server default `8`, backfill historical rows, make it non-null, and create `ck_number_bomb_round_multiplier_tenths`. Update the known built-in number-bomb knowledge-card text conditionally: only replace the exact previous built-in text; preserve administrator-customized content. Make downgrade reverse the known new content conditionally and remove the constraint and column using batch mode where SQLite requires it.

- [ ] **Step 4: Run migration and schema tests and verify GREEN**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/deploy/test_number_bomb_random_multiplier_migration.py tests/deploy/test_personal_profile_migration.py tests/core/test_repository.py -k 'random_multiplier or personal_profile_migration or number_bomb_schema' -q`

Expected: PASS.

- [ ] **Step 5: Commit the persistence slice**

```bash
git add migrations/versions/20260812_40_number_bomb_random_multiplier.py src/dzmm_bot/core/schema.py tests/deploy/test_personal_profile_migration.py tests/deploy/test_number_bomb_random_multiplier_migration.py tests/core/test_repository.py
git commit -m "feat: persist number bomb round multiplier"
```

### Task 3: Sample once per new round and retain invalid retries

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Consumes: existing `RandomSource.choice(values)` protocol and `NUMBER_BOMB_MULTIPLIER_TENTHS`.
- Produces: `CoreRepository(..., number_bomb_random: RandomSource | None = None)`.
- Produces: `_start_number_bomb_round(..., multiplier_tenths: int | None = None)` where `None` samples and an explicit value is persisted unchanged.

- [ ] **Step 1: Write failing repository lifecycle tests**

Create a deterministic random source whose `choice` returns `11` then `9` and records calls. Assert:

```python
first_round.multiplier_tenths == 11
assert rng.choice_calls == 1
```

Settle an invalid attempt and assert attempt 2 still stores `11` with no new random call. Settle it validly, send `/继续`, and assert round 2 stores `9` with exactly two total calls. Recreate `CoreRepository` over the same session factory between operations and prove the collecting round remains `11`.

- [ ] **Step 2: Run lifecycle tests and verify RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_repository.py -k 'number_bomb_random_multiplier' -q`

Expected: FAIL because repository construction and round rows do not support multiplier selection.

- [ ] **Step 3: Implement sampling and retry inheritance**

Store `number_bomb_random or SystemRandom()` in the repository. In `_start_number_bomb_round`, sample from the constant only when no multiplier is supplied. Pass the round's stored multiplier to `calculate_number_bomb`. When creating an invalid retry, copy `round_record.multiplier_tenths`. Keep multiplier fields out of `NumberBombGameResult` and `NumberBombGameSummary` so pre-settlement surfaces cannot expose them.

- [ ] **Step 4: Update existing exact-settlement expectations and verify GREEN**

Update direct calculator calls in repository tests to pass the round's deterministic multiplier. Assert stored target numerator and denominator use the new integer-tenths representation. Run:

`PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_repository.py -k 'number_bomb' -q`

Expected: PASS.

- [ ] **Step 5: Commit the lifecycle slice**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: randomize each number bomb round"
```

### Task 4: Verify non-disclosure and integrated behavior

**Files:**
- Modify only tests or production files needed to fix regressions introduced by Tasks 1–3.
- Test: `tests/core/test_group_commands.py`
- Test: `tests/core/test_service.py`

**Interfaces:**
- Verifies that existing group and direct-message delivery contracts conceal the multiplier until `public_message` settlement.

- [ ] **Step 1: Add message-boundary regression tests**

Start a round with a deterministic `×1.2` source and inspect all opening group/direct outbounds plus a 15-second reminder. Assert none contains `倍率` or `×1.2`. Complete submissions and assert the settlement group message contains:

```text
本轮随机倍率：×1.2
最终数 F：平均值 × 1.2 = ...
```

- [ ] **Step 2: Run message tests and verify behavior**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_group_commands.py tests/core/test_service.py -k 'number_bomb' -q`

Expected: PASS after the lifecycle implementation; if the new regression test exposes an early leak, make only the smallest production change needed and rerun.

- [ ] **Step 3: Run all number-bomb and migration tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_number_bomb.py tests/core/test_repository.py tests/core/test_group_commands.py tests/core/test_service.py tests/deploy/test_number_bomb_random_multiplier_migration.py -k 'number_bomb or random_multiplier' -q`

Expected: PASS.

- [ ] **Step 4: Commit integrated regressions**

```bash
git add tests/core/test_group_commands.py tests/core/test_service.py src/dzmm_bot/core/repository.py
git commit -m "test: cover hidden number bomb multiplier"
```

### Task 5: Full verification and handoff

**Files:**
- Modify only files required to fix failures introduced by Tasks 1–4.

**Interfaces:**
- Verifies the complete random-multiplier contract and all existing behavior.

- [ ] **Step 1: Run static and migration-head checks**

Run: `git diff --check && PYTHONPATH=src .venv/bin/alembic -c alembic.ini heads`

Expected: no whitespace errors and exactly `20260812_40 (head)`.

- [ ] **Step 2: Run the complete suite**

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q`

Expected: all tests pass with only known deprecation warnings.

- [ ] **Step 3: Inspect final scope and protected files**

Confirm all changed production lines trace to exact multiplier calculation, round persistence, sampling, retry inheritance, settlement rendering, or knowledge guidance. Confirm `.env`, `.DS_Store`, and `docs/BOT_MESSAGE_TRANSPORT_HANDOFF.md` remain untracked and untouched.

- [ ] **Step 4: Report a ready-to-integrate branch without deployment**

Report test counts, commit list, migration head, and the preserved personal-profile parent branch. Deployment remains a separate explicit action.
