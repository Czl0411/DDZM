# Long Message Bot API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route long non-recalled group replies through DZMM's token-authenticated Bot API, ship the prepared 谁是卧底 flow improvements, and enable DeepSeek thinking mode.

**Architecture:** Core preserves qualifying group text as one outbound record when `DZMM_BOT_API_TOKEN` is configured. Browser Worker selects `DzmmBotSender` only for those records and retains the current WebSocket gateway for every other outbound message.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, httpx, pytest, systemd.

## Global Constraints

- Bot API routing starts above 1,000 characters or above 10 newline characters.
- Direct messages and recalled messages must remain on the browser WebSocket path.
- Do not log or commit `DZMM_BOT_API_TOKEN`.
- Preserve unrelated local changes outside this isolated worktree.
- Exclude and remove the uncommitted CAPTCHA detection and manual-auth changes.

---

### Task 1: Bot API client and runtime configuration

**Files:**
- Create: `src/dzmm_bot/browser/bot_api.py`
- Modify: `src/dzmm_bot/runtime/settings.py`
- Modify: `src/dzmm_bot/browser/main.py`
- Modify: `deploy/env/dzmm.example.env`
- Test: `tests/browser/test_bot_api.py`
- Test: `tests/runtime/test_settings.py`

**Interfaces:**
- Produces: `DzmmBotSender.send_to(chatroom_id: str, text: str) -> str`
- Produces: `chatroom_id_from_url(chat_url: str) -> str`
- Produces: `Settings.bot_api_token: str | None`

- [ ] **Step 1: Add failing client and settings tests**

Test that the client sends `X-Bot-Token` and the unchanged content to `/api/bot/send-message`, returns `result.message_id`, surfaces API errors, and that Settings reads `DZMM_BOT_API_TOKEN`.

- [ ] **Step 2: Run tests and verify missing imports or attributes fail**

Run: `PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q tests/browser/test_bot_api.py tests/runtime/test_settings.py`

- [ ] **Step 3: Add the minimal client, setting, chatroom parsing, and worker construction**

Use an `httpx.Client` with base URL `https://www.dzmm.ai`, `X-Bot-Token`, and a 20-second timeout. Build it only when the optional environment variable is non-empty.

- [ ] **Step 4: Re-run focused tests**

Run the Step 2 command and require zero failures.

### Task 2: Preserve and route qualifying outbound messages

**Files:**
- Create: `src/dzmm_bot/runtime/outbound.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/browser/core_client.py`
- Modify: `src/dzmm_bot/browser/worker.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/browser/test_worker.py`

**Interfaces:**
- Produces: `requires_bot_group_sender(text: str) -> bool`
- Extends: `OutboundClaim.recall_after_seconds: int | None`
- Consumes: `DzmmBotSender.send_to(...)`

- [ ] **Step 1: Add failing Core preservation and Worker routing tests**

Cover both thresholds, ordinary messages, direct messages, and recalled messages. Assert long qualifying text remains one database record when preservation is enabled.

- [ ] **Step 2: Run tests and verify the missing routing behavior fails**

Run: `PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q tests/core/test_repository.py tests/browser/test_worker.py tests/core/test_app.py`

- [ ] **Step 3: Implement shared thresholds, claim contract, Core preservation, and Worker selection**

Preserve only group records with no explicit destination and no recall timer. Confirm Bot API sends through the existing fenced sent acknowledgement.

- [ ] **Step 4: Re-run focused tests**

Run the Step 2 command and require zero failures.

### Task 3: 谁是卧底 flow and DeepSeek thinking mode

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `tests/core/test_repository.py`
- Modify: `src/dzmm_bot/ai/client.py`
- Modify: `tests/ai/test_client.py`

**Interfaces:**
- Extends: 谁是卧底 card, opening, and voting behavior in `CoreRepository`
- Extends: `DeepSeekChatClient.complete(...)` request body with explicit thinking mode

- [ ] **Step 1: Add failing gameplay and AI request tests**

Assert role cards contain only their word, the opening lists seats and voting guidance, the first vote starts voting, and the DeepSeek request uses `{"thinking": {"type": "enabled"}}` while returning only final content.

- [ ] **Step 2: Run tests and verify the old behavior fails**

Run: `PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q tests/core/test_repository.py tests/ai/test_client.py`

- [ ] **Step 3: Implement the minimal gameplay and thinking changes**

Change only the existing card formatter, opening transition, vote transition, and DeepSeek request toggle.

- [ ] **Step 4: Re-run focused tests**

Run the Step 2 command and require zero failures.

### Task 4: Commit, deploy, and verify production

**Files:**
- Verify: all files above

**Interfaces:**
- Consumes: existing deployment scripts and `/etc/dzmm/dzmm.env`
- Produces: production services running the committed Bot API route

- [ ] **Step 1: Run the complete test suite**

Run: `PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q`

- [ ] **Step 2: Review scope and secrets**

Run `git status --short`, `git diff --check`, and inspect the staged diff. Confirm no `.env` file or token value is included.

- [ ] **Step 3: Commit and fast-forward main**

Commit with `feat: route long group replies through bot api`, then update `main` without overwriting unrelated working-tree edits.

- [ ] **Step 4: Deploy the committed revision**

Use the repository's production deployment script, leaving `/etc/dzmm/dzmm.env` intact.

- [ ] **Step 5: Verify production**

Confirm `DZMM_BOT_API_TOKEN` is non-empty without printing it, all four services are active, listener desired/effective state is true, and fresh service logs contain no send errors after a long-message smoke test.
