# 随机事件投稿 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为员工提供不阻塞其他玩法的私聊随机事件投稿向导，并在后台完成可编辑、幂等审核、建场景、奖励和通知闭环。

**Architecture:** 独立投稿表保存向导状态与 JSON 内容，`RandomEventSubmissionHandler` 只消费投稿控制指令及投稿草稿下的剩余普通私聊。后台审核由 Core 单事务完成正式场景创建、余额流水、状态转换和私聊出站。

**Tech Stack:** Python 3.12、SQLAlchemy 2、Alembic、FastAPI/Pydantic、原生 HTML/CSS/JavaScript、pytest。

## Global Constraints

- 仅员工可投稿；每人最多一份草稿和一份待审核。
- 草稿默认 30 分钟超时，目标轮数 10、事件奖励 6、通过奖励 10、最大人数 99，均后台可配置。
- 投稿正文不进入 AI；其他明确指令和游戏路由优先，不占全局玩法门禁。
- 审核通过的建场景、状态、奖励、流水、私聊通知必须同事务幂等完成。

---

### Task 1: 投稿数据模型与配置

**Files:**
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Create: `migrations/versions/20260815_43_random_event_submissions.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/deploy/test_random_event_submission_migration.py`

**Interfaces:**
- Produces: `RandomEventSubmissionRecord` with number, user, status, step, JSON content, numeric snapshots, timestamps and review fields.
- Extends: `RandomEventSettings` with submission fields from the approved spec.

- [ ] Add failing schema/migration tests for new columns, partial unique draft/pending constraints and defaults.
- [ ] Run focused tests and verify they fail because tables/columns do not exist.
- [ ] Add models, Alembic upgrade/downgrade, settings dataclass/default initialization/API serialization.
- [ ] Add repository tests for employee eligibility, one draft/pending limit, expiration and numeric snapshots; verify failure.
- [ ] Implement minimal draft lifecycle repository methods and run focused tests until green.

### Task 2: 私聊向导状态机

**Files:**
- Create: `src/dzmm_bot/core/random_event_submissions.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/service.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Test: `tests/core/test_random_event_submissions.py`
- Test: `tests/core/test_service.py`

**Interfaces:**
- Produces: `RandomEventSubmissionHandler.handle(message) -> CommandReply | list[CommandReply] | None` and `accepts_plain_direct(message) -> bool`.
- Consumes: repository lifecycle methods from Task 1.

- [ ] Add failing tests for `/投稿 随机事件`, group-to-direct handoff, unavailable private chat, employee check and draft resume.
- [ ] Implement entry/control routing and add command definitions/help text.
- [ ] Add failing step tests for name, notice, participant count, role name/capacity, event name/opening, preview and `/确认投稿`.
- [ ] Implement the smallest explicit state transition table and input validators; keep all non-command draft input private.
- [ ] Add failing tests for `/上一步`, cancel confirmation, modify/delete role/event, `/继续添加`, `/事件完成`, `/我的投稿` and `/撤回投稿 编号`.
- [ ] Implement controls and run `PYTHONPATH=src .venv/bin/pytest tests/core/test_random_event_submissions.py -q` until green.
- [ ] Add service tests proving ordinary commands/game commands route first, multiple users do not share state, and submission text is ineligible for AI history; implement service routing and run green.

### Task 3: 管理 Core API 与审核事务

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_app.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces: list/detail/update/reject/approve internal endpoints.
- Approval consumes the existing random-event scene validator and balance transaction writer.

- [ ] Add failing API tests for pagination/filter/detail and editable content validation.
- [ ] Implement query/update endpoints while keeping numeric snapshots immutable.
- [ ] Add failing transaction tests for approve, reject reason, duplicate scene, withdrawn submission, repeated/concurrent approval and reviewer audit.
- [ ] Implement row-locked approve/reject methods; approval creates enabled scene records, calls `_apply_balance_change(..., "random_event_submission_approval", ...)`, records result and enqueues direct notification in the same transaction.
- [ ] Run `PYTHONPATH=src .venv/bin/pytest tests/core/test_repository.py tests/core/test_app.py -k submission -q` until green.

### Task 4: 管理后台审核界面与设置

**Files:**
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- Consumes: Task 3 internal APIs.
- Produces: 随机事件页“玩家投稿”标签、状态筛选、详情编辑、通过/拒绝操作和投稿设置字段。

- [ ] Add failing admin proxy tests for authenticated list/detail/edit/approve/reject and config propagation.
- [ ] Implement CoreClient and admin routes with existing idempotency conventions.
- [ ] Add failing HTML assertions for submission tab, pending count, form controls and rejection reason.
- [ ] Implement minimal UI rendering, editor collection, status filtering and review mutations.
- [ ] Run `node --check src/dzmm_bot/admin/static/admin.js` and `PYTHONPATH=src .venv/bin/pytest tests/admin/test_app.py -k 'random_event and submission' -q` until green.

### Task 5: 过期任务、记忆事实与全量回归

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/scheduler.py`
- Modify: `src/dzmm_bot/core/ai_knowledge.py`
- Test: `tests/core/test_scheduler.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_group_commands.py`

**Interfaces:**
- Completes: timed expiration, activity facts and player-facing help.

- [ ] Add failing scheduler test proving inactive drafts expire independently without group notification.
- [ ] Implement expiration sweep and activity facts only for submitted/final outcomes.
- [ ] Add help/knowledge tests proving exact commands are discoverable without exposing draft content.
- [ ] Run all random event, command, scheduler, admin and AI memory focused suites.
- [ ] Run `PYTHONPATH=src .venv/bin/python -m pytest -q`, `node --check src/dzmm_bot/admin/static/admin.js`, `.venv/bin/alembic heads`, and `git diff --check`.
