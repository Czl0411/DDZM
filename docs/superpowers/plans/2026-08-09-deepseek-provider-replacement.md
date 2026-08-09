# DeepSeek Provider Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the active MiniMax integration with DeepSeek V4 Flash while preserving all existing AI assistant and memory-worker behavior.

**Architecture:** Keep the existing synchronous `httpx` chat-completions client and independent AI Worker boundary. Rename provider-specific runtime types and settings to DeepSeek, send DeepSeek's official non-thinking request fields, and leave the core queue, database, admin UI, prompts, quotas, retries, and outbound delivery unchanged.

**Tech Stack:** Python 3.12, `httpx`, `pytest`, systemd environment files.

## Global Constraints

- Read the API key only from `DP_API_KEY`; never print, log, stage, or return it.
- Default to `deepseek-v4-flash` at `https://api.deepseek.com`.
- Send `thinking: {"type": "disabled"}` and `max_tokens`; read only `choices[0].message.content`.
- Preserve the existing `max_chars` truncation and error categories: `timeout`, `http_error`, `network`, and `invalid_response`.
- Do not add explicit cache controls: DeepSeek context caching is server-side and automatic.
- Do not change database schema, admin behavior, core APIs, historical migrations, or historical design/plan documents.
- Preserve all pre-existing uncommitted work. In overlapping files, stage only DeepSeek-specific hunks and never stage `.env`.

---

### Task 1: Replace and rewire the active model provider

**Files:**
- Create: `tests/ai/test_main.py`
- Modify: `tests/ai/test_client.py`
- Modify: `tests/ai/test_worker.py`
- Modify: `tests/runtime/test_settings.py`
- Modify: `src/dzmm_bot/ai/client.py`
- Modify: `src/dzmm_bot/ai/main.py`
- Modify: `src/dzmm_bot/ai/worker.py`
- Modify: `src/dzmm_bot/ai/__init__.py`
- Modify: `src/dzmm_bot/runtime/settings.py`

**Interfaces:**
- Consumes: `httpx.Client.post(path, json=payload, timeout=seconds)`, the existing `complete(system_prompt, user_content, *, max_chars, timeout_seconds) -> str` call shape, `AICoreClient`, and `Settings.from_environment()`.
- Produces: `DeepSeekCallError(category: str)`, `DeepSeekChatClient(api_key, model, *, base_url="https://api.deepseek.com", client=None)`, and settings fields `deepseek_api_key`, `deepseek_model`, and `deepseek_base_url`.

- [ ] **Step 1: Replace the provider client tests before changing production code**

Use these tests in `tests/ai/test_client.py`:

```python
import json

import httpx
import pytest


def test_deepseek_client_sends_official_non_thinking_request():
    from dzmm_bot.ai.client import DeepSeekChatClient

    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": " 收到 ",
                            "reasoning_content": "不得发送的思考",
                        }
                    }
                ],
                "usage": {
                    "prompt_cache_hit_tokens": 10,
                    "prompt_cache_miss_tokens": 2,
                },
            },
        )

    client = DeepSeekChatClient(
        "secret",
        "deepseek-v4-flash",
        client=httpx.Client(
            base_url="https://api.deepseek.com",
            transport=httpx.MockTransport(handle),
        ),
    )

    assert client.complete("system", "user", max_chars=20, timeout_seconds=10) == "收到"
    assert requests[0].url.path == "/chat/completions"
    assert requests[0].headers["Authorization"] == "Bearer secret"
    assert json.loads(requests[0].content) == {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        "thinking": {"type": "disabled"},
        "max_tokens": 20,
    }


def test_deepseek_client_rejects_an_empty_model_response():
    from dzmm_bot.ai.client import DeepSeekCallError, DeepSeekChatClient

    client = DeepSeekChatClient(
        "secret",
        "deepseek-v4-flash",
        client=httpx.Client(
            base_url="https://api.deepseek.com",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"choices": []})
            ),
        ),
    )

    with pytest.raises(DeepSeekCallError, match="invalid_response") as captured:
        client.complete("system", "user", max_chars=20, timeout_seconds=10)

    assert captured.value.category == "invalid_response"
```

- [ ] **Step 2: Replace runtime and startup contract tests**

Replace the two MiniMax settings tests in `tests/runtime/test_settings.py` with:

```python
def test_settings_reads_deepseek_runtime_configuration(monkeypatch):
    monkeypatch.setenv("DZMM_DATABASE_URL", "postgresql+psycopg://dzmm@localhost/dzmm")
    monkeypatch.setenv("DZMM_CORE_TOKEN", "core-secret")
    monkeypatch.setenv("DP_API_KEY", "deepseek-secret")

    settings = Settings.from_environment()

    assert settings.deepseek_api_key == "deepseek-secret"
    assert settings.deepseek_model == "deepseek-v4-flash"
    assert settings.deepseek_base_url == "https://api.deepseek.com"


def test_settings_does_not_reuse_the_legacy_generic_api_key(monkeypatch):
    monkeypatch.setenv("DZMM_DATABASE_URL", "postgresql+psycopg://dzmm@localhost/dzmm")
    monkeypatch.setenv("DZMM_CORE_TOKEN", "core-secret")
    monkeypatch.delenv("DP_API_KEY", raising=False)
    monkeypatch.setenv("API_KEY", "legacy-secret")

    assert Settings.from_environment().deepseek_api_key is None
```

Change `TimeoutClient` in `tests/ai/test_worker.py` to use the new provider error:

```python
class TimeoutClient:
    def complete(self, *args, **kwargs):
        from dzmm_bot.ai.client import DeepSeekCallError

        raise DeepSeekCallError("timeout")
```

Create `tests/ai/test_main.py`:

```python
from types import SimpleNamespace

import pytest


def test_ai_main_builds_the_deepseek_client(monkeypatch):
    import dzmm_bot.ai.main as module

    settings = SimpleNamespace(
        core_api_port=18120,
        core_token="core-token",
        deepseek_api_key="deepseek-secret",
        deepseek_model="deepseek-v4-flash",
        deepseek_base_url="https://api.deepseek.com",
    )
    captured = {}

    class FakeDeepSeekClient:
        def __init__(self, api_key, model, *, base_url):
            captured["client"] = (api_key, model, base_url)

    class StopWorker:
        def __init__(self, worker_id, core, client):
            captured["worker_id"] = worker_id

        def run_once(self):
            raise StopIteration

    monkeypatch.setattr(
        module.Settings, "from_environment", staticmethod(lambda: settings)
    )
    monkeypatch.setattr(module, "DeepSeekChatClient", FakeDeepSeekClient)
    monkeypatch.setattr(module, "AICoreClient", lambda *args: object())
    monkeypatch.setattr(module, "AIWorker", StopWorker)

    with pytest.raises(StopIteration):
        module.main()

    assert captured == {
        "client": ("deepseek-secret", "deepseek-v4-flash", "https://api.deepseek.com"),
        "worker_id": "ai-worker-1",
    }


def test_ai_main_requires_the_deepseek_key(monkeypatch):
    import dzmm_bot.ai.main as module

    settings = SimpleNamespace(deepseek_api_key=None)
    monkeypatch.setattr(
        module.Settings, "from_environment", staticmethod(lambda: settings)
    )

    with pytest.raises(ValueError, match="DP_API_KEY must be set and nonempty"):
        module.main()
```

- [ ] **Step 3: Run all new contracts and verify the RED state**

Run:

```bash
.venv/bin/pytest tests/ai/test_client.py tests/ai/test_worker.py tests/ai/test_main.py tests/runtime/test_settings.py -v
```

Expected: FAIL because the DeepSeek types and settings fields do not exist and the active Worker still imports MiniMax errors.

- [ ] **Step 4: Implement the minimal DeepSeek client**

In `src/dzmm_bot/ai/client.py`, rename the provider types, change the default base URL, and make the request body exactly:

```python
{
    "model": self._model,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ],
    "thinking": {"type": "disabled"},
    "max_tokens": max_chars,
}
```

Keep the existing exception ordering and map every failure to `DeepSeekCallError` with the same category strings. Keep `content.strip()` and `return text[:max_chars]`; do not inspect or expose `reasoning_content` or `usage`.

- [ ] **Step 5: Implement the runtime rename and atomic wiring**

In `Settings`, replace the three provider fields and reads with:

```python
deepseek_api_key: str | None = None
deepseek_model: str = "deepseek-v4-flash"
deepseek_base_url: str = "https://api.deepseek.com"
```

```python
deepseek_api_key=_optional("DP_API_KEY", empty_as_none=True),
deepseek_model=os.environ.get("DZMM_DEEPSEEK_MODEL", "deepseek-v4-flash"),
deepseek_base_url=os.environ.get(
    "DZMM_DEEPSEEK_BASE_URL", "https://api.deepseek.com"
),
```

Preserve the unrelated `bot_api_token` field and environment read exactly as they exist in the working tree.

In `ai/main.py`, construct `DeepSeekChatClient` from the three DeepSeek fields and reject a missing key with `DP_API_KEY must be set and nonempty`.

In `ai/worker.py`, import and catch `DeepSeekCallError` in both reply and memory paths. Update `ai/__init__.py` to describe the independent DeepSeek AI Worker. Make no queue, prompt, lease, timeout, or truncation changes.

- [ ] **Step 6: Run provider/runtime tests and verify the GREEN state**

Run:

```bash
.venv/bin/pytest tests/ai tests/runtime/test_settings.py -v
rg -n -i "minimax|DZMM_MINIMAX" src tests/ai tests/runtime/test_settings.py -g '!**/__pycache__/**'
```

Expected: all tests PASS and the scan returns no active runtime or relevant test matches.

- [ ] **Step 7: Selectively commit the atomic runtime replacement**

Because `src/dzmm_bot/runtime/settings.py` and `tests/runtime/test_settings.py` contain pre-existing Bot API edits, use hunk staging and inspect the index:

```bash
git add src/dzmm_bot/ai/__init__.py src/dzmm_bot/ai/client.py src/dzmm_bot/ai/main.py src/dzmm_bot/ai/worker.py tests/ai/test_client.py tests/ai/test_main.py tests/ai/test_worker.py
git add -p src/dzmm_bot/runtime/settings.py tests/runtime/test_settings.py
git diff --cached --check
git diff --cached -- src/dzmm_bot/runtime/settings.py tests/runtime/test_settings.py
git commit -m "feat: replace MiniMax provider with DeepSeek"
```

The cached diff must contain the DeepSeek replacements but must not introduce or remove the existing `bot_api_token` work.

### Task 2: Update deployment artifacts and verify the repository

**Files:**
- Modify: `tests/deploy/test_artifacts.py`
- Modify: `deploy/env/dzmm.example.env`
- Modify: `deploy/systemd/dzmm-ai-worker.service`

**Interfaces:**
- Consumes: `DP_API_KEY`, `DZMM_DEEPSEEK_MODEL`, and `DZMM_DEEPSEEK_BASE_URL` from Task 1.
- Produces: a deployable example environment and a correctly labeled systemd unit.

- [ ] **Step 1: Add a failing deployment artifact test**

Extend `test_systemd_units_use_environment_factories_and_isolated_ports` in `tests/deploy/test_artifacts.py`:

```python
example_env = (ROOT / "deploy/env/dzmm.example.env").read_text()

assert "Description=DZMM DeepSeek AI Worker" in ai_worker
assert "DP_API_KEY=CHANGE_ME" in example_env
assert "DZMM_DEEPSEEK_MODEL=deepseek-v4-flash" in example_env
assert "DZMM_DEEPSEEK_BASE_URL=https://api.deepseek.com" in example_env
assert "MINIMAX" not in (ai_worker + example_env).upper()
```

- [ ] **Step 2: Run the artifact test and verify the RED state**

Run: `.venv/bin/pytest tests/deploy/test_artifacts.py::test_systemd_units_use_environment_factories_and_isolated_ports -v`

Expected: FAIL because the unit description and example environment still name MiniMax.

- [ ] **Step 3: Update only the active deployment provider settings**

Set the systemd description to:

```ini
Description=DZMM DeepSeek AI Worker
```

Replace only the MiniMax block in `deploy/env/dzmm.example.env` with:

```dotenv
DP_API_KEY=CHANGE_ME
DZMM_DEEPSEEK_MODEL=deepseek-v4-flash
# Optional; leave at the official OpenAI-compatible endpoint unless instructed otherwise.
DZMM_DEEPSEEK_BASE_URL=https://api.deepseek.com
```

Preserve the pre-existing `DZMM_BOT_API_TOKEN` lines exactly and do not edit `.env`.

- [ ] **Step 4: Run targeted and full verification**

Run:

```bash
.venv/bin/pytest tests/ai tests/runtime/test_settings.py tests/deploy/test_artifacts.py -v
.venv/bin/pytest -v
rg -n -i "minimax|DZMM_MINIMAX" src tests deploy -g '!**/__pycache__/**'
git diff --check
git status --short
```

Expected: targeted and full test suites PASS; the scan returns no active-code, test, or deployment matches; `git diff --check` reports no whitespace errors; `.env` remains untracked and unstaged; all unrelated pre-existing edits remain present.

- [ ] **Step 5: Selectively commit deployment changes**

Because the example environment already contains an unrelated Bot API edit, stage only the DeepSeek replacement hunk and inspect it:

```bash
git add tests/deploy/test_artifacts.py deploy/systemd/dzmm-ai-worker.service
git add -p deploy/env/dzmm.example.env
git diff --cached --check
git diff --cached
git commit -m "chore: deploy DeepSeek AI worker"
```

The cached diff must not add, remove, or alter `DZMM_BOT_API_TOKEN`.
