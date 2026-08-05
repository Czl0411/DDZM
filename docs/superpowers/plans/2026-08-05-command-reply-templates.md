# Command Reply Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let administrators edit every built-in group-command reply with safe, scenario-specific dynamic variables, including a new `/帮助` command.

**Architecture:** A compact reply-template catalog defines scenarios, default text, labels, and allowed variables. The repository persists catalog entries and administrator edits; the command handler selects a scenario after completing its existing business action and renders the stored template. Core exposes template data to the authenticated admin relay, whose existing command page renders editable scenario cards with variable insertion controls.

**Tech Stack:** Python 3.12, SQLAlchemy 2, Alembic, FastAPI, Pydantic 2, vanilla JavaScript, pytest.

## Global Constraints

- Keep the six built-in command names and all existing gameplay rules unchanged.
- Add only `/帮助`; administrators cannot define arbitrary commands or executable expressions.
- Store and render dates in `Asia/Shanghai`.
- Permit only documented `{变量}` tokens for each command scenario; reject unknown tokens at save time.
- Seed missing defaults without overwriting an administrator edit.
- Keep the existing command enable/disable gate before any business action or reply.
- A malformed stored template must fall back to its default instead of preventing a valid action.
- Do not add a DOM or browser-platform fallback.

---

### Task 1: Define and persist reply-template catalog

**Files:**
- Create: `src/dzmm_bot/core/reply_templates.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Create: `migrations/versions/20260805_03_command_reply_templates.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces `TemplateDefinition(command, scenario, label, default, variables)` and `TEMPLATE_DEFINITIONS` for the 13 approved scenarios.
- Produces `validate_template(command, scenario, template) -> None`, raising `ValueError` for an unknown command/scenario, empty or over-2000-character text, or an unsupported token.
- Produces `list_reply_templates(command)`, `get_reply_template(command, scenario)`, and `set_reply_template(command, scenario, template)` on `CoreRepository`.

- [ ] **Step 1: Write failing persistence and validation tests**

```python
def test_reply_template_defaults_seed_once_and_preserve_an_edit(repository):
    repository.ensure_reply_templates()
    repository.set_reply_template("/余额", "shown", "{昵称} 有 {余额} 币。")
    repository.ensure_reply_templates()
    assert repository.get_reply_template("/余额", "shown").template == "{昵称} 有 {余额} 币。"

def test_template_validation_rejects_a_variable_unavailable_to_its_scenario():
    with pytest.raises(ValueError, match="不支持"):
        validate_template("/余额", "shown", "{商店列表}")
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py -q`

Expected: FAIL because reply-template catalog and repository methods do not exist.

- [ ] **Step 3: Add catalog, schema, repository methods, and migration**

```python
class CommandReplyTemplateRecord(Base):
    __tablename__ = "command_reply_templates"
    __table_args__ = (UniqueConstraint("command", "scenario"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    command: Mapped[str] = mapped_column(String(32), nullable=False)
    scenario: Mapped[str] = mapped_column(String(64), nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(BeijingDateTime, default=beijing_now)
    updated_at: Mapped[datetime] = mapped_column(BeijingDateTime, default=beijing_now, onupdate=beijing_now)
```

Implement all defaults and allowed-variable tuples from the approved specification; add `/帮助` to `_COMMAND_DEFINITIONS`; call `ensure_reply_templates()` from command-definition initialization; use conflict-do-nothing insertion for defaults. The Alembic upgrade creates the table, inserts `/帮助` only if absent, and inserts all defaults. Its downgrade drops only this table and removes `/帮助`.

- [ ] **Step 4: Run repository tests**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py tests/core/test_group_commands.py -q`

Expected: PASS, including repeated seeding preserving edits and existing command behavior.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/reply_templates.py src/dzmm_bot/core/schema.py src/dzmm_bot/core/repository.py migrations/versions/20260805_03_command_reply_templates.py tests/core/test_repository.py
git commit -m "feat: persist command reply templates"
```

### Task 2: Render scenario templates from command outcomes

**Files:**
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `tests/core/test_group_commands.py`

**Interfaces:**
- Consumes `CoreRepository.get_reply_template()` and the reply-template catalog.
- Produces `GroupCommandHandler.handle(message) -> str | None` replies rendered by `render_template(definition, template, values) -> str`.
- `/帮助` uses scenario `shown` and `{指令列表}` built from enabled command definitions.

- [ ] **Step 1: Write failing scenario-rendering tests**

```python
def test_custom_checkin_template_receives_current_balance_and_reward():
    service, repository, factory = _service()
    repository.set_reply_template("/打卡", "checked_in", "{昵称} 今日 +{打卡奖励}，余额 {余额}")
    _receive(service, "join", "platform-xiaoming", "/入职 小明", NOW)
    _receive(service, "checkin", "platform-xiaoming", "/打卡", NOW)
    assert _latest_reply(factory) == "小明 今日 +5，余额 5"

def test_help_lists_only_enabled_commands_and_uses_its_template():
    service, repository, factory = _service()
    repository.set_command_enabled("/打卡", False)
    repository.set_reply_template("/帮助", "shown", "可用：\n{指令列表}")
    _receive(service, "help", "platform-xiaoming", "/帮助", NOW)
    assert "/帮助" in _latest_reply(factory)
    assert "/打卡" not in _latest_reply(factory)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `.venv/bin/python -m pytest tests/core/test_group_commands.py -q`

Expected: FAIL because templates are not selected or rendered and `/帮助` is unknown.

- [ ] **Step 3: Implement minimal scenario selection and rendering**

```python
def _reply(self, command: str, scenario: str, **values: str | int) -> str:
    definition = template_definition(command, scenario)
    record = self._repository.get_reply_template(command, scenario)
    template = record.template if record is not None else definition.default
    try:
        return render_template(definition, template, values)
    except ValueError:
        return render_template(definition, definition.default, values)
```

Replace only literal reply returns with `_reply()` calls. Pass values from the already-computed employee, item, check-in, or Beijing receipt timestamp. Use `暂时空空如也。` for empty inventory and the current name/price/stock formatting for list variables. Do not change balance mutation, check-in uniqueness, or shop query behavior.

- [ ] **Step 4: Run command tests**

Run: `.venv/bin/python -m pytest tests/core/test_group_commands.py -q`

Expected: PASS for original flows plus custom rendering, fallback, `{日期}`, and `/帮助` filtering.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/commands.py tests/core/test_group_commands.py
git commit -m "feat: render group replies from templates"
```

### Task 3: Expose templates through protected Core and Admin APIs

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `tests/core/test_app.py`
- Modify: `tests/admin/test_app.py`

**Interfaces:**
- Produces `CommandTemplateResponse(scenario, label, template, variables)` nested in `CommandDefinitionResponse.templates`.
- Produces `SetCommandTemplateRequest(command, scenario, template)` and protected `PATCH /internal/game/command-templates`.
- Produces `PATCH /api/game/command-templates`, delegating to `AdminCorePort.set_game_command_template(command, scenario, template)`.

- [ ] **Step 1: Write failing protected API tests**

```python
def test_core_lists_templates_and_updates_a_valid_template(client, headers):
    commands = client.get("/internal/game/commands", headers=headers).json()
    assert commands[0]["templates"][0]["variables"]
    response = client.patch(
        "/internal/game/command-templates", headers=headers,
        json={"command": "/余额", "scenario": "shown", "template": "{昵称}：{余额}"},
    )
    assert response.json()["template"] == "{昵称}：{余额}"

def test_admin_relay_rejects_a_template_without_required_fields(client, headers):
    response = client.patch("/api/game/command-templates", headers=headers, json={"command": "/余额"})
    assert response.status_code == 422
```

- [ ] **Step 2: Run API tests and verify failure**

Run: `.venv/bin/python -m pytest tests/core/test_app.py tests/admin/test_app.py -q`

Expected: FAIL because template response models and update routes do not exist.

- [ ] **Step 3: Add models, Core route, and Admin relay**

```python
class CommandTemplateResponse(ApiModel):
    scenario: str
    label: str
    template: str
    variables: list[str]

class SetCommandTemplateRequest(ApiModel):
    command: str = Field(min_length=1, max_length=32)
    scenario: str = Field(min_length=1, max_length=64)
    template: str = Field(min_length=1, max_length=2000)
```

Have the Core route validate before persisting and return HTTP 422 on a validation failure. The command-list route obtains scenario labels and variable lists solely from the catalog, never from administrator-provided data. Extend the Admin fake Core with the same method and preserve the enable/disable endpoint.

- [ ] **Step 4: Run API tests**

Run: `.venv/bin/python -m pytest tests/core/test_app.py tests/admin/test_app.py -q`

Expected: PASS, including authentication, allowed updates, unknown-variable rejection, and relay validation.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py tests/core/test_app.py tests/admin/test_app.py
git commit -m "feat: manage reply templates through admin API"
```

### Task 4: Add command-template controls to the Admin page

**Files:**
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `tests/admin/test_app.py`

**Interfaces:**
- Consumes nested `templates` from `GET /api/game/commands` and saves through `PATCH /api/game/command-templates`.
- Produces per-scenario cards with textarea, allowed-variable buttons, and a save button without changing the command toggle.

- [ ] **Step 1: Write failing page and asset contract tests**

```python
def test_command_library_includes_template_editor_controls(client):
    page = client.get("/")
    script = client.get("/static/admin.js")
    assert 'id="command-list"' in page.text
    assert "command-templates" in script.text
    assert "insert-template-variable" in script.text
```

- [ ] **Step 2: Run the page test and verify failure**

Run: `.venv/bin/python -m pytest tests/admin/test_app.py::test_command_library_includes_template_editor_controls -q`

Expected: FAIL because current JavaScript has no template editor behavior.

- [ ] **Step 3: Render cards, insert variables at the caret, and save**

```javascript
function insertTemplateVariable(textarea, variable) {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  textarea.value = `${textarea.value.slice(0, start)}${variable}${textarea.value.slice(end)}`;
  textarea.focus();
  textarea.selectionStart = textarea.selectionEnd = start + variable.length;
}
```

Render server fields only through `escapeHtml()`. Each variable button uses `data-variable`; each save button carries `data-template-command` and `data-template-scenario`. The delegated command-list handler inserts variables or sends exactly `{command, scenario, template}`, then reloads this view. Add compact styles for multiline editor cards, variable pills, and save controls while preserving the existing navigation and responsive layout.

- [ ] **Step 4: Run Admin tests**

Run: `.venv/bin/python -m pytest tests/admin/test_app.py -q && git diff --check`

Expected: PASS and no whitespace errors.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css src/dzmm_bot/admin/templates/index.html tests/admin/test_app.py
git commit -m "feat: edit reply templates in command library"
```

### Task 5: Verify migration, full suite, and deploy

**Files:**
- Modify only files required to correct a task-owned verification defect.

**Interfaces:**
- Consumes the migration and Core/Admin changes.
- Produces deployed Core/Admin services with default templates seeded and edits preserved.

- [ ] **Step 1: Verify the migration chain**

Run: `DATABASE_URL=sqlite+pysqlite:///:memory: .venv/bin/alembic upgrade head`

Expected: reaches `20260805_03` without error. If SQLite cannot execute the PostgreSQL migration dialect, run the project PostgreSQL deployment migration and record that limitation.

- [ ] **Step 2: Run the full suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all tests pass with no command, worker, socket, or Admin regression.

- [ ] **Step 3: Review final state**

Run: `git diff --check && git status --short`

Expected: only task-owned source changes are committed; preserve user-owned `docs/HANDOFF.md`.

- [ ] **Step 4: Deploy and validate one edit end to end**

Run the existing release deployment script, restart `dzmm-core` and `dzmm-admin-web`, and verify the Worker remains `ready`. In the Admin page change `/余额` → `shown` to `{昵称}：{余额} 摸鱼币`, save, invoke `/余额` once in the configured target group, and verify that exact reply. Keep that saved live template unless the user asks to restore the default.

- [ ] **Step 5: Confirm no uncommitted verification repair remains**

```bash
git status --short
```

Expected: no task-owned changes remain; do not create an empty commit.
