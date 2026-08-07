# DZMM Unified Admin Management UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the desktop management UI with tabbed sections, fixed-height data regions, custom controls, and selectable 5/10/15/20/50 pagination.

**Architecture:** Retain FastAPI routes, DOM IDs used by event listeners, and every gameplay rule. Reorganize `index.html` into reusable management panes; extend `admin.js` with UI-only tabs and pagination; use `admin.css` as the shared component system.

**Tech Stack:** FastAPI static HTML, vanilla JavaScript, CSS custom properties, pytest.

## Global Constraints

- Desktop operation is primary at 1280px and above.
- Preserve API paths, request semantics, modal identifiers, data-action attributes, and game/economy behavior.
- Each page-size selector offers exactly 5, 10, 15, 20, and 50; its initial value is 20.
- Content regions that can grow use bounded desktop height with internal vertical scrolling.
- Buttons, search fields, selects, pagination, tabs, badges, and modal footers share a custom visual system.
- Purple remains the primary brand accent; passive refresh remains silent.

---

### Task 1: Define reusable management and list primitives

**Files:**
- Modify: `tests/admin/test_app.py`
- Modify: `src/dzmm_bot/admin/static/admin.css`

- [x] Write a failing test asserting `.management-tabs`, `.management-tab`, `.management-pane`, `.list-toolbar`, `.list-scroll`, `.page-size-select`, `.data-table`, `.status-badge`, `max-height`, and `overflow-y: auto` exist in the stylesheet.
- [x] Run `PYTHONPATH=src .worktrees/server-runtime/.venv/bin/pytest tests/admin/test_app.py::test_admin_styles_define_unified_management_components -q`; expect failure before the selectors exist.
- [x] Add the shared CSS primitives with custom select styling, keyboard focus, consistent buttons, badge colors, and a maximum 520px desktop list scroll region.
- [x] Re-run the focused test; expect pass.

### Task 2: Convert multi-section views into tabbed, bounded panes

**Files:**
- Modify: `tests/admin/test_app.py`
- Modify: `src/dzmm_bot/admin/templates/index.html`

- [x] Write a failing HTML test asserting `data-management-tabs="events"`, `data-management-tab="today"`, `data-management-pane="scenes"`, `class="list-scroll"`, and `class="list-toolbar"` exist.
- [x] Run `PYTHONPATH=src .worktrees/server-runtime/.venv/bin/pytest tests/admin/test_app.py::test_admin_groups_management_content_into_tabs_and_bounded_lists -q`; expect failure before markup is reorganized.
- [x] Preserve all existing element IDs and arrange views as: settings (经济 / 活跃度与收益); events (今日场次 / 场景库 / 事件规则); hide-and-seek (地点库 / 游戏规则); memory assessment (单人规则 / 对战规则); undercover (当前对局 / 游戏规则); organization (职位 / 部门 / 晋升审批 / 部门审批); shop (商品列表 / 上架商品); admins (管理员列表 / 新增管理员). Give commands and employees one toolbar/list pane each. Wrap every persistent list in `.list-scroll` and add a `.list-toolbar`.
- [x] Re-run the focused test; expect pass.

### Task 3: Implement tabs and uniform pagination controls

**Files:**
- Modify: `tests/admin/test_app.py`
- Modify: `src/dzmm_bot/admin/static/admin.js`

- [x] Write a failing script test asserting `function initializeManagementTabs()`, `function renderPageSizeControl(`, `const pageSizeOptions = [5, 10, 15, 20, 50]`, and `function renderLocalPagination(` occur in the script.
- [x] Run `PYTHONPATH=src .worktrees/server-runtime/.venv/bin/pytest tests/admin/test_app.py::test_admin_script_supports_tabs_and_configurable_page_sizes -q`; expect failure before controller code exists.
- [x] Implement tab state preservation, per-list page-size state, existing paginated loaders using selected page size, and local pagination for finite command/admin/today-event arrays. Do not alter routes or mutations.
- [x] Re-run the focused test; expect pass.

### Task 4: Add filter toolbars and compact status indicators

**Files:**
- Modify: `tests/admin/test_app.py`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`

- [x] Write a failing HTML test asserting `data-list-filter="commands"`, `data-list-filter="employees"`, `data-list-filter="random-event-scenes"`, and `data-list-page-size="shop"` exist.
- [x] Run `PYTHONPATH=src .worktrees/server-runtime/.venv/bin/pytest tests/admin/test_app.py::test_admin_management_lists_expose_consistent_toolbar_controls -q`; expect failure before toolbar metadata exists.
- [x] Add client-side search for list text, filter loaded API pages or finite arrays appropriately, and render existing state text as `.status-badge` while retaining every action data attribute.
- [x] Re-run the focused test; expect pass.

### Task 5: Verify and commit

**Files:**
- Modify: `docs/superpowers/plans/2026-08-08-admin-management-ui.md`
- Verify: `src/dzmm_bot/admin/templates/index.html`
- Verify: `src/dzmm_bot/admin/static/admin.css`
- Verify: `src/dzmm_bot/admin/static/admin.js`
- Verify: `tests/admin/test_app.py`

- [x] Run JavaScript parsing, the admin test file, and `git diff --check`; expect all checks pass.
- [ ] Run `PYTHONPATH=src .worktrees/server-runtime/.venv/bin/pytest -q`; expect all tests pass with known skips unchanged.
- [ ] Inspect at 1440px: tabs show active state, long lists scroll internally, selectors are custom, overview has no layout shift, and console has no errors.
- [ ] Update completed checkboxes and commit with `feat: unify admin management ui`.

## Self-Review

- All multi-section management views receive tabs; overview remains a dashboard by design.
- Persistent lists receive bounded scrolling, a standardized toolbar, and exactly five page-size options.
- Backend behavior, APIs, games, economy, permissions, modal IDs, and mutation anchors stay unchanged.
