# Minimax AI 总监事 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Add an administrator-configured Minimax-powered group AI assistant that responds only to ordinary @总监事 内容 messages through the existing durable outbound queue.

**Architecture:** The core remains the only writer of business data. It detects eligible, unhandled group mentions after existing command and game processing, atomically consumes the user's Beijing-day quota, and persists an AI request. A separate dzmm-ai-worker claims requests with leases, calls Minimax's OpenAI-compatible chat endpoint, and submits either the model text or a controlled failure back to the core; the existing browser worker then delivers it.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy/Alembic, PostgreSQL/SQLite, httpx, vanilla JavaScript admin UI, systemd, pytest.

## Global Constraints

- All date boundaries, persistent timestamps, quotas, and reset calculations use Beijing time.
- AI applies only to non-empty normal group mentions matching @总监事 内容; v1 does not read or answer private messages.
- Existing slash commands, economy, games, random-event flow, and event command restrictions always run before AI detection.
- Unregistered senders receive the existing /入职 名字 guidance and never create an AI request.
- Default daily quota is LV1–LV10 = 1–10 calls respectively; 核心董事会 = 10 calls. Administrators may change every value.
- AI is seeded disabled; it becomes callable only after an administrator enables it.
- The Minimax key comes from DZMM_MINIMAX_API_KEY; the server environment also supplies DZMM_MINIMAX_MODEL and may override DZMM_MINIMAX_BASE_URL. No secret is stored, returned, logged, or staged.
- Failed, timed-out, empty, or invalid model responses use the configured fallback and do not refund a consumed quota.
- The immutable system guardrail precedes the configured system prompt and persona and prohibits command execution, economy/game rulings, fabricated state, and instructions unrelated to the current mention.
- AI output enters the existing outbound queue and uses its existing platform message splitting; the browser worker never accesses Minimax credentials.
- Do not stage or modify the local .env file.

---

## File Structure

- src/dzmm_bot/runtime/settings.py: explicit Minimax runtime settings.
- src/dzmm_bot/core/schema.py: assistant settings, rank quotas, daily usage, and leaseable requests.
- migrations/versions/20260808_27_minimax_ai_assistant.py: schema and seed data.
- src/dzmm_bot/core/repository.py: atomic quota/request creation, claims, completion/failure, and settings CRUD.
- src/dzmm_bot/core/service.py: post-command group-mention routing.
- src/dzmm_bot/core/api_models.py and src/dzmm_bot/core/app.py: internal admin and worker APIs.
- src/dzmm_bot/ai/{client,core_client,worker,main}.py: provider client and independent queue worker.
- deploy/systemd/dzmm-ai-worker.service, deploy/env/dzmm.example.env, deploy/scripts/deploy.sh: deployment support.
- src/dzmm_bot/admin/{core_client,app}.py, admin/templates/index.html, admin/static/{admin.js,admin.css}: AI 总监事 configuration view.
- rule.md: global product rules.
- tests/runtime/test_settings.py, tests/core/test_{repository,service,app}.py, tests/admin/test_app.py, tests/deploy/test_artifacts.py, tests/ai/test_{client,worker}.py: regression coverage.

### Task 1: Persist assistant configuration, Beijing quotas, and the durable request queue

**Files:**
- Modify: src/dzmm_bot/core/schema.py
- Create: migrations/versions/20260808_27_minimax_ai_assistant.py
- Modify: tests/core/test_repository.py

**Interfaces:**
- Produces AIAssistantSettingsRecord, AIRankQuotaRecord, DailyAIUsageRecord, and AIRequestRecord.
- Produces revision 20260808_27 with down_revision = "20260807_26".
- AIRequestRecord.inbound_message_id is unique; DailyAIUsageRecord is unique by (user_id, usage_date).

- [ ] **Step 1: Write failing persistence tests**

~~~python
def test_ai_request_is_unique_for_one_inbound_message(repository, inbound_id, user):
    repository.create_ai_request(inbound_id, user.platform_id, BEIJING_NOW)
    with pytest.raises(IntegrityError):
        repository.create_ai_request(inbound_id, user.platform_id, BEIJING_NOW)

def test_daily_ai_usage_is_separate_for_each_beijing_date(repository, user):
    assert repository.consume_ai_quota(user.platform_id, date(2026, 8, 8), 1)
    assert repository.consume_ai_quota(user.platform_id, date(2026, 8, 9), 1)
~~~

- [ ] **Step 2: Verify the tests fail before implementation**

Run: pytest tests/core/test_repository.py -k "ai_request or daily_ai" -v  
Expected: FAIL because the tables and repository methods do not exist.

- [ ] **Step 3: Add minimal records and the migration**

Create a singleton settings row with enabled, persona, system_prompt, over_limit_reply, failure_reply, max_response_chars, and timeout_seconds. Create rank quota rows, daily user/date counters, and queue rows with inbound/user foreign keys, status, worker lease fields, attempt count, controlled failure summary, and timestamps.

Seed the assistant disabled with a 美女总监事 persona, maximum response chars 600, timeout 20, and rank quotas in existing rank order: 1,2,3,4,5,6,7,8,9,10,10.

- [ ] **Step 4: Verify persistence**

Run: pytest tests/core/test_repository.py -k "ai_request or daily_ai" -v && git diff --check  
Expected: PASS and no whitespace errors.

- [ ] **Step 5: Commit**

~~~bash
git add src/dzmm_bot/core/schema.py migrations/versions/20260808_27_minimax_ai_assistant.py tests/core/test_repository.py
git commit -m "feat: persist minimax assistant requests"
~~~

### Task 2: Implement atomic quota/request transitions and lease-fenced finalization

**Files:**
- Modify: src/dzmm_bot/core/repository.py
- Modify: tests/core/test_repository.py

**Interfaces:**
- Produces AIAssistantSettings, AIRankQuota, ClaimedAIRequest, and AIEnqueueResult.
- Produces try_enqueue_ai_request(...), claim_ai_request(...), complete_ai_request(...), and fail_ai_request(...).

- [ ] **Step 1: Write failing transactional tests**

~~~python
def test_quota_is_consumed_only_until_rank_limit(repository, registered_user):
    repository.set_ai_rank_quota(registered_user.rank_id, 1)
    first = repository.try_enqueue_ai_request(_inbound("a"), registered_user.platform_id, "你好", BEIJING_NOW)
    second = repository.try_enqueue_ai_request(_inbound("b"), registered_user.platform_id, "你好", BEIJING_NOW)
    assert first.state == "queued"
    assert second.state == "over_limit"

def test_completed_request_enqueues_one_outbound(repository, registered_user):
    request = _queued_ai_request(repository, registered_user)
    claimed = repository.claim_ai_request("ai-1", BEIJING_NOW, 90)
    assert repository.complete_ai_request(claimed.id, "ai-1", claimed.lease_token, "收到", BEIJING_NOW)
    assert [row.text for row in repository.list_pending_outbound()] == ["收到"]
~~~

- [ ] **Step 2: Verify failures**

Run: pytest tests/core/test_repository.py -k "ai_quota or ai_request" -v  
Expected: FAIL because enqueue, claim, and completion transitions are absent.

- [ ] **Step 3: Implement the minimal state machine**

In one transaction, resolve the joined user and rank quota, derive now.astimezone(BEIJING).date(), and increment only while used_count < daily_limit. Return exactly disabled, not_joined, over_limit, queued, or duplicate.

Claim only pending or expired leased work, then set random lease token/expiry and increment attempt count. Completion/failure requires matching request id, worker id, and lease token; duplicate callbacks create no second outbound. Successful completion calls the existing enqueue_outbound(inbound_message_id, result_text, 0); failure queues the configured fallback. No normal provider error retries occur.

Build the system prompt only at claim time in this order: IMMUTABLE_AI_GUARDRAIL, trimmed administrator system prompt, then "你的人设：" + trimmed persona. ClaimedAIRequest exposes only request id, lease token, system prompt, current mention text, response limit, and timeout—never an API key.

- [ ] **Step 4: Verify transitions**

Run: pytest tests/core/test_repository.py -k "ai_quota or ai_request" -v  
Expected: PASS for Beijing rollover, disabled/not-joined/over-limit, idempotency, lease fencing, and failure without refund.

- [ ] **Step 5: Commit**

~~~bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: queue assistant requests with rank quotas"
~~~

### Task 3: Route only eligible, unhandled group mentions into the AI queue

**Files:**
- Modify: src/dzmm_bot/core/service.py
- Modify: tests/core/test_service.py
- Modify: tests/core/test_group_commands.py

**Interfaces:**
- is_ai_mention(content: str) -> str | None returns trimmed text only for a non-empty exact @总监事 prefix.
- CoreService.receive_inbound() creates an AI request only after existing command/event routing produces no reply.

- [ ] **Step 1: Write failing priority tests**

~~~python
def test_command_does_not_enqueue_ai_even_when_it_mentions_bot(service, repository):
    service.receive_inbound(_message("/帮助 @总监事", "m1"))
    assert repository.pending_ai_request_count() == 0

def test_normal_group_mention_queues_ai_after_unhandled_command_route(service, repository):
    service.receive_inbound(_message("@总监事 今天适合摸鱼吗？", "m2"))
    assert repository.pending_ai_request_count() == 1

def test_empty_bot_mention_does_not_consume_quota(service, repository):
    service.receive_inbound(_message("@总监事   ", "m3"))
    assert repository.daily_ai_used_count(_user_id(), date(2026, 8, 8)) == 0
~~~

- [ ] **Step 2: Verify failures**

Run: pytest tests/core/test_service.py tests/core/test_group_commands.py -k "ai or mention" -v  
Expected: FAIL because no mention route exists.

- [ ] **Step 3: Add the route without changing existing authority**

Keep this ordering: persist inbound → activity → valid random-event round → event block → group command handler → command replies. Only if command handling returned None and no event block applied, parse the exact mention. For not_joined, enqueue onboarding guidance; for over_limit, enqueue settings.over_limit_reply; for disabled, do nothing; for queued/duplicate, do not create a synchronous reply.

Do not send ordinary text, bare/embedded mentions, slash commands, participant dialogue, or observer-valid bracket dialogue to Minimax.

- [ ] **Step 4: Verify core regressions**

Run: pytest tests/core/test_service.py tests/core/test_group_commands.py -v  
Expected: PASS, including current event/game command precedence.

- [ ] **Step 5: Commit**

~~~bash
git add src/dzmm_bot/core/service.py tests/core/test_service.py tests/core/test_group_commands.py
git commit -m "feat: route group mentions to assistant queue"
~~~

### Task 4: Expose authenticated configuration and worker lease APIs

**Files:**
- Modify: src/dzmm_bot/core/api_models.py
- Modify: src/dzmm_bot/core/app.py
- Modify: tests/core/test_app.py

**Interfaces:**
- GET/PATCH /internal/game/ai-assistant/settings reads/writes settings plus quotas, never keys.
- POST /internal/ai/claim, POST /internal/ai/{id}/completed, and POST /internal/ai/{id}/failed use existing X-Core-Token authorization and lease conventions.

- [ ] **Step 1: Write failing API tests**

~~~python
def test_ai_settings_api_returns_no_key_and_updates_quotas(client, headers):
    initial = client.get("/internal/game/ai-assistant/settings", headers=headers)
    assert initial.status_code == 200
    assert "key" not in initial.text.lower()
    changed = client.patch("/internal/game/ai-assistant/settings", headers=headers, json=_assistant_payload(initial.json()))
    assert changed.status_code == 200

def test_ai_worker_completion_is_lease_fenced(client, headers):
    claim = client.post("/internal/ai/claim", headers=headers, json=_claim_payload()).json()
    response = client.post(f"/internal/ai/{claim['id']}/completed", headers=headers,
                           json={**_result_payload(claim), "text": "回复"})
    assert response.status_code == 200
~~~

- [ ] **Step 2: Verify failures**

Run: pytest tests/core/test_app.py -k "ai_assistant or ai_worker" -v  
Expected: FAIL with missing routes and models.

- [ ] **Step 3: Add constrained models and routes**

Validate persona/system prompt at max 4000 chars, fixed replies max 1000, response limit 1..800, timeout 1..60, quota 0..100, and one quota for every rank. PATCH replaces settings and quotas atomically. Claim returns null when idle. Completion strips text and rejects content longer than the claimed cap. Failure only accepts categories timeout, network, http_error, or invalid_response; no raw provider payload is received or stored.

- [ ] **Step 4: Verify APIs**

Run: pytest tests/core/test_app.py -k "ai_assistant or ai_worker" -v  
Expected: PASS, including 401 and secret-free response checks.

- [ ] **Step 5: Commit**

~~~bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py tests/core/test_app.py
git commit -m "feat: expose assistant configuration and worker api"
~~~

### Task 5: Add the independent Minimax client and AI worker

**Files:**
- Modify: src/dzmm_bot/runtime/settings.py
- Create: src/dzmm_bot/ai/__init__.py
- Create: src/dzmm_bot/ai/client.py
- Create: src/dzmm_bot/ai/core_client.py
- Create: src/dzmm_bot/ai/worker.py
- Create: src/dzmm_bot/ai/main.py
- Create: tests/ai/__init__.py
- Create: tests/ai/test_client.py
- Create: tests/ai/test_worker.py
- Modify: tests/runtime/test_settings.py

**Interfaces:**
- MinimaxChatClient.complete(system_prompt, user_content, *, max_chars, timeout_seconds) -> str.
- AIWorker.run_once() -> bool claims at most one request and reports one terminal result.
- Settings gains minimax_api_key, minimax_model, and minimax_base_url.

- [ ] **Step 1: Write failing transport tests**

~~~python
def test_minimax_client_sends_openai_compatible_request(httpx_mock):
    httpx_mock.add_response(json={"choices": [{"message": {"content": "收到"}}]})
    result = MinimaxChatClient("secret", "MiniMax-M2.5").complete(
        "system", "user", max_chars=20, timeout_seconds=10
    )
    assert result == "收到"
    request = httpx_mock.get_request()
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer secret"

def test_ai_worker_reports_timeout(fake_core, timeout_client):
    AIWorker("ai-1", fake_core, timeout_client, clock=lambda: BEIJING_NOW).run_once()
    assert fake_core.failed == [("request-1", "timeout")]
~~~

- [ ] **Step 2: Verify failures**

Run: pytest tests/ai tests/runtime/test_settings.py -k "minimax or ai_worker" -v  
Expected: FAIL because the package and settings are absent.

- [ ] **Step 3: Implement the minimum safe worker**

Core/admin/browser can start without Minimax settings; the AI worker requires DZMM_MINIMAX_API_KEY. Default DZMM_MINIMAX_MODEL=MiniMax-M2.5 and DZMM_MINIMAX_BASE_URL=https://api.minimaxi.com/v1.

Use httpx.Client to POST {base_url}/chat/completions with model, system/user messages, and max_completion_tokens. Map timeout to timeout; other transport/HTTP failures to network/http_error; missing or blank choices[0].message.content to invalid_response. Never log headers, API keys, prompt texts, or raw provider bodies. Strip and cap output before completion.

AIWorker.run_once() claims for 90 seconds, does nothing on an empty queue, and calls core complete/fail once per claim. main() loops once per second with DZMM_AI_WORKER_ID default ai-worker-1.

- [ ] **Step 4: Verify the worker**

Run: pytest tests/ai tests/runtime/test_settings.py -k "minimax or ai_worker" -v  
Expected: PASS for success, timeout, malformed response, empty queue, and no credential in callback/exception text.

- [ ] **Step 5: Commit**

~~~bash
git add src/dzmm_bot/runtime/settings.py src/dzmm_bot/ai tests/ai tests/runtime/test_settings.py
git commit -m "feat: add minimax assistant worker"
~~~

### Task 6: Add the AI 总监事 operator configuration view

**Files:**
- Modify: src/dzmm_bot/admin/core_client.py
- Modify: src/dzmm_bot/admin/app.py
- Modify: src/dzmm_bot/admin/templates/index.html
- Modify: src/dzmm_bot/admin/static/admin.js
- Modify: src/dzmm_bot/admin/static/admin.css
- Modify: tests/admin/test_app.py

**Interfaces:**
- CoreClient.get_ai_assistant_settings() and CoreClient.update_ai_assistant_settings(payload).
- GET/PATCH /api/ai-assistant/settings with current revision/idempotency behavior.
- A left-nav view named AI 总监事 with enable toggle, texts, rank limits, fixed replies, response cap, timeout, loading/error/save states.

- [ ] **Step 1: Write failing admin contract tests**

~~~python
def test_admin_serves_and_saves_ai_settings(client, admin_headers, fake_core):
    assert client.get("/api/ai-assistant/settings", headers=admin_headers).status_code == 200
    saved = client.patch("/api/ai-assistant/settings", headers=admin_headers, json=_assistant_payload())
    assert saved.status_code == 200
    assert fake_core.ai_assistant_saved["enabled"] is True

def test_admin_page_contains_ai_assistant_view(client, admin_headers):
    document = client.get("/", headers=admin_headers).text
    assert "AI 总监事" in document
    assert "每日调用上限" in document
~~~

- [ ] **Step 2: Verify failures**

Run: pytest tests/admin/test_app.py -k "ai_assistant" -v  
Expected: FAIL because proxy, UI section, and fake-core support do not exist.

- [ ] **Step 3: Implement the fixed-height standard console view**

Use the current standard card/button/select styles—no native unstyled controls or raw JSON editor. Render quotas as a compact fixed-height scrollable two-column table, sorted by rank. Use the existing debounce/idempotency, loading button, success/error toast, and revision conflict patterns. There is no key input, provider header, or secret field anywhere in admin HTML/JS/API responses.

A save submits the complete validated payload. Editing does not auto-enable AI. On an API error, preserve unsaved values and show the field error next to its control.

- [ ] **Step 4: Verify admin regressions**

Run: pytest tests/admin/test_app.py -v  
Expected: PASS for new save, auth, validation, conflict behavior, and existing admin pages.

- [ ] **Step 5: Commit**

~~~bash
git add src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/admin/test_app.py
git commit -m "feat: configure ai assistant in admin console"
~~~

### Task 7: Document rules and deploy the fourth service

**Files:**
- Modify: rule.md
- Modify: deploy/env/dzmm.example.env
- Create: deploy/systemd/dzmm-ai-worker.service
- Modify: deploy/scripts/deploy.sh
- Modify: tests/deploy/test_artifacts.py

**Interfaces:**
- dzmm-ai-worker.service starts python -m dzmm_bot.ai.main after core and reads /etc/dzmm/dzmm.env.
- Deployment restarts all four services after migrations.

- [ ] **Step 1: Write failing artifact tests**

~~~python
def test_ai_worker_unit_uses_environment_file_and_core_dependency():
    unit = Path("deploy/systemd/dzmm-ai-worker.service").read_text()
    assert "EnvironmentFile=/etc/dzmm/dzmm.env" in unit
    assert "After=network-online.target dzmm-core.service" in unit
    assert "-m dzmm_bot.ai.main" in unit

def test_deploy_restarts_ai_worker():
    assert "dzmm-ai-worker.service" in Path("deploy/scripts/deploy.sh").read_text()
~~~

- [ ] **Step 2: Verify failures**

Run: pytest tests/deploy/test_artifacts.py -k "ai_worker" -v  
Expected: FAIL because the unit and restart target are absent.

- [ ] **Step 3: Add deployment support and durable rules**

Document placeholder-only settings:

~~~dotenv
DZMM_MINIMAX_API_KEY=CHANGE_ME
DZMM_MINIMAX_MODEL=MiniMax-M2.5
DZMM_MINIMAX_BASE_URL=https://api.minimaxi.com/v1
DZMM_AI_WORKER_ID=ai-worker-1
~~~

Create a Restart=on-failure unit. Add it to deploy restart. Add rule.md entries for AI priority, group-only scope, Beijing quota/no-refund rule, and the rule that AI cannot determine commands/economic/game outcomes.

- [ ] **Step 4: Verify artifacts**

Run: pytest tests/deploy/test_artifacts.py -v && git diff --check  
Expected: PASS and no secret values in tracked files.

- [ ] **Step 5: Commit**

~~~bash
git add rule.md deploy/env/dzmm.example.env deploy/systemd/dzmm-ai-worker.service deploy/scripts/deploy.sh tests/deploy/test_artifacts.py
git commit -m "chore: deploy minimax assistant worker"
~~~

### Task 8: Complete verification and deploy only with server configuration present

**Files:**
- Modify: none unless preceding tests reveal a defect.

- [ ] **Step 1: Run complete local verification**

Run: pytest -q && python -m compileall -q src && git diff --check  
Expected: exit code 0.

- [ ] **Step 2: Verify the approved requirements line by line**

Check: group-only trigger; command/event precedence; onboarding; Beijing quotas/rank defaults; editable settings; no secret persistence/exposure; worker lease; safe fallback; outbound reuse; admin view; unit/deploy artifacts; .env still untracked.

- [ ] **Step 3: Commit plan and push completed code**

~~~bash
git add docs/superpowers/plans/2026-08-08-minimax-ai-assistant.md
git commit -m "docs: plan minimax assistant implementation"
git push origin rewrite/server-runtime
~~~

- [ ] **Step 4: Deploy and verify without exposing secrets**

Before deployment, put the existing Minimax credential into server /etc/dzmm/dzmm.env as DZMM_MINIMAX_API_KEY and set DZMM_MINIMAX_MODEL. Deploy the approved commit, migrate, then run:

~~~bash
sudo systemctl is-active dzmm-core dzmm-admin-web dzmm-browser-worker dzmm-ai-worker
curl -fsS http://127.0.0.1:18120/healthz
curl -fsS http://127.0.0.1:18090/healthz
~~~

Expected: all services are active, health endpoints respond, and logs contain no credential, Authorization header, or provider request body.
