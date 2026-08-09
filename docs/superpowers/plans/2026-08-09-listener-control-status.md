# Persistent Listener Control and Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the administrator's listener choice, restore it after Browser Worker or server restarts, and expose the actual listener state and controls in the admin console.

**Architecture:** Store both the administrator's desired state and the Worker's actual state on `worker_instances`. The heartbeat reports actual state and returns desired state so the Core remains authoritative across restarts. Existing durable pause/resume commands remain the immediate control path, while the heartbeat provides convergence after failures or restarts.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL/SQLite tests, vanilla JavaScript, HTML/CSS, pytest.

## Global Constraints

- Both the enabled and paused choices survive Browser Worker and server restarts.
- Authentication recovery enables reading only when `listening_desired` is true.
- Existing `/api/worker/start` and `/api/worker/stop` routes and administrator permissions remain unchanged.
- Do not alter DeepSeek, message rules, outbound delivery, or manual login behavior.
- Preserve all unrelated uncommitted Bot API changes and stage only listener-control hunks.

---

### Task 1: Persist desired and actual listener state

**Files:**
- Create: `migrations/versions/20260809_29_listener_control.py`
- Modify: `src/dzmm_bot/runtime/contracts.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/app.py`
- Test: `tests/runtime/test_contracts.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_app.py`

**Interfaces:**
- `WorkerHeartbeat(worker_id, login_state, recorded_at, listening=True)` reports actual state.
- `HeartbeatResponse.listening` reports actual state and `HeartbeatResponse.listening_desired` returns the persisted target.
- `CoreRepository.enqueue_worker_command(command)` updates `listening_desired` only for `pause_listening` and `resume_listening` in the same transaction.

- [ ] **Step 1: Write failing contract, repository, and API tests**

```python
def test_listener_choice_survives_later_heartbeats(repository, now):
    repository.record_worker_heartbeat(
        WorkerHeartbeat("worker-a", LoginState.READY, now, listening=True)
    )
    repository.enqueue_worker_command("pause_listening")
    updated = repository.record_worker_heartbeat(
        WorkerHeartbeat(
            "worker-a",
            LoginState.AUTH_REQUIRED,
            now + timedelta(seconds=5),
            listening=False,
        )
    )
    assert updated.listening is False
    assert updated.listening_desired is False
```

Extend the heartbeat and aggregate-status API expectations with:

```python
"listening": False,
"listening_desired": False,
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/runtime/test_contracts.py tests/core/test_repository.py tests/core/test_app.py
```

Expected: failures show missing heartbeat fields, schema columns, and status fields.

- [ ] **Step 3: Add the migration and minimal persistence implementation**

The migration adds non-null booleans with a true server default:

```python
op.add_column(
    "worker_instances",
    sa.Column("listening", sa.Boolean(), server_default=sa.true(), nullable=False),
)
op.add_column(
    "worker_instances",
    sa.Column(
        "listening_desired", sa.Boolean(), server_default=sa.true(), nullable=False
    ),
)
```

The heartbeat upsert updates `listening` but never overwrites `listening_desired`. Enqueuing pause/resume updates the latest Worker row's desired value to false/true before inserting the durable command. Other commands leave the value unchanged.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit only Task 1 hunks**

```bash
git add migrations/versions/20260809_29_listener_control.py \
  src/dzmm_bot/runtime/contracts.py src/dzmm_bot/core/schema.py
git add -p src/dzmm_bot/core/api_models.py src/dzmm_bot/core/repository.py \
  src/dzmm_bot/core/app.py tests/core/test_repository.py
git add tests/runtime/test_contracts.py tests/core/test_app.py
git commit -m "feat: persist listener control state"
```

### Task 2: Converge Browser Worker state through heartbeats

**Files:**
- Modify: `src/dzmm_bot/browser/core_client.py`
- Modify: `src/dzmm_bot/browser/worker.py`
- Test: `tests/browser/test_core_client.py`
- Test: `tests/browser/test_worker.py`

**Interfaces:**
- `CorePort.heartbeat(worker_id, login_state, listening, recorded_at) -> bool` returns `listening_desired`.
- `BrowserWorker.listening` exposes the actual state for testing and heartbeat construction.

- [ ] **Step 1: Write failing Browser Worker and Core client tests**

Add a transport test asserting the request and response contract:

```python
desired = client.heartbeat("worker-a", LoginState.READY, True, now)
assert observed["payload"]["listening"] is True
assert desired is False
```

Add restart/recovery behavior tests:

```python
def test_worker_applies_persisted_pause_after_restart(context):
    worker, gateway, _, _, core, _ = context
    core.listening_desired = False
    gateway.messages = [InboundMessage("p-1", "u-1", "/打卡", NOW)]
    worker.run_once()
    assert core.submitted_ids == []
    assert core.heartbeats[-1][2] is False

def test_worker_resumes_after_authentication_when_desired(context):
    worker, gateway, _, _, core, _ = context
    core.listening_desired = True
    gateway.read_error = RuntimeError("temporary socket failure")
    worker.run_once()
    gateway.read_error = None
    gateway.messages = [InboundMessage("p-2", "u-1", "/打卡", NOW)]
    worker.run_once()
    assert core.submitted_ids == ["p-2"]
```

- [ ] **Step 2: Run focused tests and verify RED**

```bash
.venv/bin/pytest -q tests/browser/test_core_client.py tests/browser/test_worker.py
```

Expected: heartbeat signature/return and persisted pause tests fail.

- [ ] **Step 3: Implement minimal heartbeat convergence**

Send the actual state in every heartbeat and apply the returned target before reading messages. Keep a distinct `_listening_paused` flag for local command behavior, but replace it with the Core's returned desired state on every successful heartbeat:

```python
desired = self._core.heartbeat(
    self._worker_id,
    self._login_state,
    self._listening,
    self._clock(),
)
self._listening_paused = not desired
self._listening = desired and self._login_state is LoginState.READY
```

Authentication recovery must use `not self._listening_paused`, never unconditional `True`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit only Task 2 hunks**

```bash
git add -p src/dzmm_bot/browser/core_client.py src/dzmm_bot/browser/worker.py \
  tests/browser/test_core_client.py tests/browser/test_worker.py
git commit -m "fix: restore persisted listener state"
```

### Task 3: Expose listener status and controls in the admin console

**Files:**
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- `/api/status` returns safe `listening` and `listening_desired` fields.
- `#listener-state`, `#listener-help`, `#start-listening`, and `#pause-listening` are stable UI selectors.

- [ ] **Step 1: Write failing admin API and asset tests**

Extend `test_status_returns_only_safe_operational_fields` to require both listener fields. Extend the index test with assertions that the old adapter warning and disabled action wrapper are absent and the four stable selectors are present.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
.venv/bin/pytest -q tests/admin/test_app.py
```

Expected: listener fields and enabled UI controls are missing.

- [ ] **Step 3: Implement the status panel and control behavior**

Replace the old disabled block with a live region:

```html
<div class="listener-status" aria-live="polite">
  <span id="listener-state" class="status-badge">状态未知</span>
  <p id="listener-help" class="muted">等待 Worker 心跳。</p>
</div>
<div class="listener-actions">
  <button id="start-listening" data-action="/api/worker/start" type="button">开始监听</button>
  <button id="pause-listening" data-action="/api/worker/stop" type="button">暂停监听</button>
</div>
```

Render four states:

- listening: green badge, start disabled, pause enabled;
- paused: warning badge, start enabled, pause disabled;
- waiting: warning badge, start disabled, pause enabled;
- unknown: neutral badge, both disabled.

Use the existing mutation and refresh helpers; add busy labels `开启中…` and `暂停中…` and refresh after command submission.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all admin tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/dzmm_bot/admin/app.py src/dzmm_bot/admin/templates/index.html \
  src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css \
  tests/admin/test_app.py
git commit -m "feat: add admin listener controls"
```

### Task 4: Full verification and production deployment

**Files:**
- Verify only; no new implementation files expected.

**Interfaces:**
- Production admin URL: `http://<production-host>:18090`.
- Production services: Core, Admin Web, Browser Worker, and AI Worker.

- [ ] **Step 1: Run migration and full automated verification locally**

```bash
.venv/bin/alembic -c alembic.ini upgrade head
.venv/bin/pytest -q
git diff --check
```

Expected: migration reaches `20260809_29`, all tests pass, and no whitespace errors are reported.

- [ ] **Step 2: Review staged/committed scope**

```bash
git status --short
git log --oneline -6
git diff HEAD~3..HEAD --stat
```

Expected: existing Bot API work remains uncommitted; listener commits contain only files and hunks from Tasks 1–3.

- [ ] **Step 3: Deploy with the existing release script**

Deploy a clean archive of the listener commits, run Alembic before service restart through `deploy/scripts/deploy.sh`, and do not copy local `.env` into the release.

- [ ] **Step 4: Verify services, status API, and admin UI**

Confirm all four systemd services are active, migration head is `20260809_29`, `/healthz` succeeds on ports 18090 and 18120, and `/api/status` reports both listener fields without secret fields.

Open the 18090 admin page and verify the listener badge, explanation, and buttons render correctly in listening, paused, and resumed states.

- [ ] **Step 5: Verify behavior without losing administrator intent**

Pause from the admin page, restart Browser Worker, and verify the status remains paused. Start from the admin page, restart Browser Worker, and verify it returns to listening. Finally submit a new harmless chat command and verify it enters Core and receives a reply.
