# Random Event Two-Stage Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split random-event sign-up and role-play copy, choose a formal opening when an event fills, and enforce the approved observer speech rule.

**Architecture:** Scene records gain a sign-up text and child formal-opening rows. Event records retain a frozen selected formal opening so the lifecycle can send the sign-up message at creation and the selected role-play opening at full capacity. The message service asks the repository whether a normal message should count, be ignored, or trigger an observer warning.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy, Alembic, pytest, vanilla JavaScript.

## Global Constraints

- All date and time behavior stays in Beijing time.
- A group has at most one joinable random event; `/加入 角色` remains the common game entrypoint.
- A scene requires one sign-up announcement and at least one formal role-play opening.
- Existing `opening_text` values migrate to the sign-up announcement and receive one equivalent formal opening.
- During an in-progress random event, non-participant non-command messages are valid only when their whitespace-stripped content is fully wrapped by matching `（…）` or `(…)` and contains non-whitespace content.

---

### Task 1: Persist split scene copy and frozen event opening

**Files:**
- Modify: `src/dzmm_bot/core/schema.py:140-207`
- Create: `migrations/versions/20260806_09_random_event_scene_openings.py`
- Modify: `src/dzmm_bot/core/repository.py:740-1000`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Consumes: `Repository.create_random_event_scene(name, signup_text, openings, reward, target_rounds, seats)`.
- Produces: scene dictionaries with `signup_text: str` and `openings: list[str]`; event records with `formal_opening_text: str | None`.

- [ ] **Step 1: Write the failing repository tests**

```python
def test_full_random_event_freezes_and_sends_a_formal_opening(repository, session_factory):
    repository.create_random_event_scene(
        "茶水间", "茶水间事件来啦，快报名吧。", ["咖啡洒了一桌。"], 3, 1,
        [("主持", 1), ("员工", 1)],
    )
    # Create the due event and join both seats.
    assert repository.join_random_event("u2", "员工", now) == "started"
    with session_factory() as session:
        event = session.scalar(select(RandomEventRecord))
        outbound = session.scalar(select(OutboundRecord).order_by(OutboundRecord.created_at.desc()))
    assert event.formal_opening_text == "咖啡洒了一桌。"
    assert outbound.text.endswith("咖啡洒了一桌。")
```

- [ ] **Step 2: Run the focused test to verify RED**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py -k formal_opening -v`

Expected: FAIL because the new scene arguments and frozen formal opening are absent.

- [ ] **Step 3: Implement the migration and repository changes**

```python
op.alter_column("random_event_scenes", "opening_text", new_column_name="signup_text")
op.create_table(
    "random_event_scene_openings",
    sa.Column("id", uuid_type, primary_key=True),
    sa.Column("scene_id", uuid_type, sa.ForeignKey("random_event_scenes.id"), nullable=False),
    sa.Column("content", sa.Text(), nullable=False),
)
op.add_column("random_events", sa.Column("formal_opening_text", sa.Text(), nullable=True))
op.execute("UPDATE random_events SET formal_opening_text = opening_text")
```

Add the matching schema records. Replace repository scene creation, updating, and serialization with the split fields. At event creation, enqueue `signup_text`, choose one opening once, and store it as `formal_opening_text`. At full capacity, enqueue the stored opening after the start notice.

- [ ] **Step 4: Run the focused test to verify GREEN**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py -k formal_opening -v`

Expected: PASS.

- [ ] **Step 5: Commit the persistence slice**

```bash
git add src/dzmm_bot/core/schema.py src/dzmm_bot/core/repository.py \
  migrations/versions/20260806_09_random_event_scene_openings.py tests/core/test_repository.py
git commit -m "feat: split random event scene copy"
```

### Task 2: Expose split scene copy through core and management APIs

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py:186-220`
- Modify: `src/dzmm_bot/core/app.py:382-444,672-682`
- Modify: `src/dzmm_bot/admin/core_client.py:44-58,154-188`
- Modify: `src/dzmm_bot/admin/app.py:472-532`
- Test: `tests/core/test_app.py`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Consumes: JSON scene body `{"name", "signup_text", "openings", "reward", "target_rounds", "seats"}`.
- Produces: the same split fields from core and relay endpoints, with existing idempotency and version headers unchanged.

- [ ] **Step 1: Write failing API tests**

```python
def test_random_event_scene_api_requires_an_opening(client, headers):
    response = client.post("/internal/game/random-events/scenes", headers=headers, json={
        "name": "茶水间", "signup_text": "来报名", "openings": [],
        "reward": 1, "target_rounds": 1, "seats": [{"role": "主持", "capacity": 1}],
    })
    assert response.status_code == 422

def test_random_event_scene_api_returns_split_copy(client, headers):
    # Create a valid scene and assert its list response preserves both fields.
    assert response.json()["signup_text"] == "来报名"
    assert response.json()["openings"] == ["正式开场"]
```

- [ ] **Step 2: Run the API tests to verify RED**

Run: `.venv/bin/python -m pytest tests/core/test_app.py tests/admin/test_app.py -k random_event_scene -v`

Expected: FAIL for missing request/response fields.

- [ ] **Step 3: Implement request/response and relay changes**

```python
class RandomEventSceneResponse(ApiModel):
    signup_text: str
    openings: list[str]

class CreateRandomEventSceneRequest(ApiModel):
    signup_text: str = Field(min_length=1, max_length=2000)
    openings: list[str] = Field(min_length=1, max_length=20)
```

Reject blank opening entries before invoking the repository. Route both fields through the core and admin client. Do not alter unrelated management endpoints.

- [ ] **Step 4: Run the API tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/core/test_app.py tests/admin/test_app.py -k random_event_scene -v`

Expected: PASS.

- [ ] **Step 5: Commit the API slice**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py \
  src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py \
  tests/core/test_app.py tests/admin/test_app.py
git commit -m "feat: expose random event scene openings"
```

### Task 3: Enforce active-event observer speech rules

**Files:**
- Modify: `src/dzmm_bot/core/repository.py:850-910`
- Modify: `src/dzmm_bot/core/service.py:30-55`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_service.py`

**Interfaces:**
- Consumes: `Repository.classify_random_event_message(platform_id, content) -> Literal["none", "participant", "observer_valid", "observer_invalid"]`.
- Produces: one fixed warning outbound for invalid observer speech; only `participant` increments a role-play round.

- [ ] **Step 1: Write failing message-classification tests**

```python
def test_in_progress_event_allows_parenthesized_observer_message(repository):
    assert repository.classify_random_event_message(
        "observer", " （ 你好，你们在干什么 ） "
    ) == "observer_valid"

def test_in_progress_event_warns_unwrapped_observer_message(repository):
    assert repository.classify_random_event_message(
        "observer", "你好，你们在干什么"
    ) == "observer_invalid"
```

- [ ] **Step 2: Run the focused tests to verify RED**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py tests/core/test_service.py -k observer -v`

Expected: FAIL because the classifier is absent.

- [ ] **Step 3: Implement the classifier and service routing**

```python
def _is_parenthesized_observer_message(content: str) -> bool:
    compact = "".join(content.split())
    return (
        len(compact) >= 3
        and (compact[0], compact[-1]) in {("（", "）"), ("(", ")")}
    )
```

Commands and blank messages classify as `none`. Valid observer messages are ignored. Invalid observer messages enqueue `当前随机事件进行中，旁观请用（内容）或 (内容) 的形式发言。`. Participant messages increment one round.

- [ ] **Step 4: Run the focused tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py tests/core/test_service.py -k observer -v`

Expected: PASS.

- [ ] **Step 5: Commit the message-rule slice**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/service.py \
  tests/core/test_repository.py tests/core/test_service.py
git commit -m "feat: guard random event observer messages"
```

### Task 4: Update the scene modal for two copy phases

**Files:**
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js:150-235,760-825`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Consumes: scene objects containing `signup_text` and `openings`.
- Produces: one sign-up announcement textarea and repeatable formal-opening textarea rows; browser submissions contain the split fields.

- [ ] **Step 1: Write failing UI tests**

```python
def test_random_event_scene_modal_uses_split_copy_fields(client, headers):
    page = client.get("/", headers=headers).text
    assert 'id="random-event-scene-signup"' in page
    assert 'id="random-event-scene-openings"' in page

def test_random_event_scene_script_submits_openings_list():
    script = Path("src/dzmm_bot/admin/static/admin.js").read_text()
    assert "signup_text: signupText" in script
    assert "openings" in script
```

- [ ] **Step 2: Run the UI tests to verify RED**

Run: `.venv/bin/python -m pytest tests/admin/test_app.py -k random_event_scene -v`

Expected: FAIL because the old modal only exposes `opening_text`.

- [ ] **Step 3: Implement the modal controls and rendering**

```javascript
function renderRandomEventSceneOpening(value = "") {
  const row = document.createElement("div");
  row.className = "scene-opening-row";
  row.innerHTML = '<textarea data-random-event-formal-opening></textarea><button data-remove-random-event-opening type="button">删除</button>';
  row.querySelector("textarea").value = value;
  randomEventSceneOpenings.append(row);
}
```

Use existing `runMutation`. Prevent submission unless the name, sign-up announcement, one valid seat, and one non-blank formal opening are set. Render the sign-up announcement and formal-opening count in the list; keep all editors inside the modal.

- [ ] **Step 4: Run the UI tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/admin/test_app.py -k random_event_scene -v`

Expected: PASS.

- [ ] **Step 5: Commit the management UI slice**

```bash
git add src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js \
  src/dzmm_bot/admin/static/admin.css tests/admin/test_app.py
git commit -m "feat: edit random event copy phases"
```

### Task 5: Full regression and migration verification

**Files:**
- Modify: no additional product files expected
- Test: all `tests/`

**Interfaces:**
- Consumes: all previous slices.
- Produces: a migration-safe tested feature ready for deployment.

- [ ] **Step 1: Run the complete suite**

Run: `.venv/bin/python -m pytest`

Expected: exit code 0 with no failures.

- [ ] **Step 2: Check migration rendering and diff integrity**

Run: `.venv/bin/python -m alembic upgrade head --sql >/dev/null && git diff --check`

Expected: exit code 0.

- [ ] **Step 3: Verify the approved requirements**

Confirm tests and source cover per-scene sign-up messages, multiple formal openings, frozen selection, common join semantics, observer brackets, and modal validation.

