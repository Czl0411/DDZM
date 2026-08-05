# 玩法运营配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an operator-friendly global economy configuration page for currency name, new-employee balance, and daily check-in reward.

**Architecture:** Persist one `game_settings` row with defaults. Commands read it for new `/入职`, successful `/打卡`, and generated currency wording. The migration upgrades only unchanged old default templates to use `{货币}` and leaves administrator-authored text untouched. Core and Admin expose authenticated read/update APIs; Admin renders settings separately from the template editor.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, Alembic, vanilla JavaScript/CSS, pytest.

## Global Constraints

- One global configuration applies to the configured single group.
- Defaults are `摸鱼币`, initial balance `0`, check-in reward `5`.
- Integer values are `0..999`; currency name is trimmed to `1..12` characters.
- Reset remains fixed at Beijing time 00:00.
- New values apply only to future successful `/入职` and `/打卡`; existing balances do not change.
- Preserve untracked `docs/HANDOFF.md`.

### Task 1: Persist and consume economy settings

**Files:**
- Create: `migrations/versions/20260805_04_game_settings.py`
- Modify: `src/dzmm_bot/core/schema.py`, `src/dzmm_bot/core/repository.py`, `src/dzmm_bot/core/commands.py`
- Test: `tests/core/test_repository.py`, `tests/core/test_commands.py`

**Interfaces:** `get_game_settings()` returns the singleton; `set_game_settings(currency_name, onboarding_bonus, checkin_reward)` validates and stores it. `create_user` receives an initial balance and `check_in` receives a reward.

- [ ] **Step 1: Write failing tests**

```python
def test_game_settings_default_to_initial_economy(repository):
    settings = repository.get_game_settings()
    assert (settings.currency_name, settings.onboarding_bonus, settings.checkin_reward) == ("摸鱼币", 0, 5)

def test_updated_settings_apply_to_future_join_and_checkin(handler, repository):
    repository.set_game_settings("工分", 3, 7)
    assert "3" in handler.handle(join_message("u-1", "/入职 小明"))
    assert "7" in handler.handle(message("u-1", "/打卡"))
```

- [ ] **Step 2: Run red tests**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py tests/core/test_commands.py -q`

Expected: settings storage and reward parameters are missing.

- [ ] **Step 3: Implement migration and repository**

```python
class GameSettingsRecord(Base):
    __tablename__ = "game_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    currency_name: Mapped[str] = mapped_column(String(12), nullable=False)
    onboarding_bonus: Mapped[int] = mapped_column(Integer, nullable=False)
    checkin_reward: Mapped[int] = mapped_column(Integer, nullable=False)
```

Use defaults when the row does not exist. Validate all values in the repository. Make `GroupCommandHandler` pass configured rewards into repository writes and currency into generated context. Add `{货币}` to applicable template definitions and migrate unchanged known default templates from `摸鱼币` to `{货币}` without changing any other saved template.

- [ ] **Step 4: Run green tests**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py tests/core/test_commands.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/20260805_04_game_settings.py src/dzmm_bot/core/schema.py src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py tests/core
git commit -m "feat: add configurable game economy"
```

### Task 2: Expose settings through Core and Admin APIs

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`, `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/admin/core_client.py`, `src/dzmm_bot/admin/app.py`
- Test: `tests/core/test_app.py`, `tests/admin/test_app.py`

**Interfaces:** `GET` and `PATCH /internal/game/settings`; `GET` and `PATCH /api/game/settings`; request fields are `currency_name`, `onboarding_bonus`, `checkin_reward`.

- [ ] **Step 1: Write failing tests**

```python
def test_game_settings_can_be_read_and_updated(client, headers):
    assert client.get("/internal/game/settings", headers=headers).json()["checkin_reward"] == 5
    response = client.patch("/internal/game/settings", headers=headers, json={"currency_name": "工分", "onboarding_bonus": 3, "checkin_reward": 7})
    assert response.json()["currency_name"] == "工分"

def test_admin_game_settings_requires_admin_token(client):
    assert client.get("/api/game/settings").status_code == 401
```

- [ ] **Step 2: Run red tests**

Run: `.venv/bin/python -m pytest tests/core/test_app.py tests/admin/test_app.py -q`

Expected: settings routes are absent.

- [ ] **Step 3: Implement models and routes**

```python
class GameSettingsResponse(ApiModel):
    currency_name: str
    onboarding_bonus: int
    checkin_reward: int
    reset_time_label: str = "北京时间 00:00"
```

Core turns repository validation failures into HTTP 422. Admin CoreClient proxies the endpoints; Admin keeps its existing token authorization.

- [ ] **Step 4: Run green tests**

Run: `.venv/bin/python -m pytest tests/core/test_app.py tests/admin/test_app.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py tests/core/test_app.py tests/admin/test_app.py
git commit -m "feat: expose game settings management APIs"
```

### Task 3: Build the settings navigation and modal

**Files:**
- Modify: `src/dzmm_bot/admin/templates/index.html`, `src/dzmm_bot/admin/static/admin.js`, `src/dzmm_bot/admin/static/admin.css`
- Test: `tests/admin/test_app.py`, `tests/admin/test_package_data.py`

**Interfaces:** adds `data-view="settings"`, `#settings-view`, and `#settings-modal`; UI reads and saves `/api/game/settings`.

- [ ] **Step 1: Write failing asset tests**

```python
def test_admin_page_exposes_game_settings_navigation_and_modal(client):
    page = client.get("/").text
    assert 'data-view="settings"' in page
    assert 'id="settings-modal"' in page

def test_admin_script_requests_game_settings():
    assert '"/api/game/settings"' in (ADMIN_ROOT / "static" / "admin.js").read_text()
```

- [ ] **Step 2: Run red tests**

Run: `.venv/bin/python -m pytest tests/admin/test_app.py tests/admin/test_package_data.py -q`

Expected: settings UI is absent.

- [ ] **Step 3: Implement an operator-first view**

Render a readable economy card with current values and scope hints. Keep the main view non-editable; use the modal for labelled fields, constraints, Cancel and Save. Reuse the existing result status area and do not alter the template modal.

- [ ] **Step 4: Run green tests**

Run: `.venv/bin/python -m pytest tests/admin/test_app.py tests/admin/test_package_data.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/admin
git commit -m "feat: add operator game settings view"
```

### Task 4: Verify and deploy

- [ ] **Step 1: Run full verification**

Run: `.venv/bin/python -m pytest -q && git diff --check`

Expected: full suite passes without whitespace errors.

- [ ] **Step 2: Deploy**

Stage the release, run the existing deployment script with its release directory, then restart `dzmm-core`, `dzmm-admin-web`, and `dzmm-browser-worker` after migration succeeds.

- [ ] **Step 3: Verify production**

Confirm the three services are active, Alembic reaches `20260805_04`, and the Admin API returns the configured values. Ask the user to validate one future `/入职` and `/打卡` with non-default values.
