# 固定场次与报名席位提示实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将随机事件改为每日固定推送场次，提供报名身份提示与今日事件手动补充/移除，并正确处理跨日活动。

**Architecture:** 固定时刻和报名补充模板存入既有随机事件设置；每日计划在首次任务运行时按固定时刻创建，并继续随机冻结启用场景与事件模板。今日人工场次直接冻结指定场景和事件；事件启动后的席位从事件快照计算，避免后续编辑场景改变已报名信息。

**Tech Stack:** Python、SQLAlchemy、Alembic、FastAPI、原生 JavaScript、pytest。

## Global Constraints

- 所有业务时间使用北京时间。
- 默认固定时刻：`00:00`、`02:00`、`10:00`、`14:00`、`16:00`、`20:00`。
- 场景与事件模板继续随机抽取；仅人工补充场次明确选择场景和事件。
- 同一群最多一场报名中或进行中的事件；跨日活动继续，后续到点场次标记为 `skipped`，不顺延。
- 仅待开始的今日计划可调整或移除；人工补充仅允许今日未来时刻。
- 不覆盖运营者已编辑的 `/加入` 回复模板。

---

### Task 1: 固定场次与报名补充模板持久化

**Files:**
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Create: `migrations/versions/20260806_12_fixed_random_event_schedule.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_app.py`

**Interfaces:**
- Produces: `RandomEventSettings(schedule_times: list[str], signup_notice_template: str, signup_timeout_minutes: int, reminder_interval_minutes: int)`.
- Produces: `CoreRepository.set_random_event_settings(schedule_times, signup_notice_template, signup_timeout_minutes, reminder_interval_minutes)`.

- [ ] **Step 1: Write failing settings tests**

```python
def test_random_event_settings_default_to_fixed_daily_times(repository):
    settings = repository.get_random_event_settings()
    assert settings.schedule_times == ["00:00", "02:00", "10:00", "14:00", "16:00", "20:00"]
    assert "{可选身份}" in settings.signup_notice_template

def test_random_event_settings_reject_duplicate_times(repository):
    with pytest.raises(ValueError, match="固定场次"):
        repository.set_random_event_settings(["10:00", "10:00"], "{可选身份}", 15, 5)
```

- [ ] **Step 2: Run tests and observe RED**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py tests/core/test_app.py -q`

Expected: FAIL because fixed-time settings fields and API payload do not exist.

- [ ] **Step 3: Implement settings and migration**

Add `schedule_times` JSON and `signup_notice_template` text to `RandomEventSettingsRecord`. Migration `20260806_12` seeds the six default times and this default:

```text
可选身份：{可选身份}
请使用 /加入 身份 报名，报名将在 {报名截止分钟} 分钟后截止。
```

Validate non-empty, at most 2,000 characters, unique valid `HH:mm` values, and only `{可选身份}` / `{报名截止分钟}` template variables. Keep old random-window database columns for existing rows but remove them from new API/UI settings.

- [ ] **Step 4: Run tests and observe GREEN**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py tests/core/test_app.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/schema.py src/dzmm_bot/core/repository.py src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py migrations/versions/20260806_12_fixed_random_event_schedule.py tests/core/test_repository.py tests/core/test_app.py
git commit -m "feat: configure fixed random event schedules"
```

### Task 2: 固定计划、跨日可见性与人工场次

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_app.py`

**Interfaces:**
- Produces: `CoreRepository.create_today_random_event(scene_id: UUID, event_name: str, scheduled_at: datetime, now: datetime) -> RandomEventSchedule`.
- Produces: `CoreRepository.delete_today_random_event(schedule_id: UUID, now: datetime) -> bool`.
- Extends: `RandomEventSchedule` / response with `event_date: date` and `is_cross_day: bool`.

- [ ] **Step 1: Write failing schedule and operation tests**

```python
def test_fixed_schedule_creates_each_configured_time_and_skips_missed_times(repository):
    repository.set_random_event_settings(["10:00", "14:00"], DEFAULT_NOTICE, 15, 5)
    schedules = repository.schedule_random_events(datetime(2026, 8, 6, 12, tzinfo=BEIJING))
    assert [item.status for item in schedules] == ["skipped", "pending"]

def test_today_event_can_be_added_and_pending_event_removed(repository):
    schedule = repository.create_today_random_event(scene.id, "咖啡事故", future, now)
    assert repository.delete_today_random_event(schedule.id, now) is True
```

Also test rejection of past time, disabled scene, unknown event, non-pending deletion, a cross-day active event in today’s list, and today’s due plans becoming `skipped` while that event remains active.

- [ ] **Step 2: Run tests and observe RED**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py tests/core/test_app.py -q`

Expected: FAIL because fixed schedule states, manual create/delete, and cross-day fields do not exist.

- [ ] **Step 3: Implement snapshots and core APIs**

```python
def create_today_random_event(self, scene_id, event_name, scheduled_at, now):
    # Require Beijing today and scheduled_at > now.
    # Require the selected scene enabled and the named event to exist.
    # Create a pending schedule with the selected scene/event/seat/reward snapshots.

def delete_today_random_event(self, schedule_id, now):
    # Delete only a pending schedule that belongs to Beijing today.
```

Generate one record per `schedule_times`; when a day is first generated after a configured minute, create that record as `skipped`. Extend today listing with any active event whose start date is before today and mark it `is_cross_day=True`. Add POST/DELETE `/internal/game/random-events/today`.

- [ ] **Step 4: Run tests and observe GREEN**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py tests/core/test_app.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py tests/core/test_repository.py tests/core/test_app.py
git commit -m "feat: manage fixed daily random events"
```

### Task 3: 报名席位文案与 /加入 变量

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `migrations/versions/20260806_12_fixed_random_event_schedule.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_group_commands.py`
- Test: `tests/deploy/test_artifacts.py`

**Interfaces:**
- Produces: `CoreRepository.random_event_open_seats(platform_id: str) -> str`.
- Extends: the `/加入` `joined` template variables with `{剩余席位}`.

- [ ] **Step 1: Write failing role-summary tests**

```python
def test_random_event_signup_announcement_includes_configured_role_summary(repository):
    repository.run_random_event_jobs(now)
    assert "可选身份：主持 × 1、员工 × 2" in latest_system_outbound(repository)

def test_join_reply_includes_only_remaining_roles(service, factory):
    receive("/加入 主持")
    assert "剩余可选身份：员工 × 2" in latest_reply(factory)
```

Also test reminder formatting, invalid notice variable rejection, and migration of only the exact old `/加入` default template.

- [ ] **Step 2: Run tests and observe RED**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py tests/core/test_group_commands.py tests/deploy/test_artifacts.py -q`

Expected: FAIL because dynamic announcement rendering and `{剩余席位}` are absent.

- [ ] **Step 3: Implement live seat summaries**

```python
def _seat_summary(seats: list[tuple[str, int]]) -> str:
    return "、".join(f"{role} × {count}" for role, count in seats)
```

Initial announcements substitute frozen total seats and timeout in the configured notice. Reminders and `/加入` substitute real-time remaining seats, omitting full roles. Change the default `/加入` joined template to:

```text
{昵称} 已加入随机事件，担任 {角色}。
剩余可选身份：{剩余席位}
```

In the same migration, update only a database template equal to the former default; retain customized templates unchanged.

- [ ] **Step 4: Run tests and observe GREEN**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py tests/core/test_group_commands.py tests/deploy/test_artifacts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/commands.py src/dzmm_bot/core/reply_templates.py migrations/versions/20260806_12_fixed_random_event_schedule.py tests/core/test_repository.py tests/core/test_group_commands.py tests/deploy/test_artifacts.py
git commit -m "feat: show random event role availability"
```

### Task 4: 管理端固定场次和今日事件操作

**Files:**
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Produces: admin POST `/api/game/random-events/today` and DELETE `/api/game/random-events/today/{schedule_id}`.
- Consumes: core today-event creation/deletion APIs and existing versioned configuration headers.

- [ ] **Step 1: Write failing proxy and page-control tests**

```python
def test_admin_proxies_today_random_event_creation_and_deletion(client, headers, core):
    created = client.post("/api/game/random-events/today", headers=headers, json=payload)
    deleted = client.delete(f"/api/game/random-events/today/{created.json()['id']}", headers=headers)
    assert created.status_code == 200
    assert deleted.status_code == 200
```

Assert that the page includes fixed-time inputs, the signup notice editor, “补充今日事件”, and “移除”; assert the script sends `schedule_times` / `signup_notice_template` and refreshes after each mutation.

- [ ] **Step 2: Run tests and observe RED**

Run: `.venv/bin/python -m pytest tests/admin/test_app.py -q`

Expected: FAIL because proxy routes, controls, and browser requests are absent.

- [ ] **Step 3: Implement admin operations**

Replace random-window inputs with add/remove fixed time rows, signup notice text, signup timeout, and reminder interval. Add a “补充今日事件” modal with enabled scene and named-event selection plus Beijing datetime. Render “跨日进行中” and give only pending rows “立即触发 / 调整时间 / 移除”. Route all create/delete/save actions through `runMutation`, idempotency keys, configuration version headers, and `loadRandomEvents()`.

- [ ] **Step 4: Run tests and observe GREEN**

Run: `.venv/bin/python -m pytest tests/admin/test_app.py -q`

Expected: PASS.

- [ ] **Step 5: Verify, commit, and deploy**

Run: `.venv/bin/python -m pytest -q && .venv/bin/alembic -c alembic.ini heads && git diff --check`

Expected: all tests pass and Alembic head is `20260806_12`.

```bash
git add src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js tests/admin/test_app.py
git commit -m "feat: manage fixed event slots in admin"
```

Deploy the committed `HEAD` using the existing secure release procedure in `deploy/scripts/deploy.sh`. After deployment, verify all three services are `active`, the settings API returns `schedule_times` and `signup_notice_template`, and Alembic reports `20260806_12 (head)`.
