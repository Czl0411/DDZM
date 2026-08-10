# Blame Bomb Settlement Notice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every winning/losing end state of the blame bomb game send one complete group settlement notice with the cause, loser deduction, ordered winners, per-winner reward, and currency.

**Architecture:** Keep the existing settlement state machine and ledger untouched. Derive display values from `BlameGameResult`, route both scheduled and command-triggered endings through the existing editable reply scenarios, and add one Alembic migration that upgrades only templates still equal to the old built-in defaults.

**Tech Stack:** Python 3.12+, SQLAlchemy 2, Alembic, pytest.

## Global Constraints

- Send one public group message per terminal event; do not add a second settlement message.
- Show net economy only: loser `N-1`, each winner `1`; do not expose held-guarantee internals.
- Winner names follow the frozen player seat order and use `、` as the separator.
- Cover global explosion, turn timeout, active `/退出甩锅`, and a player command that discovers an already-due game.
- Do not change balance mutations, settlement idempotency, game timing, or cancellation behavior.
- Preserve administrator-customized templates during migration.
- Do not deploy without a separate explicit deployment instruction.

---

### Task 1: Render complete settlement results on every winning/losing path

**Files:**
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_group_commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/commands.py`

**Interfaces:**
- Consumes: `BlameGameResult.player_count`, `loser_display_name`, `winner_display_names`, and `settlement_reason`.
- Produces: `blame_settlement_template_values(result: BlameGameResult) -> dict[str, object]` and complete values for the existing `exploded`, `turn_timeout`, and active-leave `settled` reply scenarios.

- [ ] **Step 1: Write failing automatic-settlement tests**

Add repository tests that start a four-player game with literal display names, force an explosion and a turn timeout separately, run `run_blame_game_jobs`, claim the real outbound record, and assert literal messages:

```python
assert outbound.text == (
    "【甩锅游戏】操作超时，甲 背锅，扣除 3 摸鱼币；"
    "乙、丙、丁 获胜，每人获得 1 摸鱼币。"
)
```

The explosion case must assert the same economic fields with the `锅爆炸了` cause. Derive the expected loser and ordered winner literals from the controlled fixture setup, not from the production formatter.

- [ ] **Step 2: Run the automatic-settlement tests and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/core/test_repository.py -k "blame and complete_settlement_notice"
```

Expected: both tests fail because the current automatic messages contain only the loser.

- [ ] **Step 3: Write failing command-settlement tests**

Add group-command tests for active `/退出甩锅` and for a `/甩锅` request received after the turn deadline. Assert that each real queued reply contains the correct reason, `扣除 2 摸鱼币`, the two ordered winners, and `每人获得 1 摸鱼币`.

- [ ] **Step 4: Run the command-settlement tests and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/core/test_group_commands.py -k "blame and complete_settlement_notice"
```

Expected: active leave omits all economy details and the due transfer uses the generic incomplete settled template.

- [ ] **Step 5: Implement the minimal shared settlement values and routing**

In `src/dzmm_bot/core/repository.py`, add:

```python
def blame_settlement_template_values(result: BlameGameResult) -> dict[str, object]:
    return {
        "{失败者}": result.loser_display_name,
        "{扣除金额}": max(result.player_count - 1, 0),
        "{获胜者}": "、".join(result.winner_display_names),
        "{奖励}": 1,
    }
```

Use it when `_resolve_due_blame_game(..., notify=True)` renders automatic explosion or timeout messages. Add `{货币}` to `_blame_automatic_message` from `get_game_settings().currency_name`.

In `src/dzmm_bot/core/commands.py`, add one `_blame_settlement_reply` method. Select `/甩锅游戏` plus `exploded` or `turn_timeout` for deadline results, `/退出甩锅` plus `settled` for `player_left`, and retain `/甩锅` plus `settled` only as the fallback. Replace the three duplicated incomplete result branches in `_blame_transfer`, `_blame_leave`, and `_blame_end` with this method.

Update the three default templates and allowed variables in `src/dzmm_bot/core/reply_templates.py` to exactly match the approved design.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```bash
.venv/bin/pytest -q tests/core/test_repository.py -k "blame"
.venv/bin/pytest -q tests/core/test_group_commands.py -k "blame"
```

Expected: all blame-game behavior tests pass, including existing balance and idempotency coverage.

- [ ] **Step 7: Commit the complete notification behavior**

```bash
git add src/dzmm_bot/core/reply_templates.py src/dzmm_bot/core/repository.py \
  src/dzmm_bot/core/commands.py tests/core/test_repository.py \
  tests/core/test_group_commands.py
git commit -m "fix: announce complete blame settlements"
```

### Task 2: Upgrade unchanged production templates without overwriting custom copy

**Files:**
- Create: `migrations/versions/20260810_33_blame_settlement_notices.py`
- Create: `tests/deploy/test_blame_settlement_migration.py`

**Interfaces:**
- Consumes: revision `20260810_32` and table `command_reply_templates(command, scenario, template)`.
- Produces: revision `20260810_33` and `apply_template_updates(connection, updates)` for upgrade/downgrade behavior.

- [ ] **Step 1: Write a failing real-SQL migration behavior test**

Load the migration file with `importlib.util`, create a real in-memory SQLite `command_reply_templates` table, and insert one row equal to each old built-in default plus one customized row. Call `apply_template_updates(connection, TEMPLATE_UPDATES)` and assert old defaults become the approved complete messages while the customized row remains byte-for-byte unchanged.

- [ ] **Step 2: Run the migration test and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/deploy/test_blame_settlement_migration.py
```

Expected: fail because revision `20260810_33` and its update function do not exist.

- [ ] **Step 3: Implement the migration**

Create revision `20260810_33` with `down_revision = "20260810_32"`. Define literal old/new tuples for `/甩锅游戏:exploded`, `/甩锅游戏:turn_timeout`, `/甩锅:settled`, and `/退出甩锅:settled`. `upgrade()` calls `apply_template_updates(op.get_bind(), TEMPLATE_UPDATES)`; each update filters by command, scenario, and exact old template. `downgrade()` applies the reversed tuples and likewise changes only exact new defaults.

- [ ] **Step 4: Run migration and focused gameplay tests**

Run:

```bash
.venv/bin/pytest -q tests/deploy/test_blame_settlement_migration.py
.venv/bin/pytest -q tests/core/test_repository.py tests/core/test_group_commands.py -k "blame"
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit the migration**

```bash
git add migrations/versions/20260810_33_blame_settlement_notices.py \
  tests/deploy/test_blame_settlement_migration.py
git commit -m "fix: migrate blame settlement templates"
```

### Task 3: Verify the complete local release candidate

**Files:**
- Verify only; do not modify unrelated files.

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces: a locally verified commit ready for a separate deployment instruction.

- [ ] **Step 1: Run formatting and complete regression checks**

```bash
git diff --check
.venv/bin/pytest -q
```

Expected: no whitespace errors; all runnable tests pass, with PostgreSQL-only tests skipped only when `TEST_DATABASE_URL` is unset.

- [ ] **Step 2: Confirm the worktree contains no unrelated edits**

```bash
git status --short
git log -3 --oneline
```

Expected: only the known user-owned untracked files remain outside the isolated worktree, and the new commits contain only settlement-notice work.
