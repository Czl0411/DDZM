# Random Event Role Variables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render configured role variables in a full random event's formal opening as the participating players' display names, with an in-modal variable picker.

**Architecture:** The repository validates formal-opening variables against submitted scene seats. At full capacity it queries active participants joined to users, renders the event's selected template by role, stores the rendered text, then queues it. The modal tracks the focused opening textarea and inserts a chip token generated from current seat rows.

**Tech Stack:** Python 3, SQLAlchemy, FastAPI, pytest, vanilla JavaScript.

## Global Constraints

- Variables are only `{角色名}` tokens in formal role-play openings.
- A variable resolves to the display names of active participants sharing that role, ordered by join time and separated by `、`.
- Unknown non-empty braced variables are rejected when a scene is saved.
- The rendered formal opening replaces the selected template on the event record when the event enters `in_progress`.

---

### Task 1: Validate and render formal-opening role variables

**Files:**
- Modify: `src/dzmm_bot/core/repository.py:530-875,1950-2000`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Consumes: scene `seats: list[tuple[str, int]]`, formal opening templates, and full event participants.
- Produces: `_render_random_event_formal_opening(session, event) -> str`; scene mutation raises `ValueError` for an unknown `{角色}` variable.

- [ ] **Step 1: Write failing repository tests**

```python
def test_full_random_event_renders_role_variables(repository, session_factory):
    repository.create_random_event_scene("茶水间", "报名", ["{主持}对{员工}说开始。"], 1, 1, [("主持", 1), ("员工", 2)])
    # Start the event after 小明, 小红 and 小李 select their role seats.
    assert event.formal_opening_text == "小明对小红、小李说开始。"

def test_scene_rejects_unknown_formal_opening_role(repository):
    with pytest.raises(ValueError, match="不存在的角色变量"):
        repository.create_random_event_scene("茶水间", "报名", ["{未知}来了。"], 1, 1, [("主持", 1)])
```

- [ ] **Step 2: Run the focused tests to verify RED**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py -k 'role_variable or unknown_formal' -v`

Expected: FAIL because templates are not validated or rendered.

- [ ] **Step 3: Implement validation and full-event rendering**

```python
_ROLE_VARIABLE = re.compile(r"\{([^{}]+)\}")

def _validate_formal_opening_variables(openings: list[str], roles: set[str]) -> None:
    unknown = {match.group(1) for opening in openings for match in _ROLE_VARIABLE.finditer(opening)} - roles
    if unknown:
        raise ValueError(f"正式剧情开场白包含不存在的角色变量：{'、'.join(sorted(unknown))}")
```

Query active `RandomEventParticipantRecord` rows joined to `UserRecord`, ordered by `joined_at` then participant id. Build `{role: '、'.join(names)}`, substitute exact variable tokens in `event.formal_opening_text`, assign the rendered text back to that field, then enqueue it with the existing full-event message.

- [ ] **Step 4: Run the focused tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py -k 'role_variable or unknown_formal' -v`

Expected: PASS.

- [ ] **Step 5: Commit the repository slice**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: render random event role variables"
```

### Task 2: Add modal role-variable insertion controls

**Files:**
- Modify: `src/dzmm_bot/admin/static/admin.js:182-230,770-835`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Consumes: current `[data-random-event-role]` inputs and formal-opening textareas.
- Produces: `.scene-opening-variable-buttons` chips that insert a role token into the last focused opening textarea.

- [ ] **Step 1: Write failing static UI tests**

```python
def test_random_event_scene_script_renders_role_variable_buttons():
    script = Path("src/dzmm_bot/admin/static/admin.js").read_text()
    assert "renderRandomEventSceneOpeningVariables" in script
    assert "data-random-event-role-variable" in script
```

- [ ] **Step 2: Run the focused test to verify RED**

Run: `.venv/bin/python -m pytest tests/admin/test_app.py -k role_variable_buttons -v`

Expected: FAIL because the modal has no role-variable renderer.

- [ ] **Step 3: Implement the variable picker**

```javascript
function renderRandomEventSceneOpeningVariables() {
  const roles = [...randomEventSceneSeats.querySelectorAll("[data-random-event-role]")]
    .map((input) => input.value.trim()).filter(Boolean);
  randomEventSceneOpenings.querySelectorAll(".scene-opening-variable-buttons").forEach((container) => {
    container.innerHTML = [...new Set(roles)].map((role) => `<button data-random-event-role-variable="${escapeHtml(role)}" type="button">{${escapeHtml(role)}}</button>`).join("");
  });
}
```

Add one variable-button container per opening row. Refresh it when a seat is added, removed, or its role input changes. Record textarea focus and use `setRangeText` to insert the selected `{角色}` token at the cursor; append when no textarea has focus.

- [ ] **Step 4: Run the focused test to verify GREEN**

Run: `.venv/bin/python -m pytest tests/admin/test_app.py -k role_variable_buttons -v`

Expected: PASS.

- [ ] **Step 5: Commit the management UI slice**

```bash
git add src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/admin/test_app.py
git commit -m "feat: insert random event role variables"
```

### Task 3: Full regression and deployment

**Files:**
- Modify: no additional product files expected
- Test: all `tests/`

**Interfaces:**
- Consumes: the two completed slices.
- Produces: a tested and deployed role-variable feature.

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/python -m pytest`

Expected: exit code 0.

- [ ] **Step 2: Check the working tree**

Run: `git diff --check && git status --short`

Expected: no unexpected tracked changes.

- [ ] **Step 3: Deploy the committed release and check service health**

Run the project deployment script against the committed archive, then verify:

```bash
systemctl is-active dzmm-core dzmm-admin-web dzmm-browser-worker
```

Expected: all three services report `active`.
