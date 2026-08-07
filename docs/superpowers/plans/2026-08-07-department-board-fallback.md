# Department Board Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow board members to directly change departments and to resolve every pending department request.

**Architecture:** Reuse `RankRecord.is_board` in the repository authorization queries. Existing pending rows remain valid because the board query will include them without data migration.

**Tech Stack:** Python, SQLAlchemy, pytest.

## Global Constraints

- Preserve the existing 24-hour department-request expiry.
- Do not alter user-owned `docs/HANDOFF.md`.
- Keep ordinary department approval scoped to higher-ranked target-department members.

---

### Task 1: Verify the new authorization rules

**Files:**
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_group_commands.py`

- [ ] **Step 1: Write the failing tests**

```python
assert repository.request_department_change("board", "核心技术部", now).status == "joined"
assert repository.list_approvable_department_requests("board", now) == [request]
assert repository.decide_department_requests("board", [request.number], "approved", now)[0].status == "approved"
```

- [ ] **Step 2: Run the focused tests and confirm they fail under the old department-only authorization check.**

### Task 2: Apply the board authorization rules

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`

- [ ] **Step 1: Make `request_department_change` update a board member directly after target validation.**
- [ ] **Step 2: Permit `is_board` approvers in list and decision paths without target-department or rank comparisons.**
- [ ] **Step 3: Run the focused tests and confirm they pass.**

### Task 3: Verify and deliver

**Files:**
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_group_commands.py`

- [ ] **Step 1: Run `pytest -q tests/core/test_repository.py tests/core/test_group_commands.py`.**
- [ ] **Step 2: Run `pytest -q` and `git diff --check`.**
- [ ] **Step 3: Deploy the verified commit and check all service health endpoints.**
