# Command Template Modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move command reply-template editing from the command-library cards into a save-and-close modal.

**Architecture:** Keep the existing `/api/game/command-templates` request unchanged. Render a compact scenario preview and an edit trigger in each command card; store the selected command, scenario, template, and variables in the modal's DOM fields. The modal alone owns variable insertion and save/cancel/close behavior.

**Tech Stack:** FastAPI static HTML, vanilla JavaScript, CSS, pytest TestClient asset tests.

## Global Constraints

- Do not change reply-template data, validation, variables, API contracts, or group-command behavior.
- Save success must close the modal and reload the command-library preview.
- Escape, backdrop click, and cancel must close without saving.
- Use the existing protected `PATCH /api/game/command-templates` endpoint and payload.

---

### Task 1: Render and operate the command-template modal

**Files:**
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Modify: `tests/admin/test_app.py`

**Interfaces:**
- Consumes: command API template values `{scenario, label, template, variables}`.
- Produces: a modal with `#template-modal`, `#template-modal-input`, and a save control that sends `{command, scenario, template}` to `PATCH /api/game/command-templates`.

- [ ] **Step 1: Write the failing UI asset test**

```python
def test_command_library_uses_a_modal_template_editor(client):
    page = client.get("/")
    script = client.get("/static/admin.js")

    assert 'id="template-modal"' in page.text
    assert "data-edit-template" in script.text
    assert "closeTemplateModal" in script.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/admin/test_app.py::test_command_library_uses_a_modal_template_editor`

Expected: FAIL because the modal and modal controller do not exist.

- [ ] **Step 3: Implement the minimal modal UI**

```javascript
function closeTemplateModal() {
  templateModal.hidden = true;
}

function openTemplateModal(button) {
  templateModal.dataset.command = button.dataset.templateCommand;
  templateModal.dataset.scenario = button.dataset.templateScenario;
  templateInput.value = button.dataset.template;
  templateModal.hidden = false;
  templateInput.focus();
}
```

Replace inline textareas and save buttons with a preview plus
`data-edit-template` trigger. Put the textarea, variable buttons, cancel, and
save controls in `#template-modal`; its save handler performs the existing
request, calls `closeTemplateModal()`, reloads `commands`, and reports the
existing success message.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/admin/test_app.py::test_command_library_uses_a_modal_template_editor`

Expected: PASS.

- [ ] **Step 5: Run the affected suite and commit**

Run: `.venv/bin/python -m pytest -q tests/admin/test_app.py && git diff --check`

Expected: all admin tests pass and whitespace validation exits 0.
