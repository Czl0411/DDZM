# 摸鱼躲猫猫（单人模式）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在群机器人和管理端交付可配置的单人“摸鱼躲猫猫”玩法：玩家选择七个地点之一，系统一次巡查三个地点后结算。

**Architecture:** 玩法状态、每日次数、地点快照和经济流水由 `CoreRepository` 在同一事务中维护；命令层只负责解析 `/摸鱼躲猫猫` 子命令并渲染现有可编辑模板。核心 API 暴露设置与独立地点库，管理端沿用现有配置版本、幂等键、分页、禁用提交和标准通知交互。

**Tech Stack:** Python 3.13、FastAPI、SQLAlchemy、SQLite/PostgreSQL、原生 HTML/CSS/JavaScript、pytest。

## Global Constraints

- 业务日期、超时判断与账本时间统一使用 `Asia/Shanghai`（北京时间）。
- 每人每日默认最多两局；`/摸鱼躲猫猫 发起游戏` 即扣默认 1 摸鱼币并计数，余额允许变负。
- 玩家选址后，系统从冻结的七个地点中无重复巡查三个；命中失败，未命中发默认 3 摸鱼币。
- 未选址等待默认两分钟自动取消，退款并返还次数；同一玩家仅允许一局待选址游戏。
- 随机事件状态为 `signup` 或 `in_progress` 时，禁止发起躲猫猫；不同玩家其他时间可以并行游玩。
- 独立躲猫猫地点库至少启用七条才能开局，首次初始化预置十个公司地点；本局地点快照不受之后编辑、停用或删除影响。
- 所有管理端写操作沿用 `If-Match` 配置版本和 `Idempotency-Key`；列表必须分页、提交中按钮必须禁用、提示使用既有标准通知。

---

### Task 1: 持久化玩法状态、地点库与原子结算

**Files:**
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces `HideAndSeekSettings`, `HideAndSeekScene` 与 `HideAndSeekGameResult` 只读数据类。
- Produces repository methods：
  - `get_hide_and_seek_settings() -> HideAndSeekSettings`
  - `set_hide_and_seek_settings(enabled: bool, entry_fee: int, win_reward: int, daily_limit: int, selection_timeout_minutes: int) -> HideAndSeekSettings`
  - `list_hide_and_seek_scenes_page(page: int, page_size: int) -> tuple[list[HideAndSeekScene], int]`
  - `create_hide_and_seek_scene(name: str) -> HideAndSeekScene`
  - `update_hide_and_seek_scene(scene_id: UUID, name: str, enabled: bool) -> HideAndSeekScene`
  - `delete_hide_and_seek_scene(scene_id: UUID) -> bool`
  - `start_hide_and_seek(platform_id: str, now: datetime) -> HideAndSeekGameResult`
  - `choose_hide_and_seek(platform_id: str, scene_number: int, now: datetime) -> HideAndSeekGameResult`
  - `expire_hide_and_seek_games(now: datetime) -> list[HideAndSeekGameResult]`
- `HideAndSeekGameResult.status` uses `started`, `won`, `found`, `cancelled`, `not_joined`, `random_event_active`, `disabled`, `daily_limit`, `already_active`, `not_enough_scenes`, `no_active_game`, `invalid_scene`, or `expired`.

- [ ] **Step 1: Write failing repository tests for default initialization and scene validation**

```python
def test_hide_and_seek_defaults_seed_ten_company_scenes(repository):
    settings = repository.get_hide_and_seek_settings()
    scenes, total = repository.list_hide_and_seek_scenes_page(1, 20)

    assert (settings.enabled, settings.entry_fee, settings.win_reward, settings.daily_limit) == (True, 1, 3, 2)
    assert total == 10
    assert {scene.name for scene in scenes} >= {"公司前台", "茶水间", "公司天台"}


def test_hide_and_seek_scene_name_must_be_unique(repository):
    repository.get_hide_and_seek_settings()
    with pytest.raises(ValueError, match="地点名称已存在"):
        repository.create_hide_and_seek_scene("茶水间")
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py -k hide_and_seek_defaults -v`

Expected: FAIL because hide-and-seek repository methods and records do not exist.

- [ ] **Step 3: Add the minimal database records and default bootstrap**

Add `HideAndSeekSettingsRecord`, `HideAndSeekSceneRecord`, `HideAndSeekDailyPlayRecord`, and `HideAndSeekGameRecord` to `schema.py`. Use a partial unique index on `HideAndSeekGameRecord.user_id` for `state == "selecting"`; persist candidate names as JSON, selected number, patrol numbers, created/deadline/finished timestamps, and frozen entry/reward values. In `repository.py`, initialize settings and the ten agreed company locations only when the singleton settings record is first created; validate trimmed unique names and page queries with `order_by(name)`.

- [ ] **Step 4: Run the initialization and scene tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py -k 'hide_and_seek_defaults or hide_and_seek_scene_name' -v`

Expected: PASS.

- [ ] **Step 5: Write failing repository tests for start, win, hit, limit, random-event lock, and timeout refund**

```python
def test_hide_and_seek_charges_then_rewards_unpatrolled_scene(repository, monkeypatch):
    user, _ = repository.create_user("u1", "小明", NOW, 0)
    monkeypatch.setattr("dzmm_bot.core.repository.randbelow", lambda _: 0)

    started = repository.start_hide_and_seek("u1", NOW)
    finished = repository.choose_hide_and_seek("u1", 7, NOW)

    assert started.status == "started"
    assert len(started.candidates) == 7
    assert finished.status == "won"
    assert repository.find_user("u1").balance == 2


def test_hide_and_seek_timeout_refunds_and_returns_daily_play(repository):
    repository.create_user("u1", "小明", NOW, 0)
    repository.start_hide_and_seek("u1", NOW)

    cancelled = repository.expire_hide_and_seek_games(NOW + timedelta(minutes=2))
    restarted = repository.start_hide_and_seek("u1", NOW + timedelta(minutes=2, seconds=1))

    assert [game.status for game in cancelled] == ["cancelled"]
    assert repository.find_user("u1").balance == -1
    assert restarted.status == "started"
```

Also cover an active `RandomEventRecord` in both `signup` and `in_progress` states returning `random_event_active`; a third same-day start returning `daily_limit`; a second selecting game returning `already_active`; and a `scene_number` outside `1..7` returning `invalid_scene` without new ledger entries.

- [ ] **Step 6: Run the new lifecycle tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py -k hide_and_seek -v`

Expected: FAIL because lifecycle methods do not yet charge, sample, settle, or expire games.

- [ ] **Step 7: Implement minimal transactional lifecycle methods**

Use `with self.transaction()` and row locks for the user, any selecting game, daily play record, and active random event. `start_hide_and_seek` must:

```python
candidates = _sample_distinct([scene.name for scene in enabled_scenes], 7)
self._apply_balance_change(user, -settings.entry_fee, "hide_and_seek_entry", now)
daily.count += 1
session.add(HideAndSeekGameRecord(..., state="selecting", candidates=candidates,
    choice_deadline=now + timedelta(minutes=settings.selection_timeout_minutes),
    entry_fee=settings.entry_fee, win_reward=settings.win_reward))
```

`choose_hide_and_seek` samples exactly three unique indices, stores them, changes state to `found` or `won`, and only calls `_apply_balance_change(user, game.win_reward, "hide_and_seek_win", now)` for a win. `expire_hide_and_seek_games` locks only overdue selecting records, marks each `cancelled`, applies a `hide_and_seek_refund` transaction, and decrements that user/day count exactly once. Task 2 integrates this method into the worker-polled daily jobs and emits the cancellation message.

- [ ] **Step 8: Run repository tests to verify lifecycle behavior passes**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py -k hide_and_seek -v`

Expected: PASS, including repeat expiration without duplicate refund or count return.

- [ ] **Step 9: Commit Task 1**

```bash
git add src/dzmm_bot/core/schema.py src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: persist solo hide and seek games"
```

### Task 2: 暴露群指令与可编辑回复模板

**Files:**
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/service.py`
- Test: `tests/core/test_group_commands.py`
- Test: `tests/core/test_service.py`

**Interfaces:**
- Adds the enabled command definition `/摸鱼躲猫猫` with description `发起单人躲猫猫小游戏`.
- Adds configurable reply template scenarios `usage`, `not_joined`, `blocked`, `disabled`, `daily_limit`, `already_active`, `not_enough_scenes`, `started`, `invalid_scene`, `found`, and `won`.
- `GroupCommandHandler.handle()` recognizes:
  - `/摸鱼躲猫猫 发起游戏`
  - `/摸鱼躲猫猫 躲 <1-7>`

- [ ] **Step 1: Write failing group-command tests for start and selected-scene settlement**

```python
def test_hide_and_seek_command_lists_seven_places_and_patrols_three(service, repository, factory, monkeypatch):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    _receive(service, "join", "u1", "/入职 小明", now)
    monkeypatch.setattr("dzmm_bot.core.repository.randbelow", lambda _: 0)

    _receive(service, "start", "u1", "/摸鱼躲猫猫 发起游戏", now)
    started_reply = _latest_reply(factory)
    _receive(service, "choose", "u1", "/摸鱼躲猫猫 躲 7", now)

    assert "1（" in started_reply and "7（" in started_reply
    assert "【系统巡查】巡查" in _latest_reply(factory)
    assert "躲藏成功" in _latest_reply(factory)
```

Add a test that an active random-event signup causes a reply explaining that躲猫猫 cannot start; a malformed command returns the usage reply; and `/摸鱼躲猫猫` messages do not trigger `record_random_event_round` or the observer-format warning because they start with `/`.

- [ ] **Step 2: Run the command tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_group_commands.py -k hide_and_seek -v`

Expected: FAIL because the command is not registered or parsed.

- [ ] **Step 3: Add command parsing, definition, and templates**

Add `/摸鱼躲猫猫` to `_COMMANDS` and `_COMMAND_DEFINITIONS`. Add defaults with only the data required by each response. The `started` template must receive `{昵称}`, `{场景列表}`, `{选择超时分钟}` and `{货币}`; format the frozen candidates as `1（地点）` through `7（地点）`. The final templates must receive `{巡查地点}` and, on a win, `{奖励}` / `{余额}`.

Implement `_hide_and_seek()` in `GroupCommandHandler`; convert only a clean decimal third token to an integer and map `HideAndSeekGameResult.status` to its matching reply scenario. Keep all direct player replies routed through `_reply` so operators can edit them in the command library.

- [ ] **Step 4: Run command and command-template tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_group_commands.py -k 'hide_and_seek or help' -v`

Expected: PASS; `/帮助` lists the enabled new command.

- [ ] **Step 5: Write a failing service test for the automatic cancellation outbound message**

```python
def test_daily_jobs_enqueue_one_hide_and_seek_cancellation_message(repository, factory):
    repository.create_user("u1", "小明", NOW, 0)
    repository.start_hide_and_seek("u1", NOW)

    repository.run_daily_jobs(NOW + timedelta(minutes=2))
    repository.run_daily_jobs(NOW + timedelta(minutes=3))

    with factory() as session:
        texts = list(session.scalars(select(OutboundRecord.text)))
    assert sum("躲猫猫" in text and "已取消" in text for text in texts) == 1
```

- [ ] **Step 6: Run the automatic-cancellation test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_service.py -k hide_and_seek_cancellation -v`

Expected: FAIL because no timeout message is enqueued yet.

- [ ] **Step 7: Enqueue the automatic cancellation copy once per cancelled game**

After `expire_hide_and_seek_games()` in `run_daily_jobs`, enqueue `【摸鱼躲猫猫】{display_name} 未在 2 分钟内选择地点，本局已取消，入场费和次数已返还。` for each newly cancelled game. Do not call this logic from inbound handling; worker polling already calls `run_daily_jobs` continuously.

- [ ] **Step 8: Run service tests to verify the cancellation message is idempotent**

Run: `.venv/bin/python -m pytest tests/core/test_service.py -k hide_and_seek_cancellation -v`

Expected: PASS.

- [ ] **Step 9: Commit Task 2**

```bash
git add src/dzmm_bot/core/commands.py src/dzmm_bot/core/reply_templates.py src/dzmm_bot/core/repository.py src/dzmm_bot/core/service.py tests/core/test_group_commands.py tests/core/test_service.py
git commit -m "feat: add hide and seek group command"
```

### Task 3: 核心 API 与管理端代理

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Test: `tests/core/test_app.py`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Core endpoints:
  - `GET/PATCH /internal/game/hide-and-seek/settings`
  - `GET/POST /internal/game/hide-and-seek/scenes`
  - `PUT/DELETE /internal/game/hide-and-seek/scenes/{scene_id}`
- Admin proxy endpoints mirror them under `/api/game/hide-and-seek/...`; settings and scene-list GET responses include `version`.

- [ ] **Step 1: Write failing core API tests for settings and paginated scene CRUD**

```python
def test_hide_and_seek_settings_and_scenes_are_managed_over_core_api(client, headers):
    settings = client.get("/internal/game/hide-and-seek/settings", headers=headers)
    updated = client.patch(
        "/internal/game/hide-and-seek/settings", headers=headers,
        json={"enabled": True, "entry_fee": 2, "win_reward": 5,
              "daily_limit": 3, "selection_timeout_minutes": 2},
    )
    created = client.post(
        "/internal/game/hide-and-seek/scenes", headers=headers,
        json={"name": "打印区"},
    )

    assert settings.status_code == 200
    assert updated.json()["entry_fee"] == 2
    assert created.status_code == 201
```

Also assert invalid negative rewards, timeout below one minute, duplicate names, and unknown IDs return `422` or `404` with a concrete Chinese error.

- [ ] **Step 2: Run the core API tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_app.py -k hide_and_seek -v`

Expected: FAIL because the endpoints and Pydantic models do not exist.

- [ ] **Step 3: Add Pydantic models and protected core endpoints**

Add response/request models with bounds: fee/reward `0..999`, daily limit `1..99`, timeout `1..60`, scene names `1..64` trimmed non-empty. Translate repository `ValueError` into `422`; return `404` for unknown scene IDs. Return the same `{items, page, page_size, total, pages}` shape used by existing random-event scenes.

- [ ] **Step 4: Run core API tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_app.py -k hide_and_seek -v`

Expected: PASS.

- [ ] **Step 5: Write failing admin proxy tests for versioned, idempotent writes**

```python
def test_admin_proxies_hide_and_seek_scene_creation_with_version_and_idempotency(client, headers, core):
    initial = client.get("/api/game/hide-and-seek/settings", headers=headers)
    response = client.post(
        "/api/game/hide-and-seek/scenes", headers={**headers,
            "If-Match": str(initial.json()["version"]), "Idempotency-Key": "hide-scene-1"},
        json={"name": "打印区"},
    )

    assert response.status_code == 201
    assert core.created_hide_and_seek_scene == {"name": "打印区"}
    assert "version" in response.json()
```

- [ ] **Step 6: Run the admin proxy test to verify it fails**

Run: `.venv/bin/python -m pytest tests/admin/test_app.py -k hide_and_seek -v`

Expected: FAIL because `AdminCorePort`, fake core, client, and proxy routes have no hide-and-seek methods.

- [ ] **Step 7: Extend the admin core port and versioned proxy routes**

Add the exact methods to `AdminCorePort` and `CoreClient`; extend the test fake with deterministic settings and scenes. Implement read routes with config version and mutation routes with `versioned_configuration_response`, `_relay_core`, and per-resource idempotency scopes. Do not add a second authorization model: use the existing `authorize` dependency.

- [ ] **Step 8: Run core and admin API tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_app.py tests/admin/test_app.py -k hide_and_seek -v`

Expected: PASS.

- [ ] **Step 9: Commit Task 3**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py tests/core/test_app.py tests/admin/test_app.py
git commit -m "feat: expose hide and seek administration api"
```

### Task 4: 管理端“躲猫猫”配置与地点库界面

**Files:**
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Test: `tests/admin/test_package_data.py`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Adds navigation view key `hide-and-seek` and a dedicated panel with summary cards, an “编辑规则” modal, a paginated location list, and an “新增地点 / 编辑地点” modal.
- JavaScript functions `loadHideAndSeek`, `openHideAndSeekSettingsModal`, and `openHideAndSeekSceneModal` use the Task 3 proxy endpoints.

- [ ] **Step 1: Write failing static/UI contract tests**

```python
def test_admin_assets_include_hide_and_seek_configuration_surface():
    html = _admin_template_text()
    javascript = _admin_javascript_text()

    assert 'data-view="hide-and-seek"' in html
    assert 'id="hide-and-seek-view"' in html
    assert "function loadHideAndSeek" in javascript
    assert "/api/game/hide-and-seek/settings" in javascript
```

- [ ] **Step 2: Run the static/UI contract test to verify it fails**

Run: `.venv/bin/python -m pytest tests/admin/test_package_data.py tests/admin/test_app.py -k hide_and_seek -v`

Expected: FAIL because the view and loaders are absent.

- [ ] **Step 3: Add the page markup and modals**

Add a left navigation item `躲猫猫`. Its panel shows enabled/disabled state, entry fee, win reward, daily limit, timeout, and enabled-location count. Add:

```html
<button id="edit-hide-and-seek-settings" class="primary" type="button">编辑规则</button>
<button id="add-hide-and-seek-scene" class="primary" type="button">新增地点</button>
<div id="hide-and-seek-scene-list" class="data-list"></div>
<div id="hide-and-seek-scene-pagination" class="pagination"></div>
```

Use the existing modal structure and buttons, with fields for enabled, entry fee, win reward, daily limit, selection timeout, scene name, and scene enabled state. Keep the main page uncluttered: forms live only inside modals.

- [ ] **Step 4: Implement loading, rendering, pagination, mutation states, and errors**

Use `requestGame`, `configurationHeaders()`, and a fresh `idempotencyKey()` for every write. While saving, set the relevant modal save button `disabled = true` and restore it in `finally`. After create/update/delete, close the modal only on success, reload settings and the current page, preserve the returned config version, and call `setResult` once with a meaningful success or error message. Render disabled scenes distinctly and include enable/disable, edit, delete actions. Do not call `setResult("状态已更新")` from polling.

- [ ] **Step 5: Add focused CSS only for the new settings/list rows**

Reuse `.panel`, `.settings-card`, `.data-row`, `.template-modal`, `.command-actions`, and existing responsive rules. Add only selectors required for scene state badges and the two-field scene form; do not alter unrelated random-event layouts.

- [ ] **Step 6: Run UI contract and complete admin tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/admin/test_package_data.py tests/admin/test_app.py -v`

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/admin/test_package_data.py tests/admin/test_app.py
git commit -m "feat: add hide and seek admin configuration"
```

### Task 5: 全量验证、部署和线上冒烟

**Files:**
- Modify only if verification reveals a task-related defect.

- [ ] **Step 1: Run the complete local suite**

Run: `.venv/bin/python -m pytest`

Expected: all tests pass; existing known deprecation warnings may remain, with no new failures.

- [ ] **Step 2: Inspect the final change set**

Run: `git status --short && git diff --check HEAD~4..HEAD`

Expected: only the hide-and-seek feature files and the user-owned untracked `docs/HANDOFF.md`; no whitespace errors.

- [ ] **Step 3: Deploy the committed revision and restart services**

Run the existing archive deployment procedure for the current commit, then:

```bash
sudo systemctl restart dzmm-core dzmm-admin-web dzmm-browser-worker
systemctl is-active dzmm-core dzmm-admin-web dzmm-browser-worker
curl -fsS http://127.0.0.1:18090/healthz
```

Expected: all three services report `active` and health returns `{"status":"ok"}`.

- [ ] **Step 4: Smoke test the deployed management endpoints**

Authenticate with the existing administrator session/token and verify the hide-and-seek settings endpoint returns the defaults and the scene page contains ten seeded locations. In the web UI, verify the new menu, modal save loading state, toast feedback, and pagination.

- [ ] **Step 5: Commit any verification-only fix and report evidence**

```bash
git add <only-files-fixed-during-verification>
git commit -m "fix: verify hide and seek deployment"
```

Only create this commit if Step 1–4 require a code fix. Report the exact test total and service status.
