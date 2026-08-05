# 公司随机事件 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Add configurable, daily company roleplay events with seats, rounds, rewards, scheduling, and an operator console.

**Architecture:** Store settings, scenes, seats, daily schedules, event snapshots, and participants in the core database. Extend the existing daily-job loop to process schedules and extend the existing group command handler for player actions. The existing admin API and static console will mirror core endpoints and use their existing idempotency and configuration-version controls.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy/Alembic, PostgreSQL/SQLite, static HTML/CSS/JavaScript.

## Global Constraints

- Use \`Asia/Shanghai\` for timestamps, dates, and schedules.
- A group has at most one \`signing_up\` or \`in_progress\` event.
- Daily schedules are generated at midnight from the configured time window, count, and decimal-hour minimum interval.
- Commands and bot output never count toward rounds; each non-command player text counts as one round.
- Qualified \`/退出\` awards the frozen scene reward exactly once; unqualified exit does not award.
- Cross-day events remain active; conflicting next-day plans become \`skipped\`.

---

### Task 1: Add persistence and daily scheduling

**Files:**
- Modify: \`src/dzmm_bot/core/schema.py\`
- Create: \`migrations/versions/20260806_08_random_events.py\`
- Modify: \`src/dzmm_bot/core/repository.py\`
- Test: \`tests/core/test_repository.py\`

**Interfaces:**
- \`RandomEventSettings(start_time, end_time, events_per_day, minimum_interval_minutes, signup_timeout_minutes, reminder_interval_minutes)\`
- \`CoreRepository.get_random_event_settings()\`, \`set_random_event_settings(...)\`, \`save_random_event_scene(...)\`, \`list_random_event_scenes(...)\`, \`schedule_random_events(now)\`, and \`list_today_random_event_schedules(now)\`.

- [ ] **Step 1: Write failing settings and schedule tests**

\`\`\`python
def test_random_event_schedule_respects_window_and_minimum_gap(repository):
    repository.set_random_event_settings("10:00", "24:00", 3, 90, 15, 5)
    schedules = repository.schedule_random_events(beijing_datetime(2026, 8, 6, 0, 0))
    assert len(schedules) == 3
    assert all("10:00" <= row.scheduled_time.strftime("%H:%M") < "24:00" for row in schedules)
    assert all((right.scheduled_time - left.scheduled_time).total_seconds() >= 5400 for left, right in zip(schedules, schedules[1:]))
\`\`\`

- [ ] **Step 2: Verify RED**

Run: \`.venv/bin/python -m pytest tests/core/test_repository.py::test_random_event_schedule_respects_window_and_minimum_gap -q\`

Expected: FAIL because random-event storage is absent.

- [ ] **Step 3: Implement the minimal schema and repository methods**

Add singleton settings, scenes, scene seats, daily schedules, event snapshots, event-seat snapshots, and participants. Persist a daily random sample once. Reject configurations where count cannot fit the window and interval. Freeze scene text, reward, target rounds, and seats when an event starts.

- [ ] **Step 4: Verify GREEN**

Run: \`.venv/bin/python -m pytest tests/core/test_repository.py -q\`

Expected: PASS, including infeasible-spacing validation.

- [ ] **Step 5: Commit**

\`\`\`bash
git add src/dzmm_bot/core/schema.py src/dzmm_bot/core/repository.py migrations/versions/20260806_08_random_events.py tests/core/test_repository.py
git commit -m "feat: persist random event schedules"
\`\`\`

### Task 2: Implement event lifecycle, seats, rounds, and rewards

**Files:**
- Modify: \`src/dzmm_bot/core/repository.py\`
- Test: \`tests/core/test_repository.py\`

**Interfaces:**
- \`run_random_event_jobs(now, group_id) -> list[str]\`
- \`join_random_event(platform_id, role, now) -> RandomEventJoinResult\`
- \`leave_random_event(platform_id, now) -> RandomEventLeaveResult\`
- \`record_random_event_round(platform_id, content, now) -> None\`

- [ ] **Step 1: Write failing lifecycle tests**

\`\`\`python
def test_due_schedule_is_skipped_when_group_has_active_event(repository, now):
    repository.start_random_event_for_test("group-1", now)
    repository.create_due_random_event_schedule("group-1", now)
    assert repository.run_random_event_jobs(now, "group-1") == []
    assert repository.list_today_random_event_schedules(now)[0].status == "skipped"

def test_qualified_exit_awards_once(repository, now):
    repository.start_full_random_event_for_test("group-1", target_rounds=2, reward=5)
    repository.join_random_event("player-1", "男", now)
    repository.record_random_event_round("player-1", "第一句", now)
    repository.record_random_event_round("player-1", "第二句", now)
    assert repository.leave_random_event("player-1", now).reward == 5
    assert repository.leave_random_event("player-1", now).reward == 0
\`\`\`

- [ ] **Step 2: Verify RED**

Run: \`.venv/bin/python -m pytest tests/core/test_repository.py -k 'random_event and (skipped or qualified)' -q\`

Expected: FAIL because lifecycle methods are absent.

- [ ] **Step 3: Implement the state machine**

Use schedule states \`pending\`, \`started\`, \`skipped\`; event states \`signing_up\`, \`in_progress\`, \`ended\`, \`dissolved\`. Start a due event only if no active event exists, expire unfilled signup windows, queue reminders once per interval, lock seats during joins, and end after the last participant leaves. Apply a unique \`random_event_reward\` balance transaction only for qualified leaves.

- [ ] **Step 4: Verify GREEN**

Run: \`.venv/bin/python -m pytest tests/core/test_repository.py tests/core/test_service.py -q\`

Expected: PASS.

- [ ] **Step 5: Commit**

\`\`\`bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: run random event lifecycle"
\`\`\`

### Task 3: Wire group commands, inbound rounds, and event jobs

**Files:**
- Modify: \`src/dzmm_bot/core/commands.py\`
- Modify: \`src/dzmm_bot/core/service.py\`
- Modify: \`src/dzmm_bot/core/repository.py\`
- Test: \`tests/core/test_group_commands.py\`
- Test: \`tests/core/test_service.py\`

**Interfaces:**
- Extend \`GroupCommandHandler.handle\` with \`/加入 角色\` and \`/退出\`.
- Call \`record_random_event_round\` only after a newly inserted non-command inbound message.
- Call \`run_random_event_jobs\` from \`run_daily_jobs\` and enqueue returned notices.

- [ ] **Step 1: Write a failing command test**

\`\`\`python
def test_qualified_random_event_exit_replies_with_reward(service, repository, now):
    repository.start_full_random_event_for_test("group-1", target_rounds=1, reward=5)
    service.receive_inbound(message("join", "u1", "/加入 男", now))
    service.receive_inbound(message("chat", "u1", "开始聊天", now))
    service.receive_inbound(message("leave", "u1", "/退出", now))
    assert "获得 5 摸鱼币" in outbound_text(repository)
\`\`\`

- [ ] **Step 2: Verify RED**

Run: \`.venv/bin/python -m pytest tests/core/test_group_commands.py -k random_event -q\`

Expected: FAIL because \`/加入\` and \`/退出\` are unknown commands.

- [ ] **Step 3: Implement minimal wiring**

Require an existing employee to join, return clear seat/round/reward text, and never count slash commands. Enqueue normal outbound rows for opening, reminders, dissolution, and player responses.

- [ ] **Step 4: Verify GREEN and commit**

Run: \`.venv/bin/python -m pytest tests/core/test_group_commands.py tests/core/test_service.py tests/browser/test_worker.py -q\`

\`\`\`bash
git add src/dzmm_bot/core/commands.py src/dzmm_bot/core/service.py src/dzmm_bot/core/repository.py tests/core/test_group_commands.py tests/core/test_service.py
git commit -m "feat: add random event group commands"
\`\`\`

### Task 4: Add versioned core and admin management APIs

**Files:**
- Modify: \`src/dzmm_bot/core/api_models.py\`
- Modify: \`src/dzmm_bot/core/app.py\`
- Modify: \`src/dzmm_bot/admin/core_client.py\`
- Modify: \`src/dzmm_bot/admin/app.py\`
- Test: \`tests/core/test_app.py\`
- Test: \`tests/admin/test_app.py\`

**Interfaces:**
- Core \`GET/PATCH /internal/game/random-events/settings\`.
- Core \`GET/POST/PATCH /internal/game/random-events/scenes\`.
- Core \`GET /internal/game/random-events/today\` and \`PATCH /internal/game/random-events/today/{schedule_id}\`.
- Admin mirrors under \`/api/game/random-events/...\`.

- [ ] **Step 1: Write a failing pending-schedule API test**

\`\`\`python
def test_admin_moves_only_pending_random_event_schedule(client, headers):
    schedule = create_pending_random_event_schedule(client, headers, "13:00")
    response = client.patch(
        f"/api/game/random-events/today/{schedule['id']}",
        headers={**headers, "Idempotency-Key": "move-event", "If-Match": "0"},
        json={"scheduled_time": "14:30"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
\`\`\`

- [ ] **Step 2: Verify RED**

Run: \`.venv/bin/python -m pytest tests/core/test_app.py tests/admin/test_app.py -k random_event -q\`

Expected: FAIL because event endpoints are absent.

- [ ] **Step 3: Implement API models and relays**

Validate role counts, target rounds, reward, time format, time-window feasibility, and pending-only schedule moves. Attach configuration versions to settings and scenes. Require \`Idempotency-Key\` for writes and return 409 on stale \`If-Match\`.

- [ ] **Step 4: Verify GREEN and commit**

Run: \`.venv/bin/python -m pytest tests/core/test_app.py tests/admin/test_app.py -q\`

\`\`\`bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py tests/core/test_app.py tests/admin/test_app.py
git commit -m "feat: expose random event management APIs"
\`\`\`

### Task 5: Build the operator console

**Files:**
- Modify: \`src/dzmm_bot/admin/templates/index.html\`
- Modify: \`src/dzmm_bot/admin/static/admin.js\`
- Modify: \`src/dzmm_bot/admin/static/admin.css\`
- Test: \`tests/admin/test_app.py\`

**Interfaces:** Add \`随机事件\` navigation, settings, scene library, and today's schedule list.

- [ ] **Step 1: Write a failing static-console contract test**

\`\`\`python
def test_admin_dashboard_exposes_random_event_management(client):
    page = client.get("/").text
    script = client.get("/static/admin.js").text
    assert 'id="nav-random-events"' in page
    assert 'id="random-event-scenes"' in page
    assert 'id="today-random-events"' in page
    assert "random-events/today" in script
\`\`\`

- [ ] **Step 2: Verify RED**

Run: \`.venv/bin/python -m pytest tests/admin/test_app.py::test_admin_dashboard_exposes_random_event_management -q\`

Expected: FAIL because the view is absent.

- [ ] **Step 3: Implement the smallest usable UI**

Use existing modal, pagination, \`runMutation\`, idempotency-key, and configuration-version patterns. Provide global settings, paginated scenes with editable role rows and enable toggles, plus today's rows with planned time, state, frozen scene, participation progress, and a pending-only time edit.

- [ ] **Step 4: Verify GREEN and commit**

Run: \`.venv/bin/python -m pytest tests/admin/test_app.py -q\`

\`\`\`bash
git add src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/admin/test_app.py
git commit -m "feat: add random event management console"
\`\`\`

### Task 6: Regression and deployment

- [ ] **Step 1: Run full local verification**

Run: \`.venv/bin/python -m pytest -q tests/admin tests/browser tests/core tests/runtime\`

Expected: PASS; PostgreSQL-only migration tests may skip without \`TEST_DATABASE_URL\`.

- [ ] **Step 2: Verify migration graph**

Run: \`.venv/bin/alembic -c alembic.ini heads\`

Expected: one head, \`20260806_08\`.

- [ ] **Step 3: Deploy and verify**

Deploy with the existing staged \`rsync\` plus \`deploy/scripts/deploy.sh\` workflow. Restart the three DZMM services and verify they are active, Alembic reports the new head, and \`curl -fsS http://127.0.0.1:18090/healthz\` succeeds.

