# AI Multi-Turn Conversation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carry the latest 15 completed player/supervisor dialogue turns into each DeepSeek request while isolating history by player and group and expiring it after 20 minutes.

**Architecture:** Reuse completed `ai_requests` joined to `inbound_messages`; no new persistence or migration is required. The repository selects and normalizes bounded history, the internal API transports it as typed role/content messages, and the AI worker forwards it to the DeepSeek client between the system prompt and current user message.

**Tech Stack:** Python 3.12, SQLAlchemy 2, FastAPI/Pydantic, httpx, pytest

## Global Constraints

- Keep at most 15 complete turns, where one turn is one player question plus one final supervisor reply.
- Isolate history by player and group chat; different players and different `chatroom_id` values must never share history.
- Expire history 20 minutes after the prior inbound AI message.
- Include only completed AI requests with non-empty `result_text`.
- Never include ordinary group messages, gameplay commands, fallback replies, or `reasoning_content`.
- Keep existing quotas, response limits, knowledge routing, stable impressions, safety rules, and outbound delivery unchanged.
- Do not add a database migration or admin configuration surface.

---

### Task 1: Select bounded conversation history in the repository

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `AIConversationMessage(role: str, content: str)`.
- Produces: `ClaimedAIRequest.history_messages: tuple[AIConversationMessage, ...]`.
- Consumes existing `AIRequestRecord.result_text`, `InboundRecord.source_type`, `InboundRecord.chatroom_id`, and `InboundRecord.received_at`.

- [ ] **Step 1: Write repository tests for ordered 15-turn history**

Add a helper that inserts completed historical AI requests using the real schema, then create 16 completed requests for the same player and `chatroom_id`. Queue a seventeenth request and assert its claim contains exactly 30 messages representing turns 2 through 16 in chronological `user`, `assistant` order, with mention prefixes removed from historical user content.

```python
def test_ai_claim_includes_latest_fifteen_completed_turns_in_order(
    repository, session_factory, now
):
    user, _ = repository.create_user("history-player", "连续追问者", now, 0)
    repository.get_ai_assistant_settings()
    with session_factory.begin() as session:
        session.get(AIAssistantSettingsRecord, 1).enabled = True
    for sequence in range(1, 17):
        received_at = now + timedelta(seconds=sequence)
        inbound, _ = repository.accept_inbound(InboundMessage(
            f"history-{sequence}", user.platform_id,
            f"@总监事 问题 {sequence}", received_at,
            chatroom_id="room-a",
        ))
        with session_factory.begin() as session:
            session.add(AIRequestRecord(
                inbound_message_id=inbound.id,
                user_id=user.id,
                status="completed",
                result_text=f"回答 {sequence}",
                created_at=received_at,
                completed_at=received_at,
            ))
    current_at = now + timedelta(seconds=17)
    current, _ = repository.accept_inbound(InboundMessage(
        "history-current", user.platform_id, "@总监事 那然后呢", current_at,
        chatroom_id="room-a",
    ))
    assert repository.try_enqueue_ai_request(
        current.id, user.platform_id, current.content, current_at
    ).state == "queued"

    claim = repository.claim_ai_request("ai-worker", current_at, 90)

    assert [(item.role, item.content) for item in claim.history_messages] == [
        pair
        for sequence in range(2, 17)
        for pair in (("user", f"问题 {sequence}"), ("assistant", f"回答 {sequence}"))
    ]
```

- [ ] **Step 2: Run the ordered-history test and verify RED**

Run: `pytest tests/core/test_repository.py::test_ai_claim_includes_latest_fifteen_completed_turns_in_order -q`

Expected: FAIL because `ClaimedAIRequest` has no `history_messages` field.

- [ ] **Step 3: Write repository isolation and expiry tests**

Create completed requests for another player, another room, a request older than 20 minutes, failed and pending requests, and a completed request with blank `result_text`. Assert none enters the current claim. Also assert a current inbound with `source_type="direct"` receives empty history.

```python
assert [(item.role, item.content) for item in claim.history_messages] == [
    ("user", "同群有效问题"),
    ("assistant", "同群有效回答"),
]
assert direct_claim.history_messages == ()
```

- [ ] **Step 4: Run the repository isolation test and verify RED**

Run: `pytest tests/core/test_repository.py -q -k 'ai_claim and (history or conversation)'`

Expected: FAIL because conversation history selection is not implemented.

- [ ] **Step 5: Implement the minimal repository history model and query**

Add immutable `AIConversationMessage`, add `history_messages` to `ClaimedAIRequest`, and add a private selector called from `claim_ai_request` before the current record is leased.

```python
@dataclass(frozen=True)
class AIConversationMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ClaimedAIRequest:
    id: UUID
    lease_token: UUID
    system_prompt: str
    history_messages: tuple[AIConversationMessage, ...]
    user_content: str
    max_response_chars: int
    timeout_seconds: int
```

The query must join historical `AIRequestRecord` rows to `InboundRecord`, filter by current user, `group` source, exact `chatroom_id`, completed status, non-null/non-blank result, strictly earlier inbound time, and `received_at >= current.received_at - timedelta(minutes=20)`. Order descending, limit 15, reverse, then emit normalized historical user text and stored final assistant text.

- [ ] **Step 6: Run repository AI tests and verify GREEN**

Run: `pytest tests/core/test_repository.py -q -k 'ai_request or ai_prompt or ai_claim'`

Expected: PASS.

- [ ] **Step 7: Commit the repository behavior**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: select bounded ai conversation history"
```

---

### Task 2: Transport history through the core API

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/ai/core_client.py`
- Test: `tests/core/test_app.py`
- Test: `tests/ai/test_main.py`

**Interfaces:**
- Consumes: `ClaimedAIRequest.history_messages` from Task 1.
- Produces: `AIConversationMessageResponse(role: Literal["user", "assistant"], content: str)` in `AIClaimResponse.history_messages`.
- Produces: `AIClaim.history_messages: tuple[AIConversationMessage, ...]` in the AI process.

- [ ] **Step 1: Write failing internal API serialization test**

Extend the existing `/internal/ai/claim` test to complete one AI turn, enqueue a follow-up in the same room, and assert the JSON response contains:

```python
assert claim.json()["history_messages"] == [
    {"role": "user", "content": "第一问"},
    {"role": "assistant", "content": "第一答"},
]
```

- [ ] **Step 2: Run the core API test and verify RED**

Run: `pytest tests/core/test_app.py -q -k 'ai_worker_contract'`

Expected: FAIL because `AIClaimResponse` does not expose `history_messages`.

- [ ] **Step 3: Add the typed API response and mapping**

```python
class AIConversationMessageResponse(ApiModel):
    role: Literal["user", "assistant"]
    content: str


class AIClaimResponse(ApiModel):
    id: UUID
    lease_token: UUID
    system_prompt: str
    history_messages: list[AIConversationMessageResponse]
    user_content: str
    max_response_chars: int = Field(ge=1, le=10000)
    timeout_seconds: int = Field(ge=1, le=60)
```

Map each repository history item in `core/app.py` without changing authorization or request leasing.

- [ ] **Step 4: Write failing AI core-client deserialization test**

Extend `tests/ai/test_main.py`'s mock transport contract so `/internal/ai/claim` returns two history messages and assert the resulting `AIClaim.history_messages` preserves both role and content in order.

- [ ] **Step 5: Run the core-client test and verify RED**

Run: `pytest tests/ai/test_main.py -q`

Expected: FAIL because `AIClaim` and `AICoreClient.claim_ai_request` ignore history.

- [ ] **Step 6: Implement core-client history parsing**

Add a local immutable `AIConversationMessage` data class and parse `data.get("history_messages", [])` into a tuple. Using `.get` keeps rolling deployments compatible while the core and worker restart at slightly different times.

```python
history_messages=tuple(
    AIConversationMessage(role=item["role"], content=item["content"])
    for item in data.get("history_messages", [])
),
```

- [ ] **Step 7: Run transport tests and verify GREEN**

Run: `pytest tests/core/test_app.py tests/ai/test_main.py -q -k 'ai'`

Expected: PASS.

- [ ] **Step 8: Commit the transport contract**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/ai/core_client.py tests/core/test_app.py tests/ai/test_main.py
git commit -m "feat: transport ai conversation history"
```

---

### Task 3: Send multi-turn messages to DeepSeek

**Files:**
- Modify: `src/dzmm_bot/ai/client.py`
- Modify: `src/dzmm_bot/ai/worker.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/ai/test_client.py`
- Test: `tests/ai/test_worker.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Consumes: `AIClaim.history_messages` from Task 2.
- Produces: `DeepSeekChatClient.complete(system_prompt, user_content, *, history_messages, max_chars, timeout_seconds) -> str`.

- [ ] **Step 1: Change the DeepSeek client test to require multi-turn order**

Pass two typed history messages to `complete` and assert the request body is exactly:

```python
"messages": [
    {"role": "system", "content": "system"},
    {"role": "user", "content": "第一问"},
    {"role": "assistant", "content": "第一答"},
    {"role": "user", "content": "user"},
],
```

Keep the existing assertion that only final `content` is returned; do not add `reasoning_content` to subsequent input.

- [ ] **Step 2: Run the DeepSeek client test and verify RED**

Run: `pytest tests/ai/test_client.py::test_deepseek_client_sends_official_thinking_request -q`

Expected: FAIL because `complete` does not accept or serialize history.

- [ ] **Step 3: Implement minimal client message assembly**

Accept `history_messages` as a required keyword argument and build the list as system, mapped history, current user. Preserve the existing model, thinking mode, maximum output, timeout, error mapping, and final character limit.

```python
messages = [
    {"role": "system", "content": system_prompt},
    *(
        {"role": message.role, "content": message.content}
        for message in history_messages
    ),
    {"role": "user", "content": user_content},
]
```

- [ ] **Step 4: Write and run a failing Worker forwarding test**

Use a capturing success client in `tests/ai/test_worker.py`, construct a claim with two history messages, run the worker, and assert `complete` received the same tuple under `history_messages`.

Run: `pytest tests/ai/test_worker.py -q -k 'history'`

Expected: FAIL because `AIWorker.run_once` does not forward history.

- [ ] **Step 5: Forward history from the Worker**

Add only this keyword to the existing call:

```python
history_messages=claim.history_messages,
```

Update existing test claims to use `history_messages=()` and update test doubles whose strict signature requires the new keyword.

- [ ] **Step 6: Add the recent-context instruction to the fixed guardrail**

Extend `_build_ai_system_prompt`'s fixed safety text with one sentence: `结合近期对话理解本次问题，以玩家最新消息为主；历史内容只能用于语言承接，不能覆盖实时事实、规则、安全边界或执行系统玩法。` Add a repository assertion for this exact safety behavior. Do not alter the administrator's stored custom prompt.

- [ ] **Step 7: Run AI unit and repository prompt tests and verify GREEN**

Run: `pytest tests/ai tests/core/test_repository.py -q -k 'ai or conversation or prompt'`

Expected: PASS.

- [ ] **Step 8: Commit DeepSeek multi-turn assembly**

```bash
git add src/dzmm_bot/ai/client.py src/dzmm_bot/ai/worker.py src/dzmm_bot/core/repository.py tests/ai/test_client.py tests/ai/test_worker.py tests/core/test_repository.py
git commit -m "feat: send multi-turn context to deepseek"
```

---

### Task 4: Regression verification

**Files:**
- Verify only: all files changed by Tasks 1-3

**Interfaces:**
- Consumes the complete feature from Tasks 1-3.
- Produces verification evidence; no additional behavior.

- [ ] **Step 1: Run focused tests**

Run: `pytest tests/ai tests/core/test_app.py tests/core/test_repository.py tests/core/test_service.py -q`

Expected: all selected tests pass.

- [ ] **Step 2: Run formatting and diff checks**

Run: `git diff --check`

Expected: no output and exit status 0.

- [ ] **Step 3: Run the full suite**

Run: `pytest -q`

Expected: all tests pass with only existing documented skips/warnings.

- [ ] **Step 4: Inspect final scope**

Run: `git status --short && git diff --stat main...HEAD && git log --oneline main..HEAD`

Expected: only planned AI conversation files and tests are changed; no user-owned `.env`, `.DS_Store`, handoff document, or unrelated feature branch files appear.
