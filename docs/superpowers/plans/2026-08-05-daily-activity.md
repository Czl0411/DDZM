# Daily Activity and Income Leaderboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add configurable daily activity levels, automatic midnight rewards, a personal /我 and /me view, and configurable scheduled daily-income leaderboard pushes.

**Architecture:** Core persists activity configuration, daily text totals, balance transactions, settlements, and report deliveries. Each accepted ordinary message updates the joined sender’s Beijing-date total; Core creates durable replies and scheduled reports. The Browser Worker only invokes the daily job and sends the existing outbound queue.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL/SQLite tests, Pydantic, vanilla HTML/CSS/JavaScript, pytest.

## Global Constraints

- All business dates, schedules, and displayed timestamps use Asia/Shanghai.
- Count only a joined member’s non-command text after removing whitespace; do not expose raw count to players.
- Default rules are LV1–LV10: thresholds 10,25,60,90,140,190,250,330,410,500; rewards 1,2,3,4,5,6,7,8,9,10.
- Rewards settle automatically after Beijing 00:00, exactly once per user/date.
- Today’s income sums positive balance transactions only. Negative changes may make balance negative but never reduce income or rank.
- Scheduled income leaderboards use configurable Beijing HH:MM slots, default 12:00,16:00,20:00,23:59; an empty slot emits no message.
- Preserve existing command templates, economy settings, login behavior, and the user-owned untracked docs/HANDOFF.md.

---

## File Structure

- Modify src/dzmm_bot/core/schema.py — activity, ledger, schedule, delivery records and system outbounds.
- Create migrations/versions/20260805_05_daily_activity.py — tables and default rules/schedules.
- Modify src/dzmm_bot/core/repository.py — state, validation, ledger, settlement, report queueing.
- Modify src/dzmm_bot/core/service.py, commands.py, reply_templates.py — inbound counting and /我, /me.
- Modify src/dzmm_bot/core/api_models.py, app.py, browser/core_client.py, browser/worker.py — protected settings/job APIs.
- Modify src/dzmm_bot/admin/core_client.py, app.py, templates/index.html, static/admin.js, static/admin.css — modal configuration.
- Modify focused Core, Browser, and Admin pytest files already covering these modules.

### Task 1: Persist configuration and system outbound records

**Files:**
- Modify: src/dzmm_bot/core/schema.py
- Create: migrations/versions/20260805_05_daily_activity.py
- Test: tests/core/test_repository.py

**Interfaces:**
- Produces ActivityLevelRuleRecord, DailyActivityRecord, ActivityRewardSettlementRecord, BalanceTransactionRecord, IncomeReportScheduleRecord, and IncomeReportDeliveryRecord.
- Makes OutboundRecord.inbound_message_id nullable and adds enqueue_system_outbound(text: str) -> OutboundRecord.

- [ ] **Step 1: Write failing persistence tests**

~~~python
def test_activity_defaults_seed_rules_and_report_times(repository):
    settings = repository.get_activity_settings()

    assert [(rule.level, rule.character_threshold, rule.reward) for rule in settings.rules] == [
        (1, 10, 1), (2, 25, 2), (3, 60, 3), (4, 90, 4), (5, 140, 5),
        (6, 190, 6), (7, 250, 7), (8, 330, 8), (9, 410, 9), (10, 500, 10),
    ]
    assert settings.report_times == ["12:00", "16:00", "20:00", "23:59"]

def test_system_outbound_can_be_claimed(repository, now):
    outbound = repository.enqueue_system_outbound("系统推送")
    assert repository.claim_outbound("worker", now, 30).id == outbound.id
~~~

- [ ] **Step 2: Run the tests to verify failure**

Run: pytest tests/core/test_repository.py -k 'activity_defaults or system_outbound' -v

Expected: FAIL because the records and repository methods do not exist.

- [ ] **Step 3: Implement the schema and migration**

~~~python
class DailyActivityRecord(Base):
    __tablename__ = "daily_activities"
    __table_args__ = (UniqueConstraint("user_id", "activity_date"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    activity_date: Mapped[date] = mapped_column(Date, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
~~~

Create all other records above. Migration revision 20260805_05 descends from 20260805_04, makes the outbound foreign key nullable, and seeds rules/schedules only when absent.

- [ ] **Step 4: Implement defaults and system-outbound creation**

~~~python
def enqueue_system_outbound(self, text: str) -> OutboundRecord:
    with self._session() as session:
        record = OutboundRecord(inbound_message_id=None, text=text)
        session.add(record)
        session.flush()
        return record
~~~

Use the existing claim/lease/confirm workflow unchanged.

- [ ] **Step 5: Verify and commit**

Run: pytest tests/core/test_repository.py -k 'activity_defaults or system_outbound' -v && alembic -c alembic.ini upgrade head

Expected: PASS and Alembic current revision is 20260805_05.

~~~bash
git add src/dzmm_bot/core/schema.py migrations/versions/20260805_05_daily_activity.py tests/core/test_repository.py
git commit -m "feat: persist daily activity settings"
~~~

### Task 2: Implement activity, ledger, settlement, and reports

**Files:**
- Modify: src/dzmm_bot/core/repository.py
- Test: tests/core/test_repository.py

**Interfaces:**
- Produces record_activity(platform_id, received_at, content), personal_activity(platform_id, now), today_income(user_id, now), run_daily_jobs(now), and set_activity_settings(rules, report_times).
- run_daily_jobs writes settlement and report delivery records atomically with balance/outbound effects.

- [ ] **Step 1: Write failing behavior tests**

~~~python
def test_activity_counts_joined_non_command_text_without_whitespace(repository, now):
    repository.create_user("u1", "小明", now, 0)

    repository.record_activity("u1", now, "你 好\n！")
    repository.record_activity("u1", now, "/我")
    repository.record_activity("unknown", now, "一二三四五六七八九十")
    repository.record_activity("u1", now, "再来六个字呀")

    assert repository.personal_activity("u1", now).level == 1

def test_settlement_is_once_and_negative_does_not_reduce_today_income(repository):
    yesterday = datetime(2026, 8, 5, 23, 59, tzinfo=BEIJING)
    user, _ = repository.create_user("u1", "小明", yesterday, 0)
    repository.record_activity("u1", yesterday, "一二三四五六七八九十")

    repository.run_daily_jobs(datetime(2026, 8, 6, 0, 0, tzinfo=BEIJING))
    repository.record_balance_change(user.id, -4, "penalty", datetime(2026, 8, 6, 1, 0, tzinfo=BEIJING))

    assert repository.today_income(user.id, datetime(2026, 8, 6, 2, 0, tzinfo=BEIJING)) == 1
    repository.run_daily_jobs(datetime(2026, 8, 6, 0, 1, tzinfo=BEIJING))
    assert repository.find_user("u1").balance == -3
~~~

Add tests for invalid rule counts, duplicate report times, non-increasing thresholds, top-ten sorting, skipped empty slots, and exactly-one non-empty scheduled outbound.

- [ ] **Step 2: Run tests to verify failure**

Run: pytest tests/core/test_repository.py -k 'record_activity or settlement or income_report or activity_settings' -v

Expected: FAIL because activity, ledger, settlement, and scheduling are absent.

- [ ] **Step 3: Implement minimal repository behavior**

~~~python
def record_activity(self, platform_id: str, received_at: datetime, content: str) -> None:
    if content.lstrip().startswith("/"):
        return
    character_count = len("".join(content.split()))
    if not character_count:
        return
    # Find joined user; atomically insert-or-increment the Beijing-date row.

def _apply_balance_change(self, user: UserRecord, amount: int, source: str, occurred_at: datetime) -> None:
    user.balance += amount
    self._active_session.get().add(BalanceTransactionRecord(
        user_id=user.id, amount=amount, source=source, occurred_at=occurred_at,
    ))
~~~

Use the helper for nonzero join rewards, check-ins, and settlements. Derive LV from current ordered rules. Job runs settle historical activity first, then inspect every due configured slot. Persist a delivery record for skipped and queued slots. Rank is current Beijing-day positive transactions summed per user, ordered by total descending then user ID.

- [ ] **Step 4: Verify and commit**

Run: pytest tests/core/test_repository.py -k 'record_activity or settlement or income_report or activity_settings' -v

Expected: PASS, including repeated job execution.

~~~bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: add activity rewards and income reports"
~~~

### Task 3: Track inbound activity and implement /我 and /me

**Files:**
- Modify: src/dzmm_bot/core/service.py
- Modify: src/dzmm_bot/core/commands.py
- Modify: src/dzmm_bot/core/reply_templates.py
- Test: tests/core/test_service.py
- Test: tests/core/test_group_commands.py

**Interfaces:**
- Consumes Task 2 repository APIs.
- Produces canonical /我, alias /me, and variables {昵称}, {余额}, {货币}, {活跃等级}, {今日收益}, {日期}.

- [ ] **Step 1: Write failing service and command tests**

~~~python
def test_service_records_an_accepted_message_once(repository, service, now):
    repository.create_user("sender-1", "小明", now, 0)
    message = InboundMessage("p-1", "sender-1", "一二三四五六七八九十", now)

    service.receive_inbound(message)
    service.receive_inbound(message)

    assert repository.personal_activity("sender-1", now).level == 1

def test_me_alias_hides_count_and_shows_personal_status(handler, repository, now):
    repository.create_user("sender-1", "小明", now, 3)
    repository.record_activity("sender-1", now, "一二三四五六七八九十")

    reply = handler.handle(InboundMessage("p-2", "sender-1", "/me", now))

    assert "3 摸鱼币" in reply
    assert "LV1" in reply
    assert "今日收益：3" in reply
    assert "10" not in reply
~~~

- [ ] **Step 2: Run tests to verify failure**

Run: pytest tests/core/test_service.py tests/core/test_group_commands.py -k 'activity or me' -v

Expected: FAIL because the service does not track activity and /me is unknown.

- [ ] **Step 3: Implement minimal command behavior**

~~~python
stored, inserted = self._repository.accept_inbound(message)
if not inserted:
    return ReceiveResult(stored.id, False)
self._repository.record_activity(message.sender_platform_id, message.received_at, message.content)
reply = self._command_handler.handle(message)
~~~

Normalize /me to /我 before dispatch. Add command/template definitions for /我 with shown/not-joined scenarios. Keep /余额 and all existing commands.

- [ ] **Step 4: Verify and commit**

Run: pytest tests/core/test_service.py tests/core/test_group_commands.py -k 'activity or me' -v

Expected: PASS; duplicate, blank, command, and unjoined messages do not count.

~~~bash
git add src/dzmm_bot/core/service.py src/dzmm_bot/core/commands.py src/dzmm_bot/core/reply_templates.py tests/core/test_service.py tests/core/test_group_commands.py
git commit -m "feat: show personal activity and income"
~~~

### Task 4: Expose protected Core APIs and run jobs from the Worker

**Files:**
- Modify: src/dzmm_bot/core/api_models.py
- Modify: src/dzmm_bot/core/app.py
- Modify: src/dzmm_bot/browser/core_client.py
- Modify: src/dzmm_bot/browser/worker.py
- Test: tests/core/test_app.py
- Test: tests/browser/test_core_client.py
- Test: tests/browser/test_worker.py

**Interfaces:**
- Produces GET/PATCH /internal/game/activity-settings and POST /internal/daily-jobs/run.
- Produces CorePort.run_daily_jobs(now: datetime) -> None.

- [ ] **Step 1: Write failing API and Worker tests**

~~~python
def test_activity_settings_api_updates_rules_and_times(client, headers):
    response = client.patch("/internal/game/activity-settings", headers=headers, json={
        "rules": [{"level": level, "character_threshold": level * 10, "reward": level} for level in range(1, 11)],
        "report_times": ["09:30", "18:00"],
    })

    assert response.status_code == 200
    assert response.json()["report_times"] == ["09:30", "18:00"]

def test_worker_runs_jobs_after_inbound_submission(worker, core, gateway):
    gateway.messages = [message]
    worker.run_once()
    assert core.calls.index("submit_inbound") < core.calls.index("run_daily_jobs")
~~~

- [ ] **Step 2: Run tests to verify failure**

Run: pytest tests/core/test_app.py tests/browser/test_core_client.py tests/browser/test_worker.py -k 'activity_settings or daily_jobs' -v

Expected: FAIL because models, routes, client method, and worker call are absent.

- [ ] **Step 3: Implement contracts**

~~~python
class ActivitySettingsRequest(ApiModel):
    rules: list[ActivityLevelRuleInput] = Field(min_length=10, max_length=10)
    report_times: list[str] = Field(min_length=1)

@app.post("/internal/daily-jobs/run", response_model=AcceptedResponse)
def run_daily_jobs(request: DailyJobsRequest, _: Annotated[None, Depends(authorize)]):
    repository.run_daily_jobs(request.now)
    return AcceptedResponse(accepted=True)
~~~

Keep validation in the repository. In BrowserWorker.run_once submit all new messages, run the job, then claim outbounds. Extend CorePort test doubles and HTTP client.

- [ ] **Step 4: Verify and commit**

Run: pytest tests/core/test_app.py tests/browser/test_core_client.py tests/browser/test_worker.py -k 'activity_settings or daily_jobs' -v

Expected: PASS, including unauthorized and invalid requests.

~~~bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/browser/core_client.py src/dzmm_bot/browser/worker.py tests/core/test_app.py tests/browser/test_core_client.py tests/browser/test_worker.py
git commit -m "feat: run daily activity jobs from worker"
~~~

### Task 5: Build the Admin activity settings modal

**Files:**
- Modify: src/dzmm_bot/admin/core_client.py
- Modify: src/dzmm_bot/admin/app.py
- Modify: src/dzmm_bot/admin/templates/index.html
- Modify: src/dzmm_bot/admin/static/admin.js
- Modify: src/dzmm_bot/admin/static/admin.css
- Test: tests/admin/test_app.py
- Test: tests/admin/test_static.py

**Interfaces:**
- Produces Admin GET/PATCH /api/game/activity-settings proxies.
- Produces #activity-settings-modal with ten level rows and editable/addable/removable time fields.

- [ ] **Step 1: Write failing Admin tests**

~~~python
def test_admin_proxies_activity_settings(client, headers, core):
    response = client.get("/api/game/activity-settings", headers=headers)
    assert response.status_code == 200
    assert core.activity_settings_requested is True

def test_activity_configuration_is_modal_only():
    assert 'id="edit-activity-settings"' in read_admin_html()
    assert 'id="activity-settings-modal"' in read_admin_html()
    assert "openActivitySettingsModal" in read_admin_javascript()
~~~

- [ ] **Step 2: Run tests to verify failure**

Run: pytest tests/admin/test_app.py tests/admin/test_static.py -k 'activity_settings' -v

Expected: FAIL because the Admin proxy and modal do not exist.

- [ ] **Step 3: Implement the compact view and modal-only editor**

The main settings view shows a level summary and Beijing schedule plus 编辑日活跃度. The modal owns all ten rows and schedule controls; the main page has no editable rule rows. Validate basic missing/duplicate times in the browser, rely on Core for authority, and close/reload/show a Chinese success message after saving. Support Cancel, backdrop, and Escape.

- [ ] **Step 4: Verify and commit**

Run: pytest tests/admin/test_app.py tests/admin/test_static.py -k 'activity_settings' -v

Expected: PASS; proxy calls preserve the token and only the modal owns editing.

~~~bash
git add src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/admin/test_app.py tests/admin/test_static.py
git commit -m "feat: configure daily activity rules"
~~~

### Task 6: Verify and deploy

**Files:**
- Modify: none unless a failing test identifies a scoped defect.
- Test: complete suite and production smoke checks.

- [ ] **Step 1: Run complete verification**

Run: pytest -q && git diff --check && alembic -c alembic.ini upgrade head && alembic -c alembic.ini current

Expected: all tests pass, no whitespace errors, and revision is 20260805_05.

- [ ] **Step 2: Inspect release scope**

~~~bash
git status --short
git log --oneline b85783b..HEAD
git diff --check b85783b..HEAD
~~~

Expected: only this feature’s tracked files; leave docs/HANDOFF.md untouched.

- [ ] **Step 3: Deploy through established release workflow**

Copy the committed worktree to the remote release directory, run deploy/scripts/deploy.sh, and restart Core, Admin, and Browser Worker.

Expected: services are active, production migration is 20260805_05, and no credentials are printed.

- [ ] **Step 4: Perform production smoke checks**

Use protected localhost Core/Admin checks to verify defaults. With two joined test accounts, confirm /我 and /me hide counts, normal text reaches LV1, a positive-income due slot queues once, and repeated job calls do not duplicate rewards or pushes.

Expected: correct defaults, Worker remains ready, and scheduled work is idempotent.
