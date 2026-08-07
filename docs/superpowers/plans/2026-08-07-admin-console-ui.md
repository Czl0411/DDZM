# DZMM Desktop Admin Console UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing DZMM administrator portal into a desktop-first operational console with grouped navigation, consistent page context, readable data management, and standard feedback patterns.

**Architecture:** Retain all FastAPI routes, DOM IDs, modals, and loaders. Restructure only the static shell in `index.html`, add page metadata in `admin.js`, and update `admin.css`; no game or database behavior changes.

**Tech Stack:** FastAPI static HTML, vanilla JavaScript, CSS custom properties, pytest.

## Global Constraints

- Desktop-first for 1280px and above; small screens may stack but are not the primary target.
- Preserve every existing `id`, `data-view`, endpoint, modal, pagination element, and mutation behavior.
- Purple remains the only primary brand accent.
- Refresh polling remains silent; explicit user actions retain standard notifications.

---

### Task 1: Add a grouped desktop console shell

**Files:**
- Modify: `tests/admin/test_app.py`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.css`

**Interfaces:**
- Consumes: Existing `.nav-item[data-view]` controls and `#dashboard-title`.
- Produces: `#page-breadcrumb`, `#page-context`, `.nav-group`, `.side-nav-shell`, and `.sidebar-footer`.

- [x] Write a failing static asset test:

```python
def test_admin_uses_a_grouped_desktop_console_shell(client):
    page = client.get("/").text
    stylesheet = Path("src/dzmm_bot/admin/static/admin.css").read_text()

    assert 'id="page-breadcrumb"' in page
    assert 'id="page-context"' in page
    assert 'class="nav-group"' in page
    assert ".side-nav-shell" in stylesheet
    assert ".sidebar-footer" in stylesheet
```

- [x] Run `PYTHONPATH=src .worktrees/server-runtime/.venv/bin/pytest tests/admin/test_app.py::test_admin_uses_a_grouped_desktop_console_shell -q`; it failed before the shell existed.
- [x] Wrap the navigation in four labelled `.nav-group` elements: 运营概览, 游戏运营, 玩法与资源, 人员与系统. Add a sidebar footer showing “北京时间 · 配置实时生效”. Add `#page-breadcrumb` and `#page-context` in the header, preserving `#dashboard-title` and `#refresh`.
- [x] Add sticky desktop sidebar styles and validate the focused test passes.
- [ ] Commit after user review with the complete UI change set.

### Task 2: Synchronize page context with the selected view

**Files:**
- Modify: `tests/admin/test_app.py`
- Modify: `src/dzmm_bot/admin/static/admin.js`

**Interfaces:**
- Consumes: existing `loadGameView(view)` and values `overview`, `settings`, `events`, `hide-and-seek`, `memory-assessment`, `undercover`, `commands`, `organization`, `employees`, `shop`, `admins`.
- Produces: `setPageContext(view)` updates the breadcrumb, title, and description.

- [x] Write a failing test:

```python
def test_admin_script_maps_navigation_views_to_console_page_context():
    script = Path("src/dzmm_bot/admin/static/admin.js").read_text()

    assert "const pageContext" in script
    assert "function setPageContext(view)" in script
    assert 'undercover:' in script
    assert 'organization:' in script
```

- [x] Run `PYTHONPATH=src .worktrees/server-runtime/.venv/bin/pytest tests/admin/test_app.py::test_admin_script_maps_navigation_views_to_console_page_context -q`; it failed before page metadata existed.
- [x] Add this page metadata mechanism:

```js
const pageContext = {
  overview: {crumb: "运营概览", title: "机器人运行状态", description: "查看服务、浏览器和人工登录状态。"},
};

function setPageContext(view) {
  const context = pageContext[view] || pageContext.overview;
  document.querySelector("#page-breadcrumb").textContent = context.crumb;
  document.querySelector("#dashboard-title").textContent = context.title;
  document.querySelector("#page-context").textContent = context.description;
}
```

- [x] Call `setPageContext(view)` at the beginning of `loadGameView(view)` and set overview context after authentication.
- [x] Run the focused test; it passes. Commit after user review with the complete UI change set.

### Task 3: Establish reusable data and modal visual hierarchy

**Files:**
- Modify: `tests/admin/test_app.py`
- Modify: `src/dzmm_bot/admin/static/admin.css`

**Interfaces:**
- Consumes: `.panel`, `.status-grid`, `.settings-card`, `.data-list`, `.data-row`, `.pagination`, `.template-modal-card`, `.template-modal-actions`.
- Produces: consistent list rows, page context styling, clearer action hierarchy, and modal body/footer boundaries.

- [x] Write a failing test:

```python
def test_admin_styles_define_console_data_and_modal_patterns():
    stylesheet = Path("src/dzmm_bot/admin/static/admin.css").read_text()

    assert ".page-context" in stylesheet
    assert ".data-list > .data-row" in stylesheet
    assert ".template-modal-actions" in stylesheet
    assert "position: sticky" in stylesheet
```

- [x] Run `PYTHONPATH=src .worktrees/server-runtime/.venv/bin/pytest tests/admin/test_app.py::test_admin_styles_define_console_data_and_modal_patterns -q`; it failed before the list pattern existed.
- [x] Add restrained shell layers, compact action styles, scannable list-row alignment, stronger state tags, and a sticky modal action footer without altering the existing modal inputs or event listeners.
- [x] Run the focused test; it passes. Commit after user review with the complete UI change set.

### Task 4: Verify retained management behavior

**Files:**
- Modify: `tests/admin/test_app.py`
- Verify: `src/dzmm_bot/admin/templates/index.html`
- Verify: `src/dzmm_bot/admin/static/admin.css`
- Verify: `src/dzmm_bot/admin/static/admin.js`

- [x] Extend the shell test to retain `#employee-pagination`, `#random-event-settings-modal`, `#notification-region`, and `data-view="undercover"`.
- [x] Run `PYTHONPATH=src .worktrees/server-runtime/.venv/bin/pytest tests/admin/test_app.py -q`; 78 tests pass.
- [x] Run `PYTHONPATH=src .worktrees/server-runtime/.venv/bin/pytest -q`; 361 tests pass and 5 are skipped.
- [x] Inspect the static admin page at a 1440px viewport: its HTML, CSS and JavaScript load without browser console errors. Authenticated controls need the normal local stack or the deployed environment for a complete visual inspection.
- [ ] Commit after user review with the complete UI change set.

## Self-Review

- Tasks 1–3 cover the confirmed desktop shell, grouped navigation, page context, list management, action hierarchy, and modal behavior.
- Task 4 preserves all existing functional anchors, pagination, notifications, and scrolling behavior.
- `setPageContext(view)` consumes only existing view keys, avoiding backend changes.
