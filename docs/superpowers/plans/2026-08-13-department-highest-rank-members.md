# Department Highest Rank Members Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/部门人数` and `/我的部门人数` show each department's highest-ranked employee or employees.

**Architecture:** Extend the existing repository headcount projection with a compact highest-rank member result gathered in the same repository operation. Keep rendering in the command service so both commands share the exact department block format and existing reply templates remain unchanged.

**Tech Stack:** Python 3.12, SQLAlchemy 2, pytest

## Global Constraints

- Highest rank is the greatest non-null `RankRecord.sort_order` in the department.
- All employees tied at the highest rank are shown.
- Employee numbers appear only for duplicate display names among the highest-rank employees in that department.
- `/部门人数` and `/我的部门人数` use the same department block format.
- No database migration, new template variable, permission change, command change, or unrelated refactor.

---

### Task 1: Repository headcount projection

**Files:**
- Modify: `src/dzmm_bot/core/repository.py:880-900,9909-9990`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Consumes: existing `Repository.list_department_headcounts()` and `Repository.get_user_department_headcount()`.
- Produces: `DepartmentHighestRankMember(display_name: str, employee_number: int)` and new `DepartmentHeadcount.highest_rank_name: str | None`, `DepartmentHeadcount.highest_rank_members: tuple[DepartmentHighestRankMember, ...]`.

- [ ] **Step 1: Write the failing repository test**

Create users in one department across two rank levels, including two highest-rank users with the same display name, then assert:

```python
headcount.highest_rank_name == "正式员工"
headcount.highest_rank_members == (
    DepartmentHighestRankMember("同名", first.employee_number),
    DepartmentHighestRankMember("同名", second.employee_number),
)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/bin/pytest tests/core/test_repository.py -k department_headcount_highest_rank_members -q`

Expected: FAIL because the projection fields do not exist.

- [ ] **Step 3: Implement the minimal repository projection**

Add the immutable member projection. After building the existing grouped rank counts, query the employees in the selected non-empty departments with their ranks, select each department's greatest non-null `sort_order`, and attach all tied employees ordered by `employee_number`. Do not add per-department queries.

- [ ] **Step 4: Run repository tests and verify GREEN**

Run: `.venv/bin/pytest tests/core/test_repository.py -k 'department_headcount or department_headcounts' -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: include highest rank members in department counts"
```

### Task 2: Department command rendering

**Files:**
- Modify: `src/dzmm_bot/core/commands.py:604-627`
- Modify: `tests/core/test_group_commands.py:1010-1070`

**Interfaces:**
- Consumes: `DepartmentHeadcount.highest_rank_name`, `DepartmentHeadcount.highest_rank_members`, and existing `format_employee_number()`.
- Produces: department blocks ending in `最高职位者：{职位} {成员列表}`.

- [ ] **Step 1: Write failing command tests**

Update the existing command test so `/部门人数` and `/我的部门人数` expect the highest-rank line. Add tied highest-rank users and assert duplicate names render as:

```text
最高职位者：正式员工 同名 #0003、同名 #0004
```

Also assert unique names do not expose employee numbers.

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv/bin/pytest tests/core/test_group_commands.py -k department_headcount -q`

Expected: FAIL because command output lacks `最高职位者`.

- [ ] **Step 3: Implement minimal rendering**

In `_department_headcounts`, count duplicate names within `highest_rank_members`; append a department line whose labels use `format_employee_number()` only when that member's name occurs more than once.

- [ ] **Step 4: Run focused and full verification**

Run:

```bash
.venv/bin/pytest tests/core/test_group_commands.py -k department_headcount -q
.venv/bin/pytest tests/core/test_repository.py tests/core/test_group_commands.py -q
.venv/bin/pytest -q
git diff --check
```

Expected: all tests pass and `git diff --check` has no output.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/commands.py tests/core/test_group_commands.py
git commit -m "feat: show department highest rank members"
```

