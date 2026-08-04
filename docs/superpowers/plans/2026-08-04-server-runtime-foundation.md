# Server Runtime Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a durable server runtime where the browser worker is replaceable, all gameplay state is owned by a PostgreSQL-backed core, and a Web control plane can run manual login verification without a local computer.

**Architecture:** The core persists inbound/outbound messages and exposes local APIs. A browser worker calls only those APIs and owns an isolated Chrome profile; an admin Web service proxies authenticated control requests. A temporary Xvfb/noVNC session is started by the worker only for human login verification.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, psycopg 3, Alembic, httpx, Playwright, PostgreSQL 16, systemd, Xvfb, Fluxbox, x11vnc, noVNC.

## Global Constraints

- Do not modify the existing OpenClaw Chrome profile, CDP port 9222, databases, Redis, Nginx, or running services.
- Use dedicated `dzmm` Linux ownership, a dedicated PostgreSQL database/user, an isolated Chrome profile, and ports 18120, 19222, 18090, and temporary 16080 only after a collision check.
- The core is the only process that writes business tables; the browser worker must use HTTP APIs.
- Never store a group-chat password or SSH password in the database, source tree, log, or admin response.
- Keep human slider verification manual; do not automate or bypass CAPTCHA.
- The normal browser mode is headless; virtual desktop processes exist only in `auth_required` / `auth_in_progress` states.
- Maintain the existing legacy read-adapter files untouched until the foundation has passed its tests.

---

### Task 1: Repository runtime configuration and domain contracts

**Files:**
- Modify: `pyproject.toml`
- Create: `src/dzmm_bot/runtime/__init__.py`
- Create: `src/dzmm_bot/runtime/settings.py`
- Create: `src/dzmm_bot/runtime/contracts.py`
- Create: `tests/runtime/test_settings.py`
- Create: `tests/runtime/test_contracts.py`

**Interfaces:**
- Produces: `Settings.from_environment() -> Settings`, `LoginState`, `InboundMessage`, `OutboundMessage`, and `WorkerHeartbeat`.
- Consumes: `DZMM_DATABASE_URL`, `DZMM_CORE_TOKEN`, `DZMM_ADMIN_TOKEN`, `DZMM_BROWSER_PROFILE`, `DZMM_LOGIN_URL`, and port environment variables.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_settings_requires_nonempty_database_url_and_core_token(monkeypatch):
    monkeypatch.delenv("DZMM_DATABASE_URL", raising=False)
    monkeypatch.delenv("DZMM_CORE_TOKEN", raising=False)
    with pytest.raises(ValueError, match="DZMM_DATABASE_URL"):
        Settings.from_environment()

def test_settings_uses_isolated_default_browser_port(monkeypatch):
    monkeypatch.setenv("DZMM_DATABASE_URL", "postgresql+psycopg://dzmm:x@localhost/dzmm")
    monkeypatch.setenv("DZMM_CORE_TOKEN", "core-token")
    assert Settings.from_environment().browser_cdp_port == 19222
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `python3 -m pytest tests/runtime/test_settings.py -v`

Expected: FAIL because `dzmm_bot.runtime` does not exist.

- [ ] **Step 3: Add the minimal dependency and settings implementation**

Change `requires-python` from `>=3.13` to `>=3.12`, then add exact runtime dependencies `fastapi>=0.115,<1`, `uvicorn[standard]>=0.30,<1`, `sqlalchemy>=2.0,<3`, `psycopg[binary]>=3.2,<4`, `alembic>=1.13,<2`, `httpx>=0.27,<1`, and `playwright>=1.49,<2`; add `pytest>=8,<9` to a test extra. Settings must reject empty secrets, require absolute browser profile paths, and default all internal ports away from 9222.

- [ ] **Step 4: Define immutable contracts**

```python
class LoginState(StrEnum):
    READY = "ready"
    AUTH_REQUIRED = "auth_required"
    AUTH_IN_PROGRESS = "auth_in_progress"

@dataclass(frozen=True)
class InboundMessage:
    platform_message_id: str
    sender_platform_id: str
    content: str
    received_at: datetime
```

Define `OutboundMessage` with a stable UUID, `inbound_message_id`, text, status, lease expiry, attempt count, and optional platform sent ID.

- [ ] **Step 5: Run focused tests and commit**

Run: `python3 -m pytest tests/runtime/test_settings.py tests/runtime/test_contracts.py -v`

Commit: `git add pyproject.toml src/dzmm_bot/runtime tests/runtime && git commit -m "feat: add runtime contracts"`.

### Task 2: PostgreSQL schema, migrations, and core reliability service

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/versions/20260804_01_runtime_tables.py`
- Create: `src/dzmm_bot/core/__init__.py`
- Create: `src/dzmm_bot/core/database.py`
- Create: `src/dzmm_bot/core/schema.py`
- Create: `src/dzmm_bot/core/repository.py`
- Create: `src/dzmm_bot/core/service.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/core/test_service.py`

**Interfaces:**
- Produces: `CoreRepository.accept_inbound(message)`, `CoreRepository.claim_outbound(worker_id, now, lease_seconds)`, `CoreRepository.confirm_sent(message_id, platform_sent_id)`, and `CoreService.receive_inbound(message)`.
- Consumes: contracts from Task 1 and a SQLAlchemy session factory.

- [ ] **Step 1: Write the failing idempotency and lease tests**

```python
def test_duplicate_platform_message_returns_existing_record(repository, inbound):
    first, inserted = repository.accept_inbound(inbound)
    second, duplicate = repository.accept_inbound(inbound)
    assert inserted is True
    assert duplicate is False
    assert second.id == first.id

def test_expired_lease_can_be_claimed_once_by_another_worker(repository, outbound, now):
    assert repository.claim_outbound("a", now, 30).id == outbound.id
    assert repository.claim_outbound("b", now + timedelta(seconds=31), 30).id == outbound.id
    assert repository.claim_outbound("c", now + timedelta(seconds=32), 30) is None
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `python3 -m pytest tests/core/test_repository.py tests/core/test_service.py -v`

Expected: FAIL because repository and migrations are absent.

- [ ] **Step 3: Create the first Alembic revision**

Create tables `inbound_messages`, `outbound_messages`, `worker_instances`, `login_sessions`, and `audit_events`. Add a unique index on `inbound_messages.platform_message_id`; add a partial/compound query index for pending and expired outbound leases. Store timestamps in UTC.

- [ ] **Step 4: Implement transactional core operations**

```python
def receive_inbound(self, message: InboundMessage) -> ReceiveResult:
    stored, inserted = self._repository.accept_inbound(message)
    if not inserted:
        return ReceiveResult(stored.id, False)
    reply = self._command_handler.handle(message)
    if reply is not None:
        self._repository.enqueue_outbound(stored.id, reply)
    return ReceiveResult(stored.id, True)
```

All command-handler writes and `enqueue_outbound` must share the same database transaction. At this foundation stage use an explicit `NoopCommandHandler` that returns no reply; do not introduce gameplay rules.

- [ ] **Step 5: Add migration and repository integration tests**

Start an ephemeral PostgreSQL database only when `TEST_DATABASE_URL` is set; otherwise mark integration tests skipped. Assert uniqueness, atomic enqueue, lease expiry, confirmation, and worker heartbeat persistence.

- [ ] **Step 6: Run tests and commit**

Run: `python3 -m pytest tests/core -v`

Commit: `git add alembic.ini migrations src/dzmm_bot/core tests/core && git commit -m "feat: add durable core queue"`.

### Task 3: Local core HTTP API and health surface

**Files:**
- Create: `src/dzmm_bot/core/app.py`
- Create: `src/dzmm_bot/core/api_models.py`
- Create: `tests/core/test_app.py`

**Interfaces:**
- Produces:
  - `GET /healthz`
  - `POST /internal/inbound`
  - `POST /internal/outbound/claim`
  - `POST /internal/outbound/{id}/sent`
  - `POST /internal/heartbeat`
  - `GET /internal/login-state`
- Consumes: `X-Core-Token` and service methods from Task 2.

- [ ] **Step 1: Write failing HTTP authorization tests**

```python
def test_internal_inbound_rejects_missing_core_token(client, payload):
    assert client.post("/internal/inbound", json=payload).status_code == 401

def test_internal_inbound_is_idempotent(client, headers, payload):
    assert client.post("/internal/inbound", headers=headers, json=payload).json()["accepted"] is True
    assert client.post("/internal/inbound", headers=headers, json=payload).json()["accepted"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/core/test_app.py -v`

Expected: FAIL because the ASGI app is absent.

- [ ] **Step 3: Implement only the listed endpoints**

Validate input with Pydantic. Make `/healthz` report database availability and latest worker heartbeat age without leaking configuration or secrets. The API binds to `127.0.0.1:18120` only.

- [ ] **Step 4: Verify and commit**

Run: `python3 -m pytest tests/core/test_app.py tests/core -v`

Commit: `git add src/dzmm_bot/core tests/core && git commit -m "feat: expose core worker api"`.

### Task 4: Browser worker lifecycle and isolated profile

**Files:**
- Create: `src/dzmm_bot/browser/__init__.py`
- Create: `src/dzmm_bot/browser/core_client.py`
- Create: `src/dzmm_bot/browser/worker.py`
- Create: `src/dzmm_bot/browser/session.py`
- Create: `src/dzmm_bot/browser/main.py`
- Test: `tests/browser/test_worker.py`
- Test: `tests/browser/test_session.py`

**Interfaces:**
- Produces: `BrowserWorker.run_once()`, `BrowserSession.start_headless()`, `BrowserSession.stop()`, and `BrowserSession.login_state()`.
- Consumes: the core API from Task 3 and configuration from Task 1.

- [ ] **Step 1: Write failing worker tests using fake gateway and core client**

```python
def test_worker_submits_each_platform_message_once(worker, gateway, core):
    gateway.messages = [InboundMessage("p-1", "u-1", "/test", now)]
    worker.run_once()
    worker.run_once()
    assert core.submitted_ids == ["p-1"]

def test_worker_confirms_only_after_gateway_send_succeeds(worker, gateway, core):
    core.pending = [outbound]
    gateway.send_error = RuntimeError("page unavailable")
    worker.run_once()
    assert core.confirmed_ids == []
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/browser/test_worker.py tests/browser/test_session.py -v`

Expected: FAIL because browser modules are absent.

- [ ] **Step 3: Implement the worker against narrow ports**

Define a `ChatGateway` protocol: `read_new() -> list[InboundMessage]`, `send(text) -> str`, `is_authenticated() -> bool`, and `close() -> None`. The Playwright gateway is configured by `DZMM_LOGIN_URL` but does not contain platform-specific selectors until the platform page is supplied. The worker owns a profile path and launches CDP only on `127.0.0.1:19222`.

- [ ] **Step 4: Implement heartbeat, backoff, and auth-required transition**

On authentication loss, stop polling, set `auth_required` through the core API, emit one audit event, and sleep with bounded exponential backoff. Do not enqueue replies or reset profile data.

- [ ] **Step 5: Verify and commit**

Run: `python3 -m pytest tests/browser -v`

Commit: `git add src/dzmm_bot/browser tests/browser && git commit -m "feat: add isolated browser worker"`.

### Task 5: Admin Web control plane and temporary human-login console

**Files:**
- Create: `src/dzmm_bot/admin/__init__.py`
- Create: `src/dzmm_bot/admin/app.py`
- Create: `src/dzmm_bot/admin/core_client.py`
- Create: `src/dzmm_bot/admin/templates/index.html`
- Create: `src/dzmm_bot/admin/static/admin.js`
- Create: `src/dzmm_bot/auth_desktop.py`
- Test: `tests/admin/test_app.py`
- Test: `tests/admin/test_auth_desktop.py`

**Interfaces:**
- Produces:
  - `GET /healthz`
  - `GET /api/status`
  - `POST /api/worker/{start|stop|restart}`
  - `POST /api/login/start`
  - `POST /api/login/finish`
  - `GET /login-console`
- Consumes: `X-Admin-Token`, local core API, and an `AuthDesktopController`.

- [ ] **Step 1: Write failing admin authorization and lifecycle tests**

```python
def test_status_requires_admin_token(client):
    assert client.get("/api/status").status_code == 401

def test_login_start_creates_console_only_when_auth_required(client, headers, controller):
    controller.core_login_state = "auth_required"
    response = client.post("/api/login/start", headers=headers)
    assert response.status_code == 202
    assert controller.started is True
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/admin -v`

Expected: FAIL because admin modules are absent.

- [ ] **Step 3: Implement minimal admin HTML and proxy endpoints**

Serve one status page with explicit state, last heartbeat, queue counts, and buttons for the listed actions. Use `X-Admin-Token` in a password-gated browser session. Do not render credentials, profile paths, raw cookies, or raw inbound message history.

- [ ] **Step 4: Implement authentication desktop process control**

```python
class AuthDesktopController:
    def start(self) -> None:
        # Require auth_required and stopped browser worker.
        # Spawn Xvfb, Fluxbox, Chrome with the isolated profile, x11vnc, and noVNC.
    def stop(self) -> None:
        # Stop only PIDs created by this controller, then restart headless worker.
```

Use a PID file inside the dedicated runtime directory, an `asyncio.Lock`, and exact child process groups. noVNC listens only on `127.0.0.1:16080`; admin proxies `/login-console` while the login state is `auth_in_progress`. Never implement click/drag automation.

- [ ] **Step 5: Verify and commit**

Run: `python3 -m pytest tests/admin -v`

Commit: `git add src/dzmm_bot/admin src/dzmm_bot/auth_desktop.py tests/admin && git commit -m "feat: add admin login control"`.

### Task 6: Server provisioning, systemd isolation, and live smoke test

**Files:**
- Create: `deploy/requirements-server.txt`
- Create: `deploy/env/dzmm.example.env`
- Create: `deploy/systemd/dzmm-core.service`
- Create: `deploy/systemd/dzmm-browser-worker.service`
- Create: `deploy/systemd/dzmm-admin-web.service`
- Create: `deploy/scripts/preflight.sh`
- Create: `deploy/scripts/provision.sh`
- Create: `deploy/scripts/deploy.sh`
- Create: `deploy/scripts/verify-runtime.sh`
- Test: `tests/deploy/test_unit_files.py`

**Interfaces:**
- Produces: three services running under `dzmm` user and an explicit preflight report.
- Consumes: a manually created PostgreSQL DSN and admin/core tokens stored in `/etc/dzmm/dzmm.env` with mode 0600.

- [ ] **Step 1: Write failing deployment artifact tests**

```python
def test_core_unit_isolated_from_public_network_and_existing_cdp():
    text = Path("deploy/systemd/dzmm-core.service").read_text()
    assert "--host 127.0.0.1" in text
    assert "9222" not in text
    assert "User=dzmm" in text
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/deploy/test_unit_files.py -v`

Expected: FAIL because deployment artifacts are absent.

- [ ] **Step 3: Implement non-destructive preflight**

`preflight.sh` must check: Ubuntu release, available disk >= 8GB, available memory >= 1GB, PostgreSQL service, package availability, exact ports, `/root/.openclaw` untouched, and absence of an existing `dzmm` Linux user/project path. It must make no changes.

- [ ] **Step 4: Implement explicit provisioning and units**

`provision.sh` must require a typed `--apply` flag, create only the `dzmm` system user, `/opt/dzmm`, `/var/lib/dzmm-browser`, `/var/log/dzmm`, and `/etc/dzmm`; install the listed packages; create a new PostgreSQL role/database; then install unit files. It must never alter existing PostgreSQL users/databases or any existing service.

- [ ] **Step 5: Run repository verification then server preflight**

Run locally: `python3 -m pytest -v`

Run on server: `sudo /opt/dzmm/current/deploy/scripts/preflight.sh`

Expected: repository tests pass; preflight reports the exact required packages and free resources without making changes.

- [ ] **Step 6: Deploy only after preflight report is reviewed**

Run: `sudo /opt/dzmm/current/deploy/scripts/provision.sh --apply`, then deploy the code, create `/etc/dzmm/dzmm.env` interactively, enable the three units, and run `verify-runtime.sh`. Verify that all three health checks are green, no port conflicts exist, and existing services remain active.

- [ ] **Step 7: Final live smoke test**

With `DZMM_LOGIN_URL` set to the real platform login page, open the admin URL, verify `auth_required`, start the temporary console, manually complete one login, finish the console, and confirm the Worker reports `ready`. Do not send group messages in this test.

- [ ] **Step 8: Commit**

Commit: `git add deploy tests/deploy && git commit -m "feat: add isolated server deployment"`.
