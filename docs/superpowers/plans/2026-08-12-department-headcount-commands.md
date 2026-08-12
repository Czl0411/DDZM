# Department Headcount Commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/部门人数` and `/我的部门人数` so any employee can see real-time department totals and non-zero rank counts without member details.

**Architecture:** Add a small read model and two aggregate repository queries over the existing users, departments, and ranks tables. Route both commands through the existing group-command, command-definition, editable-template, and department-help systems; no schema migration or cache is needed.

**Tech Stack:** Python 3.13, SQLAlchemy 2, FastAPI, pytest, existing DZMM command/template infrastructure.

## Global Constraints

- Both commands require an existing employee account.
- `/部门人数` includes every non-empty department, including the default and disabled departments.
- `/我的部门人数` returns only the sender's current department.
- Only non-zero rank counts are shown, ordered by `RankRecord.sort_order` ascending; missing ranks are counted as `未知职位` last.
- Responses contain totals and rank counts only—never names, employee numbers, balances, or member lists.
- Statistics are queried live; no database migration, cache, counter, or scheduled job is added.
- Existing `/部门` and department approval behavior must remain unchanged.

---

### Task 1: Repository headcount read model and aggregation

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `DepartmentRankHeadcount(rank_name: str, count: int, sort_order: int | None)`.
- Produces: `DepartmentHeadcount(department_id: UUID, department_name: str, total_count: int, ranks: tuple[DepartmentRankHeadcount, ...])`.
- Produces: `CoreRepository.list_department_headcounts() -> tuple[DepartmentHeadcount, ...]`.
- Produces: `CoreRepository.get_user_department_headcount(platform_id: str) -> DepartmentHeadcount | None`.

- [ ] **Step 1: Write failing repository tests**

Create real users, departments, and ranks in SQLite. Assign duplicate-name employees across the default, enabled, disabled, and empty departments. Assert literal totals, omitted empty departments, ascending rank order, and `未知职位` for a deliberately null rank. Assert the per-user query returns only that user's department and returns `None` for a missing platform ID.

- [ ] **Step 2: Run repository tests and confirm RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_repository.py -k department_headcount -q`

Expected: FAIL because the read models and repository methods do not exist.

- [ ] **Step 3: Implement the minimal aggregate query**

Add the two frozen dataclasses near `UserProfile`. Query grouped user counts with a department join and rank outer join. Convert rows into immutable department results, omit departments with no rows, order departments using the existing `created_at/name` convention, and order known ranks by `sort_order` with `未知职位` last.

- [ ] **Step 4: Run repository tests and confirm GREEN**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_repository.py -k department_headcount -q`

Expected: PASS.

- [ ] **Step 5: Commit repository behavior**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: aggregate department headcounts"
```

### Task 2: Group commands, templates, definitions, and help

**Files:**
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Test: `tests/core/test_group_commands.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Consumes: repository headcount methods from Task 1.
- Produces: group commands `/部门人数` and `/我的部门人数`.
- Produces template variables: `{部门统计}` and `{日期}` for each `shown` scenario.

- [ ] **Step 1: Write failing command behavior tests**

Assert `/部门人数` renders multiple non-empty department blocks including `未分配部门`, with total and rank counts but no employee names. Assert `/我的部门人数` renders only the sender's department. Assert both commands return the existing enrollment guidance for an unknown sender.

- [ ] **Step 2: Write failing integration tests**

Assert both definitions appear in the command library, `/帮助 部门` includes their exact syntax, an administrator-edited `{部门统计}` template is honored, and disabling `/部门人数` suppresses its reply through the existing command switch.

- [ ] **Step 3: Run command tests and confirm RED**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_group_commands.py tests/core/test_repository.py -k 'department_headcount or department_help' -q`

Expected: FAIL because commands, templates, definitions, and help entries are absent.

- [ ] **Step 4: Implement the minimal command integration**

Add both names to `_COMMANDS`, dispatch them before department mutation commands, format one department block as `部门：共 N 人` plus `职位：N 人` lines, and render the appropriate `shown` or `not_joined` template. Add command definitions, four template definitions, and two entries under `/帮助 部门`.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_group_commands.py tests/core/test_repository.py -k 'department_headcount or department_help' -q`

Expected: PASS.

- [ ] **Step 6: Commit command integration**

```bash
git add src/dzmm_bot/core/commands.py src/dzmm_bot/core/repository.py src/dzmm_bot/core/reply_templates.py tests/core/test_group_commands.py tests/core/test_repository.py
git commit -m "feat: add department headcount commands"
```

### Task 3: API command-library contract and full regression

**Files:**
- Modify: `tests/core/test_app.py`

**Interfaces:**
- Consumes: command definitions and reply templates from Task 2.
- Produces: regression coverage proving the management API exposes both new commands and templates.

- [ ] **Step 1: Update the command-library API expectation**

Add `/部门人数` and `/我的部门人数` to the literal expected command set and assert each command exposes `shown` and `not_joined` templates.

- [ ] **Step 2: Run the API test**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/core/test_app.py -k 'command_library or game_commands' -q`

Expected: PASS with the complete command-library contract.

- [ ] **Step 3: Run formatting and full regression checks**

Run: `git diff --check`

Run: `PYTHONPATH=src .venv/bin/python -m pytest -q`

Expected: all tests pass; existing documented skips remain skips.

- [ ] **Step 4: Commit final regression coverage**

```bash
git add tests/core/test_app.py
git commit -m "test: cover department headcount command library"
```

### Task 4: Integrate without deployment

**Files:**
- No production files beyond Tasks 1–3.

**Interfaces:**
- Produces: a verified feature branch ready to merge into the user's current main branch.

- [ ] **Step 1: Verify branch state**

Run: `git status --short --branch`

Expected: clean feature worktree.

- [ ] **Step 2: Use the finishing workflow**

Invoke `superpowers:finishing-a-development-branch`, merge the verified branch into the current local `main`, rerun the full test suite on integrated main, and preserve unrelated untracked files.

- [ ] **Step 3: Stop before deployment**

Report the merged commit and verification results. Do not push or deploy unless the user explicitly requests deployment.
