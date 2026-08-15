# Random Event Submission Single-Seat Roles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the player-facing role-capacity question from random-event submissions so every submitted role automatically occupies one seat, while preserving in-progress legacy drafts.

**Architecture:** Keep the existing submission JSON and formal scene schema unchanged by storing every player-entered role as `{"role": name, "capacity": 1}`. Make `role_name` perform the complete role insertion, normalize legacy `role_capacity` drafts at the handler boundary before routing the current message, and relax only the submission role-count validator from 20 to the configured participant ceiling.

**Tech Stack:** Python 3.12+, SQLAlchemy 2, pytest, existing `RandomEventSubmissionHandler` and `CoreRepository`.

## Global Constraints

- Player submissions never ask for role capacity; each entered role has `capacity=1`.
- Role names remain 1–32 characters and unique within a submission.
- The role-count ceiling equals the submission participant count, which remains bounded by `submission_max_participants` (default 99).
- Legacy drafts at `role_capacity` are normalized once without losing the next plain-text message.
- Administrator-created formal scenes retain multi-seat role support.
- Do not change submission rewards, review, notification, AI-memory, or gameplay-gate behavior.
- Do not deploy automatically.

---

### Task 1: Make new role entry single-step

**Files:**
- Modify: `tests/core/test_random_event_submissions.py`
- Modify: `src/dzmm_bot/core/random_event_submissions.py`

**Interfaces:**
- Consumes: `RandomEventSubmissionHandler.handle(message: InboundMessage)` and `CoreRepository.replace_random_event_submission_content`.
- Produces: `role_name` input that immediately stores `capacity=1` and advances to `role_name` or `event_name`.

- [ ] **Step 1: Rewrite the complete-wizard test to describe the new interaction**

Use three unique role-name messages for a three-person event and assert that no reply contains `身份人数`, that the third identity advances to `事件名称`, and that preview shows all roles with `× 1`.

```python
assert "身份名称" in handler.handle(_direct("3")).text
assert "还剩 2" in handler.handle(_direct("调查员")).text
assert "还剩 1" in handler.handle(_direct("嫌疑人")).text
assert "事件名称" in handler.handle(_direct("目击者")).text
```

- [ ] **Step 2: Add a focused persistence test**

After two role names for a two-person draft, fetch the active submission and assert the literal role payload:

```python
assert draft.content["roles"] == [
    {"role": "调查员", "capacity": 1},
    {"role": "嫌疑人", "capacity": 1},
]
assert draft.current_step == "event_name"
```

This test must fail if `role_name` still transitions to `role_capacity` or stores any other capacity.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```bash
.venv/bin/pytest -q \
  tests/core/test_random_event_submissions.py::test_submission_wizard_collects_complete_scene_one_field_at_a_time \
  tests/core/test_random_event_submissions.py::test_submission_role_names_each_fill_one_seat
```

Expected: FAIL because the existing handler still asks for identity capacity.

- [ ] **Step 4: Implement immediate single-seat insertion**

In `_accept_plain_value`, replace the `role_name -> role_capacity` transition with construction of `{"role": value, "capacity": 1}`. Preserve `_editing_role_index` insertion order, clear role-edit temporary fields, and calculate the next step from `len(roles)` versus `participant_count`. Remove normal new-flow parsing from the `role_capacity` branch; legacy handling belongs to Task 2.

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run the Step 3 command. Expected: both tests PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/dzmm_bot/core/random_event_submissions.py tests/core/test_random_event_submissions.py
git commit -m "feat: default submitted roles to one seat"
```

---

### Task 2: Preserve legacy drafts and role controls

**Files:**
- Modify: `tests/core/test_random_event_submissions.py`
- Modify: `src/dzmm_bot/core/random_event_submissions.py`

**Interfaces:**
- Consumes: persisted legacy drafts with `current_step == "role_capacity"`, `_working_role`, optional `_editing_role_index`, and optional role-edit rollback fields.
- Produces: `_normalize_legacy_role_capacity(draft, now) -> RandomEventSubmission`, returning a persisted draft at `role_name` or `event_name` with the legacy role stored once at capacity 1.

- [ ] **Step 1: Add failing legacy-resume tests**

Create a draft directly through `replace_random_event_submission_content` with one existing role, `_working_role="嫌疑人"`, `participant_count=3`, and `current_step="role_capacity"`.

Cover both observable paths:

```python
resumed = handler.handle(_direct("/投稿 随机事件"))
assert "还剩 1" in resumed.text
assert repository.active_random_event_submission(
    "employee-1", NOW
).content["roles"][-1] == {
    "role": "嫌疑人", "capacity": 1,
}
```

```python
reply = handler.handle(_direct("目击者"))
assert "事件名称" in reply.text
assert [item["role"] for item in draft.content["roles"]] == [
    "调查员", "嫌疑人", "目击者",
]
```

The second test catches dropping the current plain-text input after normalization.

- [ ] **Step 2: Add failing edit, delete, and back tests**

Update the existing role-edit test so `/修改身份 1` followed by one new name immediately returns to `event_name`. Add assertions that `/删除身份 1` returns to `role_name`, and `/上一步` from both partially-filled `role_name` and full `event_name` removes the last role and remains at `role_name`. No resulting reply or draft may use `role_capacity`.

- [ ] **Step 3: Run the compatibility/control tests and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/core/test_random_event_submissions.py \
  -k "legacy_role_capacity or edit_role or delete_role or back_from_role or back_from_event_name"
```

Expected: FAIL because legacy normalization is absent and back/edit still enter `role_capacity`.

- [ ] **Step 4: Normalize legacy state before command routing**

Add a private handler helper that:

```python
def _normalize_legacy_role_capacity(
    self, draft: RandomEventSubmission, now: datetime
) -> RandomEventSubmission:
    if draft.current_step != "role_capacity":
        return draft
    data = deepcopy(draft.content)
    roles = data.setdefault("roles", [])
    for role in roles:
        role["capacity"] = 1
    working_role = data.pop("_working_role", None)
    edit_index = data.pop("_editing_role_index", None)
    data.pop("_editing_role_original", None)
    data.pop("_editing_return_step", None)
    data.pop("_editing_events_original", None)
    total = int(data.get("participant_count", 0))
    if (
        isinstance(working_role, str)
        and 1 <= len(working_role) <= 32
        and all(item.get("role") != working_role for item in roles)
        and len(roles) < total
    ):
        role = {"role": working_role, "capacity": 1}
        if isinstance(edit_index, int) and 0 <= edit_index <= len(roles):
            roles.insert(edit_index, role)
        else:
            roles.append(role)
    next_step = "event_name" if len(roles) >= total else "role_name"
    return self._repository.replace_random_event_submission_content(
        draft.id, data, next_step, now
    )
```

It must append or reinsert `_working_role` at capacity 1 only when valid, clear all role-edit temporary fields, persist `role_name` or `event_name`, and return unchanged drafts for every other step. Call it on resumed `/投稿 随机事件` submissions before rendering the prompt and on active direct drafts before handling commands or plain text.

- [ ] **Step 5: Remove old control transitions**

Change `_go_back` so partial `role_name` and full `event_name` pop the last saved role and return to `role_name`; keep the first-role path returning to `participant_count`. Change role editing to accept one replacement name and restore it at the original index. Keep role deletion at `role_name` and preserve event invalidation behavior.

- [ ] **Step 6: Run all submission handler tests and verify GREEN**

Run:

```bash
.venv/bin/pytest -q tests/core/test_random_event_submissions.py
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/dzmm_bot/core/random_event_submissions.py tests/core/test_random_event_submissions.py
git commit -m "fix: migrate legacy submission role steps"
```

---

### Task 3: Allow one role per configured participant

**Files:**
- Modify: `tests/core/test_random_event_submissions.py`
- Modify: `src/dzmm_bot/core/repository.py`

**Interfaces:**
- Consumes: `_validate_random_event_submission_content(content, maximum_participants, reward, target_rounds)`.
- Produces: validation accepting up to `participant_count` role entries while retaining the 1–20 event-template limit.

- [ ] **Step 1: Add a failing 21-participant confirmation test**

Create a draft with `participant_count=21`, 21 literal unique `capacity=1` roles, and one event template referencing one valid role. Confirm the submission and assert it becomes pending.

```python
roles = [
    {"role": f"身份{index}", "capacity": 1}
    for index in range(1, 22)
]
assert repository.confirm_random_event_submission("employee-1", NOW).status == "pending"
```

This must fail under the old 20-role validator.

- [ ] **Step 2: Run the new validator test and verify RED**

Run:

```bash
.venv/bin/pytest -q \
  tests/core/test_random_event_submissions.py::test_submission_accepts_one_role_per_configured_participant
```

Expected: FAIL with `身份和事件模板数量需在 1 至 20 之间`.

- [ ] **Step 3: Relax only the role-count condition**

In `_validate_random_event_submission_content`, require:

```python
1 <= len(roles) <= participant_count
1 <= len(events) <= 20
```

Keep the existing sum-of-capacities equality check and formal scene validation. Use separate error messages so role-count and event-template failures remain clear.

- [ ] **Step 4: Run repository and submission tests**

Run:

```bash
.venv/bin/pytest -q \
  tests/core/test_random_event_submissions.py \
  tests/core/test_repository.py -k "random_event"
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_random_event_submissions.py
git commit -m "fix: allow single-seat roles up to participant count"
```

---

### Task 4: Full regression and handoff

**Files:**
- Verify only; do not edit unrelated files.

**Interfaces:**
- Consumes: commits from Tasks 1–3.
- Produces: a verified feature branch ready for the user's merge/deployment decision.

- [ ] **Step 1: Check the final diff**

```bash
git diff --check main...HEAD
git status --short
```

Expected: no whitespace errors; only planned files and pre-existing user files are present.

- [ ] **Step 2: Run the full test suite**

```bash
.venv/bin/pytest -q
```

Expected: all tests pass, with only the repository's existing skips and deprecation warnings.

- [ ] **Step 3: Confirm the player-visible contract**

Run:

```bash
.venv/bin/pytest -q \
  tests/core/test_random_event_submissions.py::test_submission_wizard_collects_complete_scene_one_field_at_a_time \
  tests/core/test_random_event_submissions.py::test_submission_role_names_each_fill_one_seat \
  tests/core/test_random_event_submissions.py::test_legacy_role_capacity_plain_text_is_used_as_next_role \
  tests/core/test_random_event_submissions.py::test_edit_role_refills_only_role_name \
  tests/core/test_random_event_submissions.py::test_delete_role_returns_to_role_name \
  tests/core/test_random_event_submissions.py::test_back_from_event_name_reopens_last_role \
  tests/core/test_random_event_submissions.py::test_submission_accepts_one_role_per_configured_participant
```

Expected: all named tests pass; their previews contain `× 1`, and no tested response contains `身份人数`.

- [ ] **Step 4: Use the finishing-development-branch flow**

Present the required merge/PR/keep options. Do not merge, push, or deploy without the user's selected option.
