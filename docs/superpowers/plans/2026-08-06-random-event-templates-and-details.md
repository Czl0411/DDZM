# 随机事件模板与详情 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将场景的正式开场白升级为命名事件模板，预先选定每日计划，并记录和展示参与者发言详情。

**Architecture:** 事件模板归属场景；计划在北京时间零点生成时冻结场景和模板快照；运行时事件保存名称和渲染后的开场白，详情单独逐条保存。核心服务提供模板、计划、详情和立即触发接口，管理端仅代理和呈现。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy、Alembic、PostgreSQL、原生 JavaScript/CSS、pytest。

## Global Constraints

- 所有业务时间使用北京时间。
- 同一群组同时只能有一场 `signup` 或 `in_progress` 随机事件。
- 角色变量仅在事件开场白中使用，并在满员时替换成真实昵称。
- 详情只记录进行中、已加入且未退出玩家的非指令消息，不发送到群。
- 管理端写操作沿用版本号、幂等键、忙碌状态和错误反馈。
- 不修改或提交 `docs/HANDOFF.md`。

---

### Task 1: 添加事件模板、计划快照和详情数据模型

**Files:**
- Create: `migrations/versions/20260806_10_random_event_templates.py`
- Modify: `src/dzmm_bot/core/schema.py:167-235`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces `RandomEventSceneEventRecord(name, opening_text, position)`。
- Produces `RandomEventDetailRecord(event_id, user_id, display_name, content, occurred_at, position)`。
- Adds plan snapshot fields `scene_name`、`event_name`、`signup_text`、`formal_opening_text`、`reward`、`target_rounds` and event snapshot field `event_name`.

- [ ] **Step 1: Write the failing test**

```python
def test_random_event_scene_returns_named_event_templates(repository):
    scene = repository.create_random_event_scene("茶水间", "报名", [{"name": "咖啡事故", "opening_text": "{主持}打翻咖啡。"}], 3, 10, [("主持", 1)])
    assert scene.events[0].name == "咖啡事故"
    assert scene.events[0].opening_text == "{主持}打翻咖啡。"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py::test_random_event_scene_returns_named_event_templates -v`  
Expected: FAIL because `events` is not exposed.

- [ ] **Step 3: Write minimal implementation**

```python
op.create_table("random_event_scene_events", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("scene_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("position", sa.Integer(), nullable=False), sa.Column("name", sa.String(length=64), nullable=False), sa.Column("opening_text", sa.Text(), nullable=False), sa.UniqueConstraint("scene_id", "position"))
```

Migrate each old `random_event_scene_openings.content` row into an event template with the same position and name `未命名事件`; add snapshot columns as nullable for pre-existing schedules and a detail table. Reflect them with focused SQLAlchemy records.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py::test_random_event_scene_returns_named_event_templates -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/20260806_10_random_event_templates.py src/dzmm_bot/core/schema.py tests/core/test_repository.py && git commit -m "feat: add random event templates and details"
```

### Task 2: 冻结计划、记录详情并立即触发

**Files:**
- Modify: `src/dzmm_bot/core/repository.py:90-125,418-955,1945-2050`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces `RandomEventSchedule(scene_name, event_name, scheduled_at, status)`.
- Produces `RandomEventDetail(display_name, content, occurred_at, position)`.
- Adds `trigger_random_event(schedule_id: UUID, now: datetime) -> RandomEventSchedule` and `list_random_event_details(schedule_id: UUID) -> list[RandomEventDetail]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_schedule_freezes_scene_and_event_before_start(repository, clock):
    repository.schedule_random_events(clock)
    schedule = repository.list_today_random_event_schedules(clock)[0]
    assert (schedule.scene_name, schedule.event_name) == ("茶水间", "咖啡事故")

def test_event_records_only_active_participant_dialogue(repository, clock):
    event = _start_full_event(repository, clock)
    repository.record_random_event_round("u1", clock, "开始收拾")
    repository.record_random_event_round("observer", clock, "（路过）")
    assert [(x.display_name, x.content) for x in repository.list_random_event_details(event.schedule_id)] == [("小明", "开始收拾")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py -k 'freezes_scene or records_only_active' -v`  
Expected: FAIL because planning is late-bound and details are absent.

- [ ] **Step 3: Write minimal implementation**

```python
def trigger_random_event(self, schedule_id: UUID, now: datetime) -> RandomEventSchedule:
    # Lock a same-day pending plan, require no active event, and use its snapshot to create signup.
```

Select an enabled scene plus one of its templates while generating every daily schedule. Store the complete snapshot, and also fill any same-day pending schedule whose migration-era snapshot is empty; create signup only from that snapshot, add the event name to the frozen event record, and display `【随机事件：场景－事件】` when full. Extend `record_random_event_round` to append a detail record only after the existing active-participant classification succeeds. Exclude commands, observers and leavers. Make the immediate trigger reuse the same signup-creation helper and retain a pending row when blocked by an active event.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_repository.py -k 'random_event' -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py && git commit -m "feat: freeze random event templates and details"
```

### Task 3: 暴露核心和管理端 API

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py:195-240`
- Modify: `src/dzmm_bot/core/app.py:390-490,650-705`
- Modify: `src/dzmm_bot/admin/core_client.py:160-215`
- Modify: `src/dzmm_bot/admin/app.py:450-600`
- Test: `tests/core/test_app.py`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Consumes `events: list[{name: str, opening_text: str}]`.
- Produces schedule `scene_name` plus `event_name`.
- Produces `GET /internal/game/random-events/today/{schedule_id}/details` and `POST /internal/game/random-events/today/{schedule_id}/trigger`, with matching `/api/game/...` admin proxies.

- [ ] **Step 1: Write failing API tests**

```python
def test_random_event_scene_api_accepts_named_events(client, headers):
    response = client.post("/internal/game/random-events/scenes", headers=headers, json={"name": "茶水间", "signup_text": "报名", "events": [{"name": "咖啡事故", "opening_text": "开场"}], "reward": 3, "target_rounds": 10, "seats": [{"role": "主持", "capacity": 1}]})
    assert response.json()["events"][0]["name"] == "咖啡事故"

def test_trigger_and_list_random_event_details(client, headers):
    assert client.post(f"/internal/game/random-events/today/{schedule_id}/trigger", headers=headers).status_code == 200
    assert client.get(f"/internal/game/random-events/today/{schedule_id}/details", headers=headers).json()["items"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/core/test_app.py -k 'named_events or trigger_and_list' -v`  
Expected: FAIL because request models and routes are absent.

- [ ] **Step 3: Write minimal implementation**

```python
class RandomEventTemplateModel(ApiModel):
    name: str = Field(min_length=1, max_length=64)
    opening_text: str = Field(min_length=1, max_length=2000)
```

Replace `openings` input/output with `events` throughout scene endpoints; reject blank names, blank opening texts and unknown role variables. Add core routes, client methods and authenticated admin proxy routes. Preserve versioned mutation wrapping for trigger.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/test_app.py tests/admin/test_app.py -k 'random_event' -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py tests/core/test_app.py tests/admin/test_app.py && git commit -m "feat: expose random event templates and details"
```

### Task 4: 管理端模板编辑、今日列表和详情弹窗

**Files:**
- Modify: `src/dzmm_bot/admin/templates/index.html:175-330`
- Modify: `src/dzmm_bot/admin/static/admin.js:150-270,895-940`
- Modify: `src/dzmm_bot/admin/static/admin.css:80-110`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Consumes core `events`, plan `event_name` and detail arrays.
- Produces a read-only details modal and actions `data-trigger-random-event`, `data-adjust-random-event`, and `data-view-random-event-details`.

- [ ] **Step 1: Write failing UI tests**

```python
def test_random_event_scene_page_contains_named_event_fields(client):
    page = client.get("/").text
    assert 'data-random-event-name' in page
    assert 'data-random-event-opening' in page

def test_random_event_script_offers_trigger_and_detail_actions():
    script = Path("src/dzmm_bot/admin/static/admin.js").read_text()
    assert "data-trigger-random-event" in script
    assert "openRandomEventDetailsModal" in script
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/admin/test_app.py -k 'named_event_fields or trigger_and_detail_actions' -v`  
Expected: FAIL because controls are absent.

- [ ] **Step 3: Write minimal implementation**

```js
function renderTodayRandomEvents(events) {
  return `${event.scene_name}－${event.event_name}－${eventStatusLabel(event.status)}`;
}
```

Give every event-template row a name input, opening textarea, role-variable chips and delete action. Show “立即触发”“调整时间” for `pending`; show “查看详情” for all other states. The read-only modal renders `昵称：内容` with Beijing timestamps in sequence or `暂无参与者发言记录`. Use existing `runMutation`, configuration headers and post-save reloads.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/admin/test_app.py -k 'random_event' -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/admin/test_app.py && git commit -m "feat: manage random event templates and details"
```

### Task 5: 全量验证与部署

**Files:**
- Modify: `docs/superpowers/plans/2026-08-06-random-event-templates-and-details.md`

- [ ] **Step 1: Run full verification**

Run: `git diff --check && .venv/bin/python -m pytest`  
Expected: 所有测试通过；只保留现有集成跳过项。

- [ ] **Step 2: Deploy and migrate**

Run: `git archive --format=tar HEAD | ssh ubuntu@43.134.78.52 'tar -xf - -C /tmp/dzmm-release && sudo bash /tmp/dzmm-release/deploy/scripts/deploy.sh /tmp/dzmm-release && sudo systemctl restart dzmm-core dzmm-admin-web dzmm-browser-worker'`  
Expected: Alembic 升级至新版本，三个服务重启成功。

- [ ] **Step 3: Verify production and commit plan**

Run: `ssh ubuntu@43.134.78.52 'systemctl is-active dzmm-core dzmm-admin-web dzmm-browser-worker'`  
Expected: 三行均为 `active`。

```bash
git add docs/superpowers/plans/2026-08-06-random-event-templates-and-details.md && git commit -m "docs: plan random event templates and details"
```
