# 管理员账号与人工登录互斥 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** 让超级管理员管理普通管理员账号，并让人工登录在三分钟内只由一名管理员操作、可被任意管理员中断且能自动恢复 Worker。

**Architecture:** 管理员账户、会话与幂等结果在 PostgreSQL 持久化；管理 Web 验证身份和角色。人工登录租约与 Worker 命令在核心服务同一事务中写入。可编辑配置保存版本号，避免多人静默覆盖。

**Tech Stack:** FastAPI、SQLAlchemy 2、Alembic、PostgreSQL、hashlib.scrypt、原生 JavaScript、pytest。

## Global Constraints

- DZMM_ADMIN_TOKEN 保留为超级管理员 Token，普通管理员不使用它。
- 所有时间使用 Asia/Shanghai 的 BeijingDateTime 与 beijing_now()。
- 密码保存随机盐 scrypt 哈希；会话令牌与幂等键仅保存 SHA-256 哈希。
- 查询接口允许并发；POST/PATCH/DELETE 必须有 Idempotency-Key。
- 玩法配置保存必须携带版本；版本不一致返回 HTTP 409。
- 人工登录租约固定 180 秒、不续期；任意已认证管理员可以中断。

---

### Task 1: 持久化管理员身份、会话与幂等结果

**Files:**
- Modify: src/dzmm_bot/core/schema.py
- Create: src/dzmm_bot/admin/repository.py
- Create: migrations/versions/20260805_06_admin_accounts.py
- Create: tests/admin/test_repository.py

**Interfaces:**
- Produces AdminRepository(session_factory) with create_account, list_accounts, set_account_active, reset_password, delete_account, authenticate, create_session, resolve_session, revoke_account_sessions, reserve_idempotency_key, complete_idempotency_key.
- Produces AdminIdentity(account_id: UUID | None, username: str, role: Literal["super_admin", "admin"]).

- [ ] **Step 1: Write failing repository tests**

~~~python
def test_admin_account_passwords_and_sessions_are_revoked(tmp_path):
    repository = AdminRepository(create_session_factory(f"sqlite:///{tmp_path / 'admin.db'}"))
    account = repository.create_account("alice", "strong-password")
    assert repository.authenticate("alice", "strong-password") == account

    token = repository.create_session(account.id, beijing_now())
    repository.set_account_active(account.id, False)
    assert repository.resolve_session(token, beijing_now()) is None


def test_same_idempotency_key_returns_one_completed_result(tmp_path):
    repository = AdminRepository(create_session_factory(f"sqlite:///{tmp_path / 'admin.db'}"))
    assert repository.reserve_idempotency_key("super_admin", "key-1", beijing_now()) is None
    repository.complete_idempotency_key("super_admin", "key-1", 201, {"id": "item-1"})
    assert repository.reserve_idempotency_key("super_admin", "key-1", beijing_now()) == (201, {"id": "item-1"})
~~~

- [ ] **Step 2: Run the test**

Run: .venv/bin/pytest -q tests/admin/test_repository.py

Expected: FAIL because AdminRepository and the tables do not exist.

- [ ] **Step 3: Implement minimal storage**

Add AdminAccountRecord, AdminSessionRecord, and AdminIdempotencyRecord with unique username, token hash, and actor/key constraints. Implement a scrypt$<salt>$<digest> format, twelve-hour session expiry, one-hour successful idempotency replay, and session revocation when an account is disabled or deleted.

- [ ] **Step 4: Verify and commit**

Run: .venv/bin/pytest -q tests/admin/test_repository.py

Expected: PASS.

~~~bash
git add src/dzmm_bot/core/schema.py src/dzmm_bot/admin/repository.py migrations/versions/20260805_06_admin_accounts.py tests/admin/test_repository.py
git commit -m "feat: add administrator account storage"
~~~

### Task 2: 核心服务的三分钟人工登录租约

**Files:**
- Modify: src/dzmm_bot/core/schema.py
- Modify: src/dzmm_bot/core/repository.py
- Modify: src/dzmm_bot/core/api_models.py
- Modify: src/dzmm_bot/core/app.py
- Modify: src/dzmm_bot/admin/core_client.py
- Modify: migrations/versions/20260805_06_admin_accounts.py
- Test: tests/core/test_repository.py
- Test: tests/core/test_app.py

**Interfaces:**
- Produces start_manual_login(actor_id, actor_name, now), finish_manual_login(actor_id, now), cancel_manual_login(now), and manual_login_lease(now).
- Produces POST /internal/admin/login/start, POST /internal/admin/login/finish, POST /internal/admin/login/cancel, and GET /internal/admin/login/lease.
- Lease payload is {operator_name, expires_at, remaining_seconds} or null.

- [ ] **Step 1: Write the failing lease test**

~~~python
def test_manual_login_lease_is_exclusive_and_expires(repository):
    now = datetime(2026, 8, 5, 12, tzinfo=BEIJING)
    repository.start_manual_login("alice-id", "alice", now)

    with pytest.raises(ManualLoginBusyError):
        repository.start_manual_login("bob-id", "bob", now)

    assert repository.manual_login_lease(now + timedelta(seconds=181)) is None
    assert repository.claim_worker_command("worker", now + timedelta(seconds=181), 30).command == "cancel_auth"
~~~

- [ ] **Step 2: Run the test**

Run: .venv/bin/pytest -q tests/core/test_repository.py -k manual_login

Expected: FAIL because the lease API does not exist.

- [ ] **Step 3: Implement the singleton lease**

Add a manual_login_leases singleton with primary key 1, operator ID/name, and expiry. Lock it in one transaction, reject a live lease, create the lease, and enqueue start_auth. Expiry/cancel delete the lease and enqueue only one cancel_auth. Trigger expiry from record_worker_heartbeat. Finish requires matching operator ID, deletes the lease, and enqueues finish_auth. Map busy, wrong owner, and wrong login state to HTTP 409. Extend AdminCorePort and CoreClient.

- [ ] **Step 4: Verify and commit**

Run: .venv/bin/pytest -q tests/core/test_repository.py tests/core/test_app.py -k manual_login

Expected: PASS.

~~~bash
git add src/dzmm_bot/core/schema.py src/dzmm_bot/core/repository.py src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/admin/core_client.py migrations/versions/20260805_06_admin_accounts.py tests/core/test_repository.py tests/core/test_app.py
git commit -m "feat: add exclusive manual login lease"
~~~

### Task 3: Worker 安全取消人工登录

**Files:**
- Modify: src/dzmm_bot/browser/worker.py
- Test: tests/browser/test_worker.py

**Interfaces:**
- Consumes a WorkerCommand whose command equals cancel_auth.
- Produces a worker with stopped desktop, no active gateway, and AUTH_REQUIRED state.

- [ ] **Step 1: Write the failing worker test**

~~~python
def test_cancel_auth_closes_desktop_and_returns_to_auth_required(context):
    worker, _, _, desktop, _ = context
    worker._login_state = LoginState.AUTH_IN_PROGRESS
    worker._execute_command(WorkerCommand(uuid4(), "cancel_auth", uuid4()))
    assert desktop.stops == 1
    assert worker.login_state is LoginState.AUTH_REQUIRED
~~~

- [ ] **Step 2: Run the test**

Run: .venv/bin/pytest -q tests/browser/test_worker.py -k cancel_auth

Expected: FAIL because cancel_auth is unsupported.

- [ ] **Step 3: Implement the command branch**

Stop the isolated desktop, clear the gateway, clear manual-auth confirmation, and call _transition_to_auth_required(). Do not add a second recovery loop: the existing next run_once starts headless Chrome from its persistent profile.

- [ ] **Step 4: Verify and commit**

Run: .venv/bin/pytest -q tests/browser/test_worker.py

Expected: PASS.

~~~bash
git add src/dzmm_bot/browser/worker.py tests/browser/test_worker.py
git commit -m "feat: recover worker after cancelled manual login"
~~~

### Task 4: 管理 Web 身份、角色与写接口保护

**Files:**
- Modify: src/dzmm_bot/admin/app.py
- Modify: src/dzmm_bot/admin/core_client.py
- Test: tests/admin/test_app.py

**Interfaces:**
- POST /api/auth/login accepts {username, password}, returns {session_token, username, role}.
- GET /api/auth/me returns identity; POST /api/auth/logout revokes an ordinary session.
- Super-only: GET/POST /api/admins, PATCH /api/admins/{id}, DELETE /api/admins/{id}.
- POST /api/login/start, /finish, /cancel, GET /api/login/lease accept both roles; noVNC accepts only lease owner.

- [ ] **Step 1: Write failing API permission tests**

~~~python
def test_regular_admin_cannot_manage_administrators(client, admin_headers):
    assert client.get("/api/admins", headers=admin_headers).status_code == 403


def test_any_admin_can_cancel_manual_login(client, admin_headers, core):
    core.login_state_value = "auth_in_progress"
    response = client.post("/api/login/cancel", headers=admin_headers)
    assert response.status_code == 202
    assert core.commands[-1] == "cancel_auth"
~~~

- [ ] **Step 2: Run the test**

Run: .venv/bin/pytest -q tests/admin/test_app.py -k "regular_admin or cancel_manual_login"

Expected: FAIL because ordinary sessions and cancellation routes do not exist.

- [ ] **Step 3: Implement identity dependencies and guards**

Refactor authorize into current_identity, accepting exactly one of X-Admin-Token and X-Admin-Session; add require_super_admin. Construct AdminRepository from settings.database_url. For every public mutation, reserve Idempotency-Key, replay completed result, return 409 for a running key, and cache successful results. Login console and its iframe cookie require a valid identity that owns the lease.

- [ ] **Step 4: Verify and commit**

Run: .venv/bin/pytest -q tests/admin/test_app.py

Expected: PASS.

~~~bash
git add src/dzmm_bot/admin/app.py src/dzmm_bot/admin/core_client.py tests/admin/test_app.py
git commit -m "feat: add administrator authentication and access control"
~~~

### Task 5: 版本化玩法配置和管理端体验

**Files:**
- Modify: src/dzmm_bot/core/schema.py
- Modify: src/dzmm_bot/core/repository.py
- Modify: src/dzmm_bot/core/api_models.py
- Modify: src/dzmm_bot/core/app.py
- Modify: src/dzmm_bot/admin/templates/index.html
- Modify: src/dzmm_bot/admin/static/admin.js
- Modify: src/dzmm_bot/admin/static/admin.css
- Test: tests/core/test_app.py
- Test: tests/admin/test_app.py

**Interfaces:**
- Editable game responses expose version: int; PATCH request models include version.
- GET /api/login/lease provides lease state.
- UI keeps loaded versions, sends them with saves, and keeps form input on 409.

- [ ] **Step 1: Write failing version/UI tests**

~~~python
def test_stale_game_settings_version_is_rejected(client, headers):
    current = client.get("/internal/game/settings", headers=headers).json()
    client.patch("/internal/game/settings", headers=headers, json={**current, "checkin_reward": 6})
    assert client.patch("/internal/game/settings", headers=headers, json={**current, "checkin_reward": 7}).status_code == 409


def test_dashboard_exposes_admins_and_login_countdown(client):
    page = client.get("/").text
    assert 'id="admins-view"' in page
    assert 'id="login-countdown"' in page
    assert 'id="cancel-login"' in page
~~~

- [ ] **Step 2: Run the test**

Run: .venv/bin/pytest -q tests/core/test_app.py tests/admin/test_app.py -k "stale_game_settings or login_countdown"

Expected: FAIL because versions and UI elements do not exist.

- [ ] **Step 3: Implement versions and UI**

Add versions to command definitions, reply templates, and game settings; use an activity-settings singleton revision. Increment only after matching supplied version. Add ordinary-admin and super-token login forms, sessionStorage identity, header identity, and a super-only administrator menu. Poll status and lease every ten seconds, update countdown once per second, clear iframe on lease removal, show cancel-login to all authenticated identities, and allow only the operator to open/finish login. Every frontend mutation supplies a UUID Idempotency-Key and retries reuse its key.

- [ ] **Step 4: Verify and commit**

Run: .venv/bin/pytest -q tests/core/test_app.py tests/admin/test_app.py

Expected: PASS.

~~~bash
git add src/dzmm_bot/core/schema.py src/dzmm_bot/core/repository.py src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/core/test_app.py tests/admin/test_app.py
git commit -m "feat: add versioned multi-admin console"
~~~

### Task 6: 完整回归与部署

- [ ] **Step 1: Run full regression**

Run: .venv/bin/pytest -q

Expected: all tests pass; only documented skipped tests remain.

- [ ] **Step 2: Verify production entrypoint and desktop controller**

Run: .venv/bin/pytest -q tests/runtime/test_production_entrypoints.py tests/admin/test_auth_desktop.py

Expected: PASS.

- [ ] **Step 3: Deploy and verify production**

Deploy through the existing rsync release script, run the migration, restart dzmm-core, dzmm-admin-web, and dzmm-browser-worker. Verify all three service states are active. Use authenticated API checks to prove normal-admin login, lease status, idempotency replay, and 403 from /api/admins for a normal administrator.
