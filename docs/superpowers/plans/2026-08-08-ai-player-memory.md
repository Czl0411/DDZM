# AI Player Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add asynchronous per-player AI memory extraction, live player context, and administrator-managed gameplay guidance without delaying visible AI replies.

**Architecture:** Extend the existing AI assistant settings and request system with a separate memory-settings record, one latest-memory snapshot per player, and an independently leased memory-job queue. The existing AI worker claims both reply and memory work, but a memory-job failure never changes an AI reply request or an existing snapshot. Core builds AI prompts from live user data, the configured gameplay guide, and the current snapshot.

**Tech Stack:** Python 3.12, SQLAlchemy, Alembic, FastAPI, pytest, vanilla JavaScript admin UI, PostgreSQL.

## Global Constraints

- Business-day and timestamps use Beijing time.
- Player-visible AI output must never include MiniMax reasoning; keep `reasoning_split: true` and only use `message.content`.
- Only a non-command `@总监事 内容` enters the normal AI path.
- First extraction scans at most the configured 500 recent valid messages; later scans are incremental.
- Skip bot output, slash commands, game/random-event role-play, parenthesized observer speech, blank, and short messages.
- Current identity and game data are always read live, never persisted as AI memory.
- Players receive no command to view or delete their memory; administrators can view, edit, and clear it.
- Preserve the untracked local `.env`; it must never be staged or committed.

---

## File Structure

- `migrations/versions/20260808_28_ai_player_memory.py`: schema migration and safe defaults.
- `src/dzmm_bot/core/schema.py`: SQLAlchemy records for memory configuration, player snapshots, and leased jobs.
- `src/dzmm_bot/core/repository.py`: memory queue lifecycle, valid-history query, live-context prompt construction, and configuration CRUD.
- `src/dzmm_bot/core/api_models.py`: core request/response contracts for memory settings and employee memory operations.
- `src/dzmm_bot/core/app.py`: authenticated core routes for memory configuration, worker claim/complete/fail, and employee memory operations.
- `src/dzmm_bot/ai/core_client.py`: client contract for memory-job lifecycle.
- `src/dzmm_bot/ai/worker.py`: independent reply and memory work execution paths.
- `src/dzmm_bot/ai/client.py`: structured extraction helper that returns only memory text, never reasoning.
- `src/dzmm_bot/admin/app.py`: protected admin relay routes for settings and employee memory.
- `src/dzmm_bot/admin/templates/index.html`: AI settings section and employee-memory modal markup.
- `src/dzmm_bot/admin/static/admin.js`: load/save state and employee-memory actions.
- `tests/core/test_repository.py`, `tests/core/test_service.py`, `tests/core/test_app.py`, `tests/ai/test_client.py`, `tests/ai/test_worker.py`, `tests/admin/test_app.py`: regression coverage.

### Task 1: Persist memory configuration, snapshots, and independent jobs

**Files:**
- Create: `migrations/versions/20260808_28_ai_player_memory.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produce `AIMemorySettingsRecord`, `AIPlayerMemoryRecord`, and `AIMemoryJobRecord`.
- `AIPlayerMemoryRecord` has one row per `users.id` and stores `memory_text`, `last_scanned_message_id`, `created_at`, and `updated_at`.
- `AIMemoryJobRecord` stores `user_id`, `status`, lease fields, target message ID, attempt count, failure summary, and timestamps.

- [ ] **Step 1: Write the failing schema-contract test**

```python
def test_ai_memory_schema_keeps_one_snapshot_and_one_active_job_per_player():
    assert {"ai_memory_settings", "ai_player_memories", "ai_memory_jobs"} <= set(Base.metadata.tables)
    assert {"user_id"} == {
        column.name for column in AIPlayerMemoryRecord.__table__.primary_key.columns
    }
```

- [ ] **Step 2: Run it to verify RED**

Run: `pytest tests/core/test_repository.py::test_ai_memory_schema_keeps_one_snapshot_and_one_active_job_per_player -v`

Expected: FAIL because memory records do not exist.

- [ ] **Step 3: Implement the minimal schema and migration**

Create migration `20260808_28` with defaults: memory enabled, history limit `500`, maximum snapshot length `1200`, a concise gameplay guide, and extraction instructions that emit only stable player facts. Add the snapshot primary key and active-job uniqueness/index needed to prevent duplicate jobs.

- [ ] **Step 4: Run the focused test to verify GREEN**

Run: `pytest tests/core/test_repository.py::test_ai_memory_schema_keeps_one_snapshot_and_one_active_job_per_player -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/20260808_28_ai_player_memory.py src/dzmm_bot/core/schema.py tests/core/test_repository.py
git commit -m "feat: persist ai player memories"
```

### Task 2: Queue extraction and build safe live AI context

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Test: `tests/core/test_repository.py`, `tests/core/test_service.py`

**Interfaces:**
- Produce `try_enqueue_ai_memory_job(user_id, trigger_message_id, now) -> None`.
- Produce `claim_ai_memory_job(worker_id, now, lease_seconds) -> ClaimedAIMemoryJob | None`.
- Produce `complete_ai_memory_job(job_id, worker_id, lease_token, memory_text, scanned_message_id, now) -> bool` and `fail_ai_memory_job(job_id, worker_id, lease_token, failure_summary, now) -> bool`.
- Extend claimed reply context with live profile, gameplay guide, and bounded previous memory.

- [ ] **Step 1: Write failing queue and prompt tests**

```python
def test_ai_mention_queues_one_memory_job_without_delaying_reply(repository, now):
    user, _ = repository.create_user("memory-user", "阿彻", now, 0)
    repository.try_enqueue_ai_request(uuid4(), user.platform_id, "@总监事 我喜欢简短回复", now)
    assert repository.claim_ai_memory_job("worker", now, 30) is not None

def test_ai_context_uses_live_profile_and_snapshot(repository, now):
    claim = repository.claim_ai_request("worker", now, 30)
    assert "实时资料" in claim.system_prompt
    assert "最新玩家记忆" in claim.system_prompt
```

- [ ] **Step 2: Run tests to verify RED**

Run: `pytest tests/core/test_repository.py tests/core/test_service.py -k "memory_job or live_profile" -v`

Expected: FAIL because the queue and context do not exist.

- [ ] **Step 3: Implement the queue and context**

Reuse the `FOR UPDATE SKIP LOCKED` lease pattern used by `ai_requests`. First jobs collect at most the configured latest 500 valid messages; later jobs collect messages after the snapshot cutoff. If an active job already exists, advance its target cutoff rather than adding another job. Include escaped live nickname/rank/department/balance, gameplay guide, and bounded snapshot in the reply prompt.

- [ ] **Step 4: Add filtering and no-op tests**

```python
def test_memory_history_excludes_commands_bot_and_parenthesized_observer_messages(repository, now):
    user, _ = repository.create_user("history-user", "阿彻", now, 0)
    messages = repository.memory_source_messages_for_user(user.id, None, 500)
    assert [message.content for message in messages] == ["以后叫我阿彻"]

def test_empty_extraction_keeps_snapshot_and_advances_cutoff(repository, now):
    user, _ = repository.create_user("snapshot-user", "阿彻", now, 0)
    previous = repository.player_memory_for_user(user.id)
    claim = repository.claim_ai_memory_job("worker", now, 30)
    repository.complete_ai_memory_job(claim.id, "worker", claim.lease_token, "", claim.target_message_id, now)
    assert repository.player_memory_for_user(user.id).memory_text == previous.memory_text
```

- [ ] **Step 5: Run focused tests to verify GREEN**

Run: `pytest tests/core/test_repository.py tests/core/test_service.py -k "memory or ai_context" -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/schema.py tests/core/test_repository.py tests/core/test_service.py
git commit -m "feat: queue ai memory extraction"
```

### Task 3: Extract memories asynchronously without reasoning leakage

**Files:**
- Modify: `src/dzmm_bot/ai/client.py`
- Modify: `src/dzmm_bot/ai/core_client.py`
- Modify: `src/dzmm_bot/ai/worker.py`
- Test: `tests/ai/test_client.py`, `tests/ai/test_worker.py`

**Interfaces:**
- Produce `MinimaxChatClient.extract_memory(instruction, current_memory, messages, max_chars, timeout_seconds) -> str`.
- Make `AIWorker.run_once()` claim reply work first, then memory work when no reply is pending.

- [ ] **Step 1: Write failing extraction and isolation tests**

```python
def test_memory_extraction_sets_reasoning_split_and_returns_content_only():
    memory = client.extract_memory("rules", "旧记忆", ["新消息"], max_chars=1200, timeout_seconds=10)
    assert json.loads(requests[0].content)["reasoning_split"] is True
    assert memory == "偏好称呼：阿彻"

def test_memory_job_failure_does_not_fail_or_send_player_reply():
    worker.run_once()
    assert core.memory_failed
    assert core.completed == []
```

- [ ] **Step 2: Run tests to verify RED**

Run: `pytest tests/ai/test_client.py tests/ai/test_worker.py -k memory -v`

Expected: FAIL because memory extraction and worker lifecycle are absent.

- [ ] **Step 3: Implement the minimal extraction path**

Reuse the HTTPS MiniMax client with `reasoning_split: true`. The extraction prompt requires only a bounded snapshot, forbids secrets, third-party data, and current economy state, and returns empty output when no stable fact exists. Memory jobs never create outbound messages. Provider errors only mark the job failed and retain the previous snapshot.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run: `pytest tests/ai/test_client.py tests/ai/test_worker.py -k memory -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/ai/client.py src/dzmm_bot/ai/core_client.py src/dzmm_bot/ai/worker.py tests/ai/test_client.py tests/ai/test_worker.py
git commit -m "feat: extract ai player memories asynchronously"
```

### Task 4: Expose protected configuration and memory APIs

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Test: `tests/core/test_app.py`, `tests/admin/test_app.py`

**Interfaces:**
- Extend `/api/ai-assistant/settings` with memory settings and gameplay guide.
- Add `GET/PATCH /api/ai-assistant/memories/{platform_id}` behind administrator authorization.

- [ ] **Step 1: Write failing API tests**

```python
def test_ai_settings_expose_memory_controls(client, token):
    response = client.get("/api/ai-assistant/settings", headers=token)
    assert response.json()["memory_history_limit"] == 500
    assert "gameplay_guide" in response.json()

def test_only_administrator_can_edit_employee_ai_memory(client, user_headers):
    response = client.patch("/api/ai-assistant/memories/employee-1", headers=user_headers, json={"memory_text": "偏好称呼：阿彻"})
    assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify RED**

Run: `pytest tests/core/test_app.py tests/admin/test_app.py -k "ai_memory or memory_controls" -v`

Expected: FAIL because the fields and routes do not exist.

- [ ] **Step 3: Implement validation and relay routes**

Validate configuration booleans, history/snapshot integer bounds, and text lengths. Reuse `versioned_configuration_response` for settings writes and existing `authorize` dependencies for memory operations. Clearing memory sends an explicit empty snapshot through the same protected endpoint.

- [ ] **Step 4: Run focused API tests to verify GREEN**

Run: `pytest tests/core/test_app.py tests/admin/test_app.py -k "ai_memory or memory_controls" -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/admin/app.py tests/core/test_app.py tests/admin/test_app.py
git commit -m "feat: manage ai memory configuration"
```

### Task 5: Add administrator controls

**Files:**
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Test: `tests/admin/test_app.py`

**Interfaces:**
- The existing AI settings modal gains a “上下文与记忆” section.
- Employee rows gain an administrator-only “AI 记忆” action opening an edit/clear modal.

- [ ] **Step 1: Write the failing UI contract test**

```python
def test_admin_page_contains_ai_memory_controls(client, super_admin_headers):
    response = client.get("/", headers=super_admin_headers)
    assert 'id="ai-assistant-gameplay-guide"' in response.text
    assert 'id="employee-ai-memory-modal"' in response.text
```

- [ ] **Step 2: Run test to verify RED**

Run: `pytest tests/admin/test_app.py::test_admin_page_contains_ai_memory_controls -v`

Expected: FAIL because the controls are absent.

- [ ] **Step 3: Implement minimal UI integration**

Add automatic-memory, gameplay-guide, history-limit, snapshot-length, and extraction-instruction fields to the existing AI modal. Add a single employee-memory modal with current snapshot, save, and explicit clear. Reuse existing debounce, version headers, button loading states, standard toast, pagination, and modal scroll styles; add no player-facing controls.

- [ ] **Step 4: Run targeted admin test to verify GREEN**

Run: `pytest tests/admin/test_app.py -k ai_memory -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/admin/test_app.py
git commit -m "feat: add admin ai memory controls"
```

### Task 6: Verify and prepare safe deployment

**Files:**
- Modify: `rule.md` only if it contains AI runtime rules that need the asynchronous-memory boundary.

- [ ] **Step 1: Run the full test suite**

Run: `pytest`

Expected: exit code `0` with all existing and new tests passing.

- [ ] **Step 2: Check migration from a clean test database**

Run: `alembic upgrade head`

Expected: migration head is `20260808_28` and the new tables exist.

- [ ] **Step 3: Inspect change scope and secrets**

Run: `git diff --check && git status --short && git diff --name-only origin/main...HEAD`

Expected: no whitespace errors; `.env` remains untracked and absent from staged/committed files.

- [ ] **Step 4: Commit final documentation only if changed**

```bash
git add rule.md
git commit -m "docs: document ai memory behavior"
```

- [ ] **Step 5: Request deployment authorization with evidence**

Report the commit range, full test output, migration target, and exact production backup/deploy steps. Do not deploy without explicit user authorization.
