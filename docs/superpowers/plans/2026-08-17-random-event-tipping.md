# Random Event Tipping Phase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable, configurable random-event tipping phase with real employee-to-employee coin transfers and globally unique employee display names.

**Architecture:** Persist `tipping` on the existing random-event row and persist every tip in a dedicated table. The repository owns state transitions, row locks, balance transfers, summaries, and timeout settlement; command/service layers only parse and route. A single Alembic migration first resolves historical duplicate names, then installs database constraints and tipping storage so application-level checks always have a database backstop.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL/SQLite, pytest, vanilla HTML/CSS/JavaScript admin console.

## Global Constraints

- State flow is exactly `signup -> in_progress -> tipping -> ended`.
- Tipping starts only when the final active participant sends `/退出`; reaching target rounds alone never starts it.
- Base event rewards remain immediate on `/退出`; early leavers receive zero base reward but remain valid tip recipients.
- Tipping duration defaults to `120` seconds, is configurable from `10` through `3600`, and is snapshotted into the event deadline when tipping starts.
- All employees may tip event participants with `/打赏 员工名称 金额`; positive integers only, no self-tipping, no overdraft, no fee, and repeated tips are allowed.
- Tipping transfers real balances atomically and emits both “随机事件打赏支出” and “随机事件打赏收入” ledger entries.
- Ordinary group chat resumes during tipping, while new games, new random events, and `/修改名称` remain blocked.
- Automatic and forced settlement retain completed transfers and publish one deterministic summary.
- Trimmed display names are globally unique by exact character comparison; `G` and `g` remain distinct.
- Historical duplicate-name groups are renamed to `原名称#工号`; non-conflicting names remain unchanged.
- No migration may overwrite unrelated administrator reply-template customizations.

---

### Task 1: Persist tipping data and unique employee names

**Files:**
- Create: `migrations/versions/20260817_44_random_event_tipping.py`
- Create: `tests/deploy/test_random_event_tipping_migration.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `tests/deploy/test_artifacts.py`

**Interfaces:**
- Produces: `RandomEventTipRecord`, `RandomEventSettingsRecord.tipping_duration_seconds`, `RandomEventRecord.tipping_started_at`, and `RandomEventRecord.tipping_deadline`.
- Produces: database uniqueness for `users.display_name` and active-event uniqueness for states `signup`, `in_progress`, and `tipping`.

- [ ] **Step 1: Write migration tests that model real legacy data**

Create a pre-44 schema containing duplicate users (`同名` with employee numbers 1 and 2), a non-conflicting user, settings row, event rows, and the old partial active-event index. Assert upgrade results:

```python
assert upgraded_names == ["同名#0001", "同名#0002", "唯一名称"]
assert settings["tipping_duration_seconds"] == 120
assert {"tipping_started_at", "tipping_deadline"} <= random_event_columns
assert "random_event_tips" in inspector.get_table_names()
assert unique_display_name_constraint_exists(connection)
assert active_event_index_mentions_tipping(connection)
```

Also insert a legacy collision such as `同名#0001` and prove the migration deterministically appends that employee's own number until every name is unique. Verify downgrade removes only the new table/columns/constraints and restores the old active-state index.

- [ ] **Step 2: Run migration tests and verify RED**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/deploy/test_random_event_tipping_migration.py -q
```

Expected: FAIL because revision `20260817_44` and the new schema members do not exist.

- [ ] **Step 3: Implement the migration and ORM records**

Use revision metadata:

```python
revision = "20260817_44"
down_revision = "20260815_43"
```

Migration order must be:

1. Add `tipping_duration_seconds` with server default `120`.
2. Add nullable tipping timestamps.
3. Create `random_event_tips` with FKs to `random_events`, `users`, and `inbound_messages`; make `inbound_message_id` unique and index `event_id`.
4. Drop and recreate `ux_random_events_one_active_group` with `state IN ('signup', 'in_progress', 'tipping')` for PostgreSQL and SQLite.
5. Read users ordered by employee number, resolve only conflicting names with `suffix = f"#{employee_number:04d}"` and `f"{name[:64 - len(suffix)]}{suffix}"`, repeat collision resolution until unique, update rows, then add the unique display-name constraint/index.

Add ORM fields:

```python
class RandomEventTipRecord(Base):
    __tablename__ = "random_event_tips"
    id: Mapped[UUID]
    event_id: Mapped[UUID]
    sender_user_id: Mapped[UUID]
    recipient_user_id: Mapped[UUID]
    amount: Mapped[int]
    inbound_message_id: Mapped[UUID]
    created_at: Mapped[datetime]
```

- [ ] **Step 4: Run migration and artifact tests**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/deploy/test_random_event_tipping_migration.py tests/deploy/test_artifacts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/20260817_44_random_event_tipping.py src/dzmm_bot/core/schema.py tests/deploy/test_random_event_tipping_migration.py tests/deploy/test_artifacts.py
git commit -m "feat: persist random event tipping data"
```

---

### Task 2: Enforce unique employee names in business flows

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_group_commands.py`

**Interfaces:**
- Produces: `EmployeeNameTakenError(ValueError)` for new-user creation conflicts.
- Produces: `RenameEmployeeResult.status == "name_taken"` for rename conflicts.
- Produces: reply scenario `name_taken` for `/入职` and `/修改名称`, both defaulting to `名称已被占用。`.

- [ ] **Step 1: Replace duplicate-allowed tests with uniqueness tests**

Cover all of these assertions:

```python
with pytest.raises(EmployeeNameTakenError):
    repository.create_user("second", "同名", now, 0)
assert repository.rename_user("first", " 已占用 ").status == "name_taken"
assert repository.rename_user("first", "First").status == "renamed"
assert repository.rename_user("other", "first").status == "renamed"  # exact case rule
```

At command level, assert `/入职 同名` and `/修改名称 同名` both reply exactly `名称已被占用。`, while an already-employed platform ID still returns the existing “already joined” response before considering the supplied name.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_repository.py -k 'create_user or rename_user' -q
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_group_commands.py -k 'join or rename' -q
```

Expected: FAIL because duplicate names are currently allowed.

- [ ] **Step 3: Implement serialized name writes and typed outcomes**

Add:

```python
class EmployeeNameTakenError(ValueError):
    pass
```

For `create_user`, check the existing platform ID first, then acquire the existing employee-number counter row lock before allocating the number and checking normalized display-name occupancy. Raise `EmployeeNameTakenError` before insertion. For `rename_user`, acquire the same singleton counter row lock before checking and writing the name, returning `name_taken` on conflict. Keep the database unique constraint as the final concurrent-write guard.

Catch `EmployeeNameTakenError` only in `_join`; map rename `name_taken` normally. Add managed templates:

```python
TemplateDefinition("/入职", "name_taken", "名称已占用", "名称已被占用。", ("{日期}",))
TemplateDefinition("/修改名称", "name_taken", "名称已占用", "名称已被占用。", ("{日期}",))
```

- [ ] **Step 4: Update tests that intentionally created duplicate employees**

Tests for bonus ambiguity, department display, skip-by-name ambiguity, and similar historical behavior must build their ambiguity fixtures through raw legacy rows only when testing migrations. Runtime repository tests must now use unique display names and remove obsolete `ambiguous_target` expectations made impossible by the constraint.

- [ ] **Step 5: Run employee, command, and repository suites**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_group_commands.py tests/core/test_repository.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py src/dzmm_bot/core/reply_templates.py tests/core/test_repository.py tests/core/test_group_commands.py
git commit -m "feat: require unique employee names"
```

---

### Task 3: Add the durable tipping state transition and timeout settlement

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/service.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_service.py`

**Interfaces:**
- Produces: `RandomEventSettings.tipping_duration_seconds: int`.
- Produces: `RandomEventTippingSummary` data used by commands, admin APIs, and final messages.
- Produces: `_settle_random_event_tipping(session, event, now, forced=False) -> None`.

- [ ] **Step 1: Write lifecycle tests**

Create a two-participant in-progress event and assert:

```python
assert repository.leave_random_event("first", now).startswith("rewarded")
assert repository.active_random_event_state() == "in_progress"
assert repository.leave_random_event("second", now).startswith("rewarded")
assert repository.active_random_event_state() == "tipping"
```

Also verify early exit remains tip-eligible, deadline equals `now + timedelta(seconds=settings.tipping_duration_seconds)`, changing settings after entry does not change the deadline, ordinary messages during tipping do not add details/rounds, and other games remain blocked.

Add timeout tests at `deadline - 1 microsecond` and exactly `deadline`; assert exactly one summary outbound, one state transition to `ended`, and no duplicate message on repeated job runs. Add a restart-style test by constructing a fresh `CoreRepository` on the same database before running the due job.

- [ ] **Step 2: Run lifecycle tests and verify RED**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_repository.py -k 'random_event and tipping' -q
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_service.py -k 'random_event and tipping' -q
```

Expected: FAIL because the last exit currently ends the event.

- [ ] **Step 3: Implement settings, transition, summary rendering, and due job**

Extend these signatures:

```python
def set_random_event_settings(
    self,
    schedule_times: list[str],
    signup_notice_template: str,
    signup_timeout_minutes: int,
    reminder_interval_minutes: int,
    signup_allowed_commands: list[str] | None = None,
    in_progress_allowed_commands: list[str] | None = None,
    blocked_message: str | None = None,
    submission_enabled: bool | None = None,
    submission_draft_timeout_minutes: int | None = None,
    submission_max_participants: int | None = None,
    submission_default_target_rounds: int | None = None,
    submission_default_event_reward: int | None = None,
    submission_approval_reward: int | None = None,
    tipping_duration_seconds: int | None = None,
) -> RandomEventSettings:
```

Validate `10 <= tipping_duration_seconds <= 3600`.

Change the last-participant branch in `leave_random_event` to set:

```python
event.state = "tipping"
event.tipping_started_at = now
event.tipping_deadline = now + timedelta(seconds=settings.tipping_duration_seconds)
schedule.status = "tipping"
```

Enqueue the managed `opened` template with participant/base-reward lines. Extend all active-event lookups, gameplay gates, schedule status display, and force-end acceptance to include `tipping`. In `run_random_event_jobs`, settle a due tipping event before starting any due schedule.

During tipping, `classify_random_event_message` and `record_random_event_round` must return `none` for ordinary content. Adjust `CoreService` so ordinary non-command messages bypass the random-event blocked response in `tipping`, while forbidden commands still pass through the event command gate.

- [ ] **Step 4: Run lifecycle and service tests**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_repository.py -k 'random_event' -q
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_service.py -k 'random_event' -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/service.py src/dzmm_bot/core/reply_templates.py tests/core/test_repository.py tests/core/test_service.py
git commit -m "feat: add random event tipping phase"
```

---

### Task 4: Implement atomic real-balance tipping and group commands

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/service.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_group_commands.py`
- Modify: `tests/core/test_service.py`

**Interfaces:**
- Produces: `RandomEventTipResult` with `status`, sender/recipient names, amount, and resulting balances.
- Produces: `CoreRepository.tip_random_event(platform_id, recipient_name, amount, platform_message_id, now) -> RandomEventTipResult`.
- Consumes: `RandomEventTipRecord` and the `tipping` state from Tasks 1 and 3.

- [ ] **Step 1: Write repository rejection and success tests**

Test statuses and zero side effects for:

```text
not_joined, no_tipping_event, invalid_amount, recipient_not_found,
recipient_not_participant, self_tip, insufficient_balance, expired
```

For success, assert sender `-5`, recipient `+5`, one tip row, and exactly two balance rows with sources `random_event_tip_out` and `random_event_tip_in`. Repeat the same platform message ID and prove no second transfer. Verify multiple tips accumulate.

- [ ] **Step 2: Write PostgreSQL concurrency tests**

Using `migrated_postgres_url`, a `Barrier`, and independent repositories, submit two tips whose combined amount exceeds the sender balance; assert at most the affordable transfers succeed and balance never becomes negative. Run opposite-direction tips concurrently and require both threads to finish without deadlock. Race a deadline/force settlement against a tip and assert no transfer exists after the event is ended.

- [ ] **Step 3: Run tip tests and verify RED**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_repository.py -k 'random_event_tip' -q
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_group_commands.py -k 'tip' -q
```

Expected: FAIL because `/打赏` and the repository method do not exist.

- [ ] **Step 4: Implement the transfer transaction**

Define:

```python
def tip_random_event(
    self,
    platform_id: str,
    recipient_name: str,
    amount: int,
    platform_message_id: str,
    now: datetime,
) -> RandomEventTipResult:
```

Resolve the already accepted `InboundRecord` by its unique `platform_message_id`; store its UUID on the tip row. Lock event first, reject at `now >= tipping_deadline`, resolve sender and exact recipient name, require a participant record, reject self-tip, then lock the two users in sorted UUID order. Use `_apply_balance_change(sender, -amount, "random_event_tip_out", now)` and `_apply_balance_change(recipient, amount, "random_event_tip_in", now)`. Insert the unique tip record in the same transaction. A pre-existing tip for the same inbound UUID returns an idempotent duplicate result without changing balances.

Add labels:

```python
"random_event_tip_out": "随机事件打赏支出",
"random_event_tip_in": "随机事件打赏收入",
```

- [ ] **Step 5: Add command parsing and managed replies**

Add `/打赏` to command definitions and routing. Parse from the right so names may contain spaces:

```python
payload = content[len("/打赏"):].strip()
parts = payload.rsplit(maxsplit=1)
```

Pass `message.platform_message_id`; the repository resolves the already accepted inbound UUID. Map every repository status to a dedicated managed template. Add `/打赏` to `_RANDOM_EVENT_INDEPENDENT_COMMANDS` so the command reaches its own business validation in all random-event states. Successful output remains a reply to the source message through normal outbound fencing.

- [ ] **Step 6: Run tip and ledger tests**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_repository.py -k 'random_event_tip or balance_ledger' -q
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_group_commands.py -k 'tip' -q
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_service.py -k 'tip or random_event' -q
```

Expected: PASS; PostgreSQL-only cases may skip when `TEST_DATABASE_URL` is absent.

- [ ] **Step 7: Commit**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py src/dzmm_bot/core/service.py src/dzmm_bot/core/reply_templates.py tests/core/test_repository.py tests/core/test_group_commands.py tests/core/test_service.py
git commit -m "feat: transfer random event tips"
```

---

### Task 5: Expose tipping configuration, status, details, help, and AI guidance

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/ai_knowledge.py`
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `tests/core/test_app.py`
- Modify: `tests/core/test_group_commands.py`
- Modify: `tests/admin/test_app.py`

**Interfaces:**
- Produces: `RandomEventSettingsResponse.tipping_duration_seconds`.
- Produces: gameplay summary fields `tipping_deadline` and `tip_total`.
- Produces: random-event details `tips[]` with sender, recipient, amount, and timestamp.

- [ ] **Step 1: Write failing API and admin rendering tests**

Assert core and admin settings GET/PATCH round-trip `tipping_duration_seconds`, reject 9 and 3601, and preserve existing optional submission settings. Assert current gameplay reports:

```json
{
  "game_type": "random_event",
  "state": "tipping",
  "tipping_deadline": "2026-08-17T...+08:00",
  "tip_total": 8
}
```

Assert event details include tip rows. Static HTML/JS tests must find the duration input, save payload property, `tipping: "打赏中"` status label, deadline/total rendering, and force-end action.

- [ ] **Step 2: Run API/admin tests and verify RED**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_app.py -k 'random_event' -q
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/admin/test_app.py -k 'random_event' -q
```

Expected: FAIL because the new fields and controls are absent.

- [ ] **Step 3: Extend API models and repository summaries**

Add:

```python
tipping_duration_seconds: int = Field(default=120, ge=10, le=3600)
tipping_deadline: AwareDatetime | None = None
tip_total: int = 0
```

Return tip detail objects with `sender_display_name`, `recipient_display_name`, `amount`, and `created_at`. Ensure `active_gameplay_summary` and `gameplay_admin_summary` include `tipping`, list all event participants, and expose `/打赏 员工名称 金额` as the relevant action.

- [ ] **Step 4: Add admin configuration and displays**

Add a number input to the existing random-event settings modal:

```html
<input id="random-event-tipping-duration" type="number" min="10" max="3600" required>
```

Populate it from GET and include `tipping_duration_seconds` in PATCH. Render `打赏中`, countdown deadline, total tips, and detail rows using `escapeHtml` for every name. Extend force-end display to accept the state without creating a new endpoint.

- [ ] **Step 5: Add help and AI knowledge**

Add `/打赏 员工名称 金额` to `/帮助 随机事件`, the command library, and random-event AI knowledge. Guidance must say the command is only available after all participants exit, moves real coins, and forbids self-tipping; it must never imply the AI can execute the transfer.

- [ ] **Step 6: Run core/admin/help tests**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_app.py tests/core/test_group_commands.py tests/admin/test_app.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py src/dzmm_bot/core/ai_knowledge.py src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js tests/core/test_app.py tests/core/test_group_commands.py tests/admin/test_app.py
git commit -m "feat: manage random event tipping"
```

---

### Task 6: Verify forced settlement and final message behavior end to end

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_group_commands.py`
- Modify: `tests/core/test_app.py`

**Interfaces:**
- Consumes: `_settle_random_event_tipping(...)` from Task 3 and persisted tips from Task 4.
- Produces: one shared deterministic formatter for automatic and forced summaries.

- [ ] **Step 1: Write final-summary and forced-end tests**

Use three participants with totals 8, 8, and 0. Assert ordering is total descending, then employee number ascending; individual lines are chronological. Assert no-tip output contains `本场无人打赏`. Force end during tipping through both the board command and internal admin endpoint; assert existing transfers remain, state becomes `ended`, and only one summary outbound exists. Preserve `cancelled` for force-end actions that occur before tipping.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_repository.py tests/core/test_group_commands.py tests/core/test_app.py -k 'tipping and (summary or force)' -q
```

Expected: FAIL until forced settlement uses the same summary path.

- [ ] **Step 3: Consolidate settlement formatting without changing other game force-end behavior**

Implement a single helper that reads participant/base-reward/tip rows and returns template values:

```python
def _random_event_tipping_template_values(
    session: Session,
    event: RandomEventRecord,
) -> dict[str, object]:
    return {
        "{场景名称}": event.scene_name,
        "{参与者打赏汇总}": rendered_rows,
        "{打赏总额}": total,
    }
```

Call it from timeout and tipping-stage force end. Do not refund tips. Preserve the existing generic admin-forced message for events forced during signup or in-progress.

- [ ] **Step 4: Run random-event, force-end, and outbound tests**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_repository.py tests/core/test_group_commands.py tests/core/test_app.py tests/core/test_service.py -k 'random_event or force_end or outbound' -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/reply_templates.py tests/core/test_repository.py tests/core/test_group_commands.py tests/core/test_app.py
git commit -m "test: complete random event tipping settlement"
```

---

### Task 7: Final regression, migration, and review gate

**Files:**
- Verify all files changed in Tasks 1–6.

**Interfaces:**
- Produces: merge-ready feature branch with clean worktree and review findings resolved.

- [ ] **Step 1: Run static and migration checks**

Run:

```bash
git diff --check
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/python -m compileall -q src/dzmm_bot
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/deploy/test_random_event_tipping_migration.py tests/deploy/test_artifacts.py -q
```

Expected: all exit 0.

- [ ] **Step 2: Run focused feature suites**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_repository.py tests/core/test_group_commands.py tests/core/test_service.py tests/core/test_app.py tests/admin/test_app.py -k 'random_event or tip or rename or create_user or balance_ledger' -q
```

Expected: PASS; PostgreSQL concurrency tests may skip only when `TEST_DATABASE_URL` is not configured.

- [ ] **Step 3: Run the full suite**

Run:

```bash
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q
```

Expected: PASS with only documented environment-dependent skips and existing deprecation warnings.

- [ ] **Step 4: Request code review**

Review the complete feature diff from the branch base through HEAD. Require explicit checks for migration collision safety, PostgreSQL lock ordering, deadline races, idempotency, ordinary-chat routing, forced settlement, XSS escaping, and accidental changes to unrelated game behavior. Resolve every Critical or Important finding and rerun affected tests.

- [ ] **Step 5: Re-run final verification after review changes**

Run:

```bash
git status --short
git diff --check
PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q
```

Expected: clean tracked worktree, no diff-check failures, full suite PASS.

- [ ] **Step 6: Finish the branch**

Use `superpowers:finishing-a-development-branch` and ask whether to merge locally, push a pull request, or preserve the branch. Do not deploy without a separate explicit deployment instruction.
