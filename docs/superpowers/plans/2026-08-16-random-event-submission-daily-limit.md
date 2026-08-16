# Random Event Submission Daily Limit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce one successfully confirmed random-event submission per employee per Beijing calendar day without limiting draft creation or editing.

**Architecture:** Reuse `RandomEventSubmissionRecord.submitted_at` and the user row lock already held by `confirm_random_event_submission()`. Add a typed daily-limit exception so the private-chat handler can select a dedicated reply template without matching exception text.

**Tech Stack:** Python 3.13 locally / Python 3.12 production, SQLAlchemy 2, SQLite and PostgreSQL, pytest.

## Global Constraints

- The limit is fixed at exactly one confirmed submission per employee per Beijing calendar day.
- Only a successful `/确认投稿` consumes the allowance.
- Draft creation, editing, cancellation, and expiry do not consume it.
- Withdrawal, approval, and rejection do not restore an allowance consumed that day.
- Reset occurs naturally at Beijing `00:00`; no scheduled job, setting, counter, or migration is added.
- Rejection by the daily guard leaves the draft status, content, and existing expiry unchanged.
- Existing untracked `.env`, `.DS_Store`, and `docs/BOT_MESSAGE_TRANSPORT_HANDOFF.md` remain untouched.

---

### Task 1: Enforce the limit atomically in the repository

**Files:**
- Modify: `src/dzmm_bot/core/repository.py:1140-1150,1728-1782`
- Modify: `tests/core/test_random_event_submissions.py:28-180`
- Modify: `tests/core/test_repository.py:6770-7040`

**Interfaces:**
- Consumes: `CoreRepository.confirm_random_event_submission(platform_id: str, now: datetime) -> RandomEventSubmission` and `RandomEventSubmissionRecord.submitted_at`.
- Produces: `RandomEventSubmissionDailyLimitError`, raised before a preview draft is mutated when the user already submitted during the current Beijing day.

- [ ] **Step 1: Add a preview-draft test helper**

Extract the existing content setup into:

```python
def _preview_submission(repository, platform_id="employee-1", now=NOW):
    started = repository.start_random_event_submission(platform_id, now)
    return repository.replace_random_event_submission_content(
        started.submission.id,
        {
            "scene_name": f"失踪的咖啡-{platform_id}",
            "signup_text": "茶水间出事了，快来报名。",
            "participant_count": 3,
            "roles": [
                {"role": "调查员", "capacity": 2},
                {"role": "嫌疑人", "capacity": 1},
            ],
            "events": [
                {"name": "现场", "opening_text": "{调查员}发现了空杯。"}
            ],
        },
        "preview",
        now,
    )
```

Keep `_pending_submission()` as a wrapper that creates the employee, calls this helper, and confirms it. Preserve all existing assertions.

- [ ] **Step 2: Write failing same-day and next-day tests**

Import the future exception exactly:

```python
from dzmm_bot.core.repository import (
    CoreRepository,
    RandomEventSubmissionDailyLimitError,
)
```

Confirm a first submission at `NOW`, withdraw it, and prepare a second preview. Assert confirmation at `NOW + timedelta(hours=1)` raises the typed exception and leaves the second draft's `current_step`, `content`, and `expires_at` unchanged. Cancel that draft, prepare a new preview at `NOW + timedelta(days=1)`, confirm it, and assert `status == "pending"`. This avoids bypassing the existing draft-expiry behavior.

- [ ] **Step 3: Write failing status, user-isolation, and PostgreSQL concurrency tests**

For each first-submission terminal state `approved` and `rejected`, use the existing repository approval/rejection method, prepare a second preview, and assert same-day confirmation raises `RandomEventSubmissionDailyLimitError`. Add a separate test proving two different employees can each confirm once on the same day.

In `tests/core/test_repository.py`, use the existing `migrated_postgres_url`, `Barrier`, and `ThreadPoolExecutor` pattern. Prepare one complete preview draft, call `confirm_random_event_submission()` concurrently from two repository instances for the same employee, and assert exactly one call returns `pending`, the other raises `ValueError`, and the database contains exactly one row with non-null `submitted_at` for that employee.

- [ ] **Step 4: Run the new tests and verify RED**

```bash
PYTHONPATH=src .venv/bin/pytest tests/core/test_random_event_submissions.py -k 'daily_limit or different_employees' -q
```

Expected: collection or assertions fail because the exception and guard do not exist.

- [ ] **Step 5: Add the exception and atomic timestamp guard**

Add near the existing repository exceptions:

```python
class RandomEventSubmissionDailyLimitError(ValueError):
    pass
```

After the method has locked the user, resolved the preview draft, and validated its content—but before mutating `record.status`—add:

```python
day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
day_end = day_start + timedelta(days=1)
already_submitted = session.scalar(
    select(RandomEventSubmissionRecord.id).where(
        RandomEventSubmissionRecord.user_id == user.id,
        RandomEventSubmissionRecord.id != record.id,
        RandomEventSubmissionRecord.submitted_at >= day_start,
        RandomEventSubmissionRecord.submitted_at < day_end,
    )
)
if already_submitted is not None:
    raise RandomEventSubmissionDailyLimitError()
```

Keep the existing `UserRecord.with_for_update()` before this query. Do not change pending-submission precedence.

- [ ] **Step 6: Run all submission tests and verify GREEN**

```bash
PYTHONPATH=src .venv/bin/pytest tests/core/test_random_event_submissions.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add src/dzmm_bot/core/repository.py \
  tests/core/test_random_event_submissions.py \
  tests/core/test_repository.py
git commit -m "feat: limit random event submissions to once daily"
```

---

### Task 2: Return the dedicated player-facing message

**Files:**
- Modify: `src/dzmm_bot/core/random_event_submissions.py:1-155`
- Modify: `src/dzmm_bot/core/reply_templates.py:325-350`
- Modify: `tests/core/test_random_event_submissions.py:260-390`

**Interfaces:**
- Consumes: `RandomEventSubmissionDailyLimitError` from Task 1.
- Produces: reply-template scenario `("/确认投稿", "daily_limit")` with default text `你今天已经投稿过一次，请明天再来。`.

- [ ] **Step 1: Write a failing exact-reply test**

Prepare a first withdrawn submission and a second preview draft on the same day. Pass a direct `/确认投稿` message through `RandomEventSubmissionHandler.handle()` and assert:

```python
assert reply.text == "你今天已经投稿过一次，请明天再来。"
assert repository.active_random_event_submission(
    "employee-1", NOW + timedelta(hours=1)
).current_step == "preview"
```

- [ ] **Step 2: Run the handler test and verify RED**

```bash
PYTHONPATH=src .venv/bin/pytest tests/core/test_random_event_submissions.py -k daily_limit_reply -q
```

Expected: FAIL because no typed handler branch or template exists.

- [ ] **Step 3: Add the template and catch the typed exception**

Add:

```python
TemplateDefinition(
    "/确认投稿",
    "daily_limit",
    "今日投稿次数已用完",
    "你今天已经投稿过一次，请明天再来。",
    ("{日期}",),
),
```

Import `RandomEventSubmissionDailyLimitError` and catch it immediately before the existing `except ValueError` branch:

```python
except RandomEventSubmissionDailyLimitError:
    return self._reply(
        message,
        self._text("/确认投稿", "daily_limit", now),
    )
```

Keep every other validation error on the current `invalid_input` path.

- [ ] **Step 4: Run submission and template tests**

```bash
PYTHONPATH=src .venv/bin/pytest \
  tests/core/test_random_event_submissions.py \
  tests/core/test_reply_templates.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/dzmm_bot/core/random_event_submissions.py \
  src/dzmm_bot/core/reply_templates.py \
  tests/core/test_random_event_submissions.py
git commit -m "feat: explain the daily submission limit"
```

---

### Task 3: Full verification and deployment handoff

**Files:**
- Verify only; modify production files only for regressions introduced by Tasks 1–2.

**Interfaces:**
- Consumes: the repository guard and dedicated reply.
- Produces: reviewed, deployment-ready commits; no deployment without a separate explicit instruction.

- [ ] **Step 1: Run focused Core regression tests**

```bash
PYTHONPATH=src .venv/bin/pytest \
  tests/core/test_random_event_submissions.py \
  tests/core/test_service.py \
  tests/core/test_reply_templates.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run the complete suite**

```bash
PYTHONPATH=src .venv/bin/pytest -q
```

Expected: all mandatory tests pass; only documented optional tests skip.

- [ ] **Step 3: Inspect scope and preserved files**

```bash
git diff --check HEAD~2..HEAD
git status --short
git log --oneline -6
```

Expected: no whitespace errors; `.env`, `.DS_Store`, and `docs/BOT_MESSAGE_TRANSPORT_HANDOFF.md` remain untracked and unchanged.

- [ ] **Step 4: Request code review and fix every Critical or Important finding**

Review against `docs/superpowers/specs/2026-08-16-random-event-submission-daily-limit-design.md`, emphasizing transaction order, Beijing boundaries, state preservation, and typed template routing. Re-run affected tests after corrections.

- [ ] **Step 5: Report readiness without deploying**

Report commit range, focused/full test counts, skips, warnings, and preserved files. Deployment requires a separate explicit instruction.
