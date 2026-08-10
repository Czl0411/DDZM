# AI Stable Impressions and Activity Facts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace free-text memory rewrites with isolated, batch-stabilized player impressions and idempotent game/activity facts that never ingest commands or gameplay dialogue.

**Architecture:** Mark each inbound message as memory-eligible at the Core boundary, enqueue one per-player job after a configurable count, and process structured DeepSeek operations in a separate Memory Worker. Store administrator-pinned impressions, automatic candidates, stable entries, and compact activity statistics separately; keep the old free-text memory only as a non-injected legacy backup.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic, PostgreSQL/SQLite, DeepSeek chat completions, vanilla JavaScript, pytest, systemd.

## Global Constraints

- Merge `codex/blame-bomb-game` first so Alembic revision `20260810_30` and the approved blame-game settlement paths exist before this plan starts.
- Use Alembic revision `20260810_31` with `down_revision = "20260810_30"`.
- Keep existing `ai_player_memories.memory_text` as a legacy backup; never inject it into new AI replies and never auto-convert it.
- The six category keys are exactly: `expression_style`, `group_interaction`, `humor_style`, `interests`, `supervisor_interaction`, `boundaries`.
- Commands, parenthesized observer messages, random-event dialogue, and any active-game dialogue are never memory-eligible.
- A candidate requires support in two separate completed batches before promotion; repeated operations inside one completion count once.
- Administrator-created or edited entries are pinned and cannot be changed by automatic operations.
- Memory work never consumes daily AI quota and never runs in the normal AI reply worker.
- Activity facts are written only by server settlement paths, use a unique event key, and store totals plus the latest result—not dialogue or per-round details.
- Preserve `.env`, `.DS_Store`, and `docs/BOT_MESSAGE_TRANSPORT_HANDOFF.md` as unrelated untracked files.

---

### Task 1: Persist eligibility, structured impressions, and activity facts

**Files:**
- Create: `migrations/versions/20260810_31_ai_stable_impressions.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/deploy/test_artifacts.py`

**Interfaces:**
- Produces: `AIPlayerImpressionRecord`, `AIImpressionCandidateRecord`, `AIActivityFactRecord`, and `AIActivityEventRecord` ORM records.
- Produces: `InboundRecord.ai_memory_eligible`, `AIPlayerMemoryRecord.pending_message_count`, `AIMemoryJobRecord.target_message_count`, and `AIMemoryJobRecord.available_at`.
- Produces: new `AIMemorySettingsRecord.batch_message_threshold`, `max_entries_per_category`, and `candidate_expiry_days` settings.

- [ ] **Step 1: Write the failing schema contract tests**

```python
def test_stable_impression_schema_separates_legacy_candidates_and_facts():
    from dzmm_bot.core.schema import (
        AIActivityEventRecord,
        AIActivityFactRecord,
        AIImpressionCandidateRecord,
        AIPlayerImpressionRecord,
        AIPlayerMemoryRecord,
        AIMemoryJobRecord,
        AIMemorySettingsRecord,
        Base,
        InboundRecord,
    )

    tables = Base.metadata.tables
    assert {
        "ai_player_impressions",
        "ai_impression_candidates",
        "ai_activity_facts",
        "ai_activity_events",
    } <= set(tables)
    assert InboundRecord.__table__.c.ai_memory_eligible.default.arg is False
    assert AIPlayerMemoryRecord.__table__.c.memory_text.name == "memory_text"
    assert AIPlayerMemoryRecord.__table__.c.pending_message_count.default.arg == 0
    assert AIMemoryJobRecord.__table__.c.target_message_count.nullable is False
    assert AIMemorySettingsRecord.__table__.c.batch_message_threshold.default.arg == 20
    assert AIPlayerImpressionRecord.__table__.c.pinned.nullable is False
    assert AIImpressionCandidateRecord.__table__.c.support_batches.default.arg == 1
    assert {column.name for column in AIActivityFactRecord.__table__.primary_key.columns} == {
        "user_id", "activity_type"
    }
    assert AIActivityEventRecord.__table__.c.event_key.primary_key is True
```

Add a migration artifact assertion:

```python
def test_stable_impression_migration_preserves_legacy_memory():
    migration = (ROOT / "migrations/versions/20260810_31_ai_stable_impressions.py").read_text()
    assert 'down_revision: str | None = "20260810_30"' in migration
    assert 'op.drop_column("ai_player_memories", "memory_text")' not in migration
    assert "ai_player_impressions" in migration
    assert "ai_activity_events" in migration
```

- [ ] **Step 2: Run the schema tests and verify they fail**

Run: `pytest tests/core/test_repository.py::test_stable_impression_schema_separates_legacy_candidates_and_facts tests/deploy/test_artifacts.py::test_stable_impression_migration_preserves_legacy_memory -v`

Expected: FAIL because the new columns, tables, and migration do not exist.

- [ ] **Step 3: Add the migration and ORM records**

Use these exact table contracts:

```python
class AIPlayerImpressionRecord(Base):
    __tablename__ = "ai_player_impressions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(String(240), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contradiction_batches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_supported_at: Mapped[datetime | None] = mapped_column(BeijingDateTime)
    created_at: Mapped[datetime] = mapped_column(BeijingDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(BeijingDateTime, nullable=False)

class AIImpressionCandidateRecord(Base):
    __tablename__ = "ai_impression_candidates"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(String(240), nullable=False)
    support_batches: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    conflict_entry_id: Mapped[UUID | None] = mapped_column(ForeignKey("ai_player_impressions.id"))
    last_supported_at: Mapped[datetime] = mapped_column(BeijingDateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(BeijingDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(BeijingDateTime, nullable=False)

class AIActivityFactRecord(Base):
    __tablename__ = "ai_activity_facts"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    activity_type: Mapped[str] = mapped_column(String(48), primary_key=True)
    participation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    win_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    loss_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_result: Mapped[str] = mapped_column(String(32), nullable=False)
    last_result_at: Mapped[datetime] = mapped_column(BeijingDateTime, nullable=False)

class AIActivityEventRecord(Base):
    __tablename__ = "ai_activity_events"
    event_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(BeijingDateTime, nullable=False)
```

Add indexes on `(user_id, category)` for entries and candidates, plus a unique constraint on `(user_id, category, content, conflict_entry_id)` for candidates. Add all new columns with server defaults, backfill existing rows, then remove server defaults where the ORM supplies values. Do not alter or clear `ai_player_memories.memory_text`.

- [ ] **Step 4: Run the schema tests and the migration smoke tests**

Run: `pytest tests/core/test_repository.py::test_stable_impression_schema_separates_legacy_candidates_and_facts tests/deploy/test_artifacts.py::test_stable_impression_migration_preserves_legacy_memory -v`

Expected: PASS.

- [ ] **Step 5: Commit the persistence contract**

```bash
git add migrations/versions/20260810_31_ai_stable_impressions.py src/dzmm_bot/core/schema.py tests/core/test_repository.py tests/deploy/test_artifacts.py
git commit -m "feat: add structured AI impression storage"
```

---

### Task 2: Classify ordinary chat and enqueue threshold batches

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/service.py`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_service.py`

**Interfaces:**
- Produces: `CoreRepository.record_ai_memory_message(message_id: UUID, platform_id: str, eligible: bool, now: datetime) -> None`.
- Produces: `CoreRepository.user_has_active_game_context(platform_id: str) -> bool`.
- Consumes: eligibility and counter columns from Task 1.

- [ ] **Step 1: Write failing tests for eligibility and threshold scheduling**

```python
def test_twenty_ordinary_messages_enqueue_memory_without_ai_quota(repository, now):
    from dzmm_bot.core.schema import AIPlayerMemoryRecord, AIMemoryJobRecord, DailyAIUsageRecord
    user, _ = repository.create_user("observer", "观察员", now, 0)
    repository.set_ai_memory_settings(
        enabled=True,
        extraction_prompt="只提取稳定可观察倾向",
        batch_message_threshold=20,
        max_entries_per_category=3,
        candidate_expiry_days=30,
    )
    for index in range(20):
        inbound, _ = repository.accept_inbound(
            InboundMessage(f"ordinary-{index}", user.platform_id, f"普通聊天 {index}", now + timedelta(seconds=index))
        )
        repository.record_ai_memory_message(inbound.id, user.platform_id, True, inbound.received_at)
    with repository._session() as session:
        assert session.get(AIPlayerMemoryRecord, user.id).pending_message_count == 20
        assert session.get(AIMemoryJobRecord, user.id).target_message_count == 20
        assert session.scalar(select(DailyAIUsageRecord)) is None
```

```python
def test_commands_and_active_game_dialogue_are_not_memory_eligible(session_factory):
    service, repository = _service(session_factory)
    now = datetime(2026, 8, 10, 12, 0, tzinfo=BEIJING)
    _receive(service, "join", "player", "/入职 玩家", now)
    _receive(service, "command", "player", "/打卡", now + timedelta(seconds=1))
    _receive(service, "observer", "player", "（围观）", now + timedelta(seconds=2))
    with session_factory() as session:
        rows = list(session.scalars(select(InboundRecord).order_by(InboundRecord.received_at)))
        assert [row.ai_memory_eligible for row in rows] == [False, False, False]
```

Add one test using an active random event participant and one using an active undercover/blame participant; plain natural-language gameplay dialogue must remain `False`. A plain non-game message after the game ends must become `True`.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest tests/core/test_repository.py::test_twenty_ordinary_messages_enqueue_memory_without_ai_quota tests/core/test_service.py::test_commands_and_active_game_dialogue_are_not_memory_eligible -v`

Expected: FAIL because message eligibility and threshold scheduling are absent.

- [ ] **Step 3: Implement message classification at the Core boundary**

In `CoreService.receive_inbound`, leave `ai_memory_eligible=False` as the safe default. After random-event classification and command/game handling, call:

```python
eligible = (
    bool(message.content.strip())
    and not message.content.lstrip().startswith(("/", "(", "（"))
    and event_message_status == "none"
    and not self._repository.user_has_active_game_context(message.sender_platform_id)
)
self._repository.record_ai_memory_message(
    stored.id, message.sender_platform_id, eligible, message.received_at
)
```

Before every early return caused by random-event participant/observer handling, call the same repository method with `eligible=False`. `user_has_active_game_context` must check active participation in random events, undercover, memory assessment, hide-and-seek selection, and blame game. It must not exclude ordinary chat merely because an unrelated player has an active solo game.

- [ ] **Step 4: Implement threshold enqueueing and remove `@总监事` coupling**

`record_ai_memory_message` must:

1. Persist the eligibility flag on the inbound row.
2. Return without creating memory state when `eligible` is false, memory is disabled, or the sender is not an employee.
3. Create `AIPlayerMemoryRecord` with the existing `memory_text` backup untouched and increment `pending_message_count`.
4. When the count reaches `batch_message_threshold`, upsert the one per-user `AIMemoryJobRecord`.
5. Update a pending job target to the newest eligible message and current count; never mutate a leased job target.

Remove memory-job creation from `try_enqueue_ai_request`; that method must only enforce quota and enqueue the visible AI reply.

- [ ] **Step 5: Run repository and service tests**

Run: `pytest tests/core/test_repository.py tests/core/test_service.py -v`

Expected: PASS, including existing AI quota and duplicate-message tests.

- [ ] **Step 6: Commit message eligibility and scheduling**

```bash
git add src/dzmm_bot/core/repository.py src/dzmm_bot/core/service.py tests/core/test_repository.py tests/core/test_service.py
git commit -m "feat: schedule impressions from ordinary chat"
```

---

### Task 3: Define structured impression operations and deterministic merge rules

**Files:**
- Create: `src/dzmm_bot/ai/impressions.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `tests/ai/test_impressions.py`
- Modify: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `IMPRESSION_CATEGORIES`, `parse_impression_operations(text: str) -> tuple[AIImpressionOperation, ...]`, and `render_impression_prompt(...) -> str`.
- Produces API action values: `new_candidate`, `reinforce_candidate`, `weaken_entry`, `replace_entry`, `keep`.
- Changes: `claim_ai_memory_job` returns stable entries, candidates, source messages, and `source_message_count`.
- Changes: `complete_ai_memory_job(..., operations: list[AIImpressionOperationModel], source_message_count: int, now: datetime) -> bool`.

- [ ] **Step 1: Write failing parser tests**

```python
def test_parse_impression_operations_accepts_only_the_contract():
    text = '{"operations":[{"action":"new_candidate","category":"interests","content":"持续关注桌游"}]}'
    assert parse_impression_operations(text)[0].content == "持续关注桌游"

@pytest.mark.parametrize("payload", [
    "not json",
    '{"operations":[{"action":"new_candidate","category":"diagnosis","content":"焦虑"}]}',
    '{"operations":[{"action":"new_candidate","category":"interests","content":""}]}',
    '{"operations":[{"action":"reinforce_candidate","candidate_id":"bad"}]}',
])
def test_parse_impression_operations_rejects_invalid_or_unsafe_payloads(payload):
    with pytest.raises(ValueError):
        parse_impression_operations(payload)
```

- [ ] **Step 2: Write failing merge tests**

Cover these exact cases in `tests/core/test_repository.py`:

- First batch `new_candidate` creates support count `1` but no stable entry.
- A later batch `reinforce_candidate` promotes at support count `2`.
- Two identical operations in one completion increment only once.
- `replace_entry` creates a conflict candidate; a later reinforcement replaces an automatic entry.
- Two separate `weaken_entry` batches delete an automatic entry.
- Pinned entries ignore weaken and replace operations.
- Expired candidates are removed when a new job is claimed.
- A full category keeps an unpromoted candidate instead of exceeding `max_entries_per_category`.

Use operations shaped as:

```python
{"action": "new_candidate", "category": "expression_style", "content": "偏好简短直接的回复"}
{"action": "reinforce_candidate", "candidate_id": str(candidate.id)}
{"action": "weaken_entry", "entry_id": str(entry.id)}
{"action": "replace_entry", "entry_id": str(entry.id), "category": "expression_style", "content": "更偏好分步骤解释"}
{"action": "keep"}
```

- [ ] **Step 3: Run parser and merge tests to verify failure**

Run: `pytest tests/ai/test_impressions.py tests/core/test_repository.py -k 'impression or memory_completion' -v`

Expected: FAIL because the parser and merge contract do not exist.

- [ ] **Step 4: Implement strict parsing and prompt rendering**

`parse_impression_operations` must call `json.loads`, require a top-level `operations` list of at most 50 items, reject unknown fields/actions/categories, enforce content length `1..240`, and parse referenced IDs as UUIDs. Do not accept Markdown code fences.

`render_impression_prompt` must enumerate stable and candidate IDs, describe the six categories and prohibited inferences, and demand the exact JSON object. Include this instruction verbatim:

```text
只分析本批普通群聊。不得记录指令、游戏过程、随机事件过程、一次性情绪、第三方描述、隐私、心理诊断、道德判断或负面人格标签。单批内容只能支持候选，不能自行声明稳定结论。仅输出 JSON，不输出 Markdown。
```

- [ ] **Step 5: Implement deterministic repository merging**

Validate every referenced candidate/entry belongs to the claimed user. Deduplicate candidate IDs, entry IDs, and normalized `(category, content, conflict_entry_id)` values within one completion. Normalize only by trimming and collapsing whitespace; semantic similarity comes from the model referencing an existing candidate ID.

Promotion and replacement threshold is exactly `2` separate batches. Automatic entries start with `source="auto"`, `pinned=False`, and `contradiction_batches=0`. Administrator entries are never mutated. Expire candidates whose `last_supported_at < now - timedelta(days=settings.candidate_expiry_days)`.

On successful completion, advance `last_scanned_message_id`, subtract `source_message_count` from `pending_message_count`, and release the lease. If the remaining count still meets the threshold, retarget the same job to the newest later eligible inbound and leave it `pending`; otherwise mark it `completed`.

- [ ] **Step 6: Run focused and full Core repository tests**

Run: `pytest tests/ai/test_impressions.py tests/core/test_repository.py -v`

Expected: PASS.

- [ ] **Step 7: Commit the structured merge contract**

```bash
git add src/dzmm_bot/ai/impressions.py src/dzmm_bot/core/api_models.py src/dzmm_bot/core/repository.py tests/ai/test_impressions.py tests/core/test_repository.py
git commit -m "feat: stabilize player impressions across batches"
```

---

### Task 4: Expose structured memory jobs over the Core API

**Files:**
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/ai/core_client.py`
- Modify: `tests/core/test_app.py`
- Modify: `tests/ai/test_worker.py`

**Interfaces:**
- Consumes: structured claim and completion methods from Task 3.
- Produces: `AIMemoryClaim.stable_entries`, `candidates`, `source_messages`, and `source_message_count`.
- Produces: completion JSON `{"operations": [...], "source_message_count": N}`.

- [ ] **Step 1: Rewrite the failing Core API contract test**

Replace the old free-text completion assertion with:

```python
claim = client.post("/internal/ai/memory/claim", headers=headers, json={
    "worker_id": "memory-1", "now": NOW.isoformat(), "lease_seconds": 90,
})
assert claim.status_code == 200
assert claim.json()["source_message_count"] == len(claim.json()["source_messages"])
assert claim.json()["stable_entries"] == []
assert claim.json()["candidates"] == []

completed = client.post(
    f"/internal/ai/memory/{claim.json()['user_id']}/completed",
    headers=headers,
    json={
        "worker_id": "memory-1",
        "lease_token": claim.json()["lease_token"],
        "target_message_id": claim.json()["target_message_id"],
        "source_message_count": claim.json()["source_message_count"],
        "operations": [{"action": "new_candidate", "category": "interests", "content": "持续关注桌游"}],
        "now": NOW.isoformat(),
    },
)
assert completed.json() == {"accepted": True}
```

- [ ] **Step 2: Run the API test and verify it fails**

Run: `pytest tests/core/test_app.py::test_ai_assistant_settings_and_lease_api_are_secret_free_and_fenced -v`

Expected: FAIL because the API still exposes `current_memory` and accepts `memory_text`.

- [ ] **Step 3: Update Pydantic responses, routes, and HTTP client dataclasses**

Remove `current_memory` and `memory_text` from the worker-facing contract. Keep error categories unchanged. Convert UUIDs at the HTTP boundary, and preserve lease fencing checks in the repository.

- [ ] **Step 4: Make failures retry safely**

On `fail_ai_memory_job`, set status back to `pending` and set:

```python
job.available_at = now + timedelta(seconds=min(300, 2 ** min(job.attempt_count, 8)))
```

The claim query must require `available_at <= now`. A failed task must retain its target and counters and must not change stable/candidate state.

- [ ] **Step 5: Run Core API and HTTP client tests**

Run: `pytest tests/core/test_app.py tests/ai/test_worker.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the structured worker API**

```bash
git add src/dzmm_bot/core/app.py src/dzmm_bot/ai/core_client.py src/dzmm_bot/core/repository.py tests/core/test_app.py tests/ai/test_worker.py
git commit -m "feat: expose structured impression jobs"
```

---

### Task 5: Split the normal AI worker from the Memory Worker

**Files:**
- Create: `src/dzmm_bot/ai/memory_worker.py`
- Create: `src/dzmm_bot/ai/memory_main.py`
- Modify: `src/dzmm_bot/ai/worker.py`
- Modify: `src/dzmm_bot/ai/main.py`
- Modify: `tests/ai/test_worker.py`
- Modify: `tests/ai/test_main.py`

**Interfaces:**
- Produces: `AIMemoryWorker.run_once() -> bool`.
- Consumes: `render_impression_prompt`, `parse_impression_operations`, and structured `AICorePort` methods.
- Changes: `AIWorker.run_once()` claims only `/internal/ai/claim` and never calls memory endpoints.

- [ ] **Step 1: Write failing worker-isolation tests**

```python
def test_reply_worker_never_claims_memory_when_reply_queue_is_empty():
    core = FakeCore(None, memory_claim=memory_claim())
    assert AIWorker("ai-1", core, SuccessClient(), clock=lambda: NOW).run_once() is False
    assert core.memory_claim is not None

def test_memory_worker_parses_json_and_completes_structured_operations():
    core = FakeMemoryCore(memory_claim())
    client = SuccessClient('{"operations":[{"action":"new_candidate","category":"interests","content":"持续关注桌游"}]}')
    assert AIMemoryWorker("memory-1", core, client, clock=lambda: NOW).run_once() is True
    assert core.completed[0][-3][0].action == "new_candidate"
```

Also test invalid JSON maps to `invalid_response`, DeepSeek timeout maps to `timeout`, and an empty queue returns `False`.

- [ ] **Step 2: Run worker tests and verify they fail**

Run: `pytest tests/ai/test_worker.py tests/ai/test_main.py -v`

Expected: FAIL because `AIMemoryWorker` and the isolated entrypoint do not exist.

- [ ] **Step 3: Implement the two focused workers**

`AIWorker` retains only visible reply claim/complete/fail behavior. `AIMemoryWorker` claims one memory task, renders the structured prompt, calls DeepSeek with `timeout_seconds=20` and `max_chars=8000`, parses strict JSON, and submits the parsed operations plus source count. Parsing errors must call the failure endpoint with `invalid_response`; no error is sent to the group.

- [ ] **Step 4: Implement `memory_main.py`**

Construct `AIMemoryWorker` with the same `Settings`, `AICoreClient`, and `DeepSeekChatClient` used by `ai/main.py`, but default worker ID to `ai-memory-worker-1` and read override `DZMM_AI_MEMORY_WORKER_ID`. Keep the loop interval at one second.

- [ ] **Step 5: Run AI tests**

Run: `pytest tests/ai -v`

Expected: PASS.

- [ ] **Step 6: Commit worker isolation**

```bash
git add src/dzmm_bot/ai/memory_worker.py src/dzmm_bot/ai/memory_main.py src/dzmm_bot/ai/worker.py src/dzmm_bot/ai/main.py tests/ai/test_worker.py tests/ai/test_main.py
git commit -m "feat: isolate AI memory processing"
```

---

### Task 6: Record compact activity facts idempotently

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `tests/core/test_repository.py`

**Interfaces:**
- Produces: `CoreRepository._record_ai_activity_fact(session, *, event_key: str, user_id: UUID, activity_type: str, result: str, occurred_at: datetime) -> bool`.
- Produces: `CoreRepository.list_ai_activity_facts(platform_id: str) -> tuple[AIActivityFact, ...]`.

- [ ] **Step 1: Write the failing idempotency test**

```python
def test_activity_fact_counts_each_settlement_event_once(repository, now):
    user, _ = repository.create_user("facts", "事实玩家", now, 0)
    with repository._session() as session:
        assert repository._record_ai_activity_fact(
            session,
            event_key="hide_and_seek:game-1:facts",
            user_id=user.id,
            activity_type="hide_and_seek",
            result="win",
            occurred_at=now,
        ) is True
        assert repository._record_ai_activity_fact(
            session,
            event_key="hide_and_seek:game-1:facts",
            user_id=user.id,
            activity_type="hide_and_seek",
            result="win",
            occurred_at=now,
        ) is False
    facts = repository.list_ai_activity_facts("facts")
    assert facts[0].participation_count == 1
    assert facts[0].win_count == 1
    assert facts[0].loss_count == 0
    assert facts[0].last_result == "win"
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/core/test_repository.py::test_activity_fact_counts_each_settlement_event_once -v`

Expected: FAIL because the helper and DTO do not exist.

- [ ] **Step 3: Implement the dialect-safe insert-once helper**

Accept result values `win`, `loss`, `ended`, and `cancelled`. Insert `AIActivityEventRecord` with PostgreSQL or SQLite `on_conflict_do_nothing(event_key)`. Only when the insert returns a row should the method create/update `AIActivityFactRecord`, increment participation, increment win/loss when applicable, and update the latest result/time.

- [ ] **Step 4: Run the focused test**

Run: `pytest tests/core/test_repository.py::test_activity_fact_counts_each_settlement_event_once -v`

Expected: PASS.

- [ ] **Step 5: Commit the fact recorder**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: record idempotent AI activity facts"
```

---

### Task 7: Emit facts from every formal game settlement

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `tests/core/test_repository.py`

**Interfaces:**
- Consumes: `_record_ai_activity_fact` from Task 6.
- Produces facts for activity types `random_event`, `hide_and_seek`, `memory_assessment_single`, `memory_assessment_duel`, `undercover`, and `blame_bomb`.

- [ ] **Step 1: Add failing settlement integration tests**

Add one test per terminal business path:

1. Hide-and-seek `won` writes `win`; `found` writes `loss`; timeout cancellation writes `cancelled` once.
2. Random-event `/退出` after required rounds writes `win`; early exit writes `loss`; signup exit writes nothing.
3. Memory single `completed`/`cashed_out` writes `win`; wrong answer writes `loss`.
4. Memory duel writes winner `win` and every other participant `loss`; collected/timeout writes every participant `loss`.
5. Undercover settlement writes each player `win` or `loss` according to the winning role; participant-forced end writes `ended` for each player.
6. Blame-bomb settlement writes the holder/active quitter `loss` and every other player `win`; administrator cancellation writes `cancelled` for every started player.
7. Calling the same job/settlement path twice leaves all counts unchanged.

For every test, assert `list_ai_activity_facts` contains totals and latest result only; do not assert or store dialogue, choices, reasons, words, roles, scene names, or commands.

- [ ] **Step 2: Run settlement tests and verify they fail**

Run: `pytest tests/core/test_repository.py -k 'activity_fact or settlement_records_fact' -v`

Expected: FAIL because settlement paths do not emit facts.

- [ ] **Step 3: Add fact writes inside existing settlement transactions**

Use deterministic event keys:

```text
random_event:{event.id}:{user.id}
hide_and_seek:{game.id}:{user.id}
memory_assessment_single:{game.id}:{user.id}
memory_assessment_duel:{game.id}:{user.id}
undercover:{game.id}:{user.id}
blame_bomb:{game.id}:{user.id}
```

Write facts immediately after the existing game state becomes terminal and before the transaction exits. Reuse one helper per multiplayer game to iterate its frozen participant rows so command settlement, timeout settlement, and leave settlement all call the same fact-writing path.

- [ ] **Step 4: Run all game repository and command tests**

Run: `pytest tests/core/test_repository.py tests/core/test_group_commands.py -v`

Expected: PASS with no changes to economy totals or existing reply text.

- [ ] **Step 5: Commit settlement fact integration**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: summarize settled game outcomes"
```

---

### Task 8: Replace the administrator free-text editor with categorized impressions

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `tests/core/test_app.py`
- Modify: `tests/admin/test_app.py`

**Interfaces:**
- Produces: `GET /internal/game/users/{platform_id}/ai-memory` returning `impressions`, `activity_facts`, `legacy_memory_text`, and `updated_at`.
- Produces: `POST /internal/game/users/{platform_id}/ai-impressions` for a new pinned entry.
- Produces: `PUT /internal/game/users/{platform_id}/ai-impressions/{entry_id}` for content/category/pinned edits.
- Produces: `DELETE /internal/game/users/{platform_id}/ai-impressions/{entry_id}` and `DELETE /internal/game/users/{platform_id}/ai-memory`.

- [ ] **Step 1: Write failing Core and admin proxy API tests**

```python
created = client.post(
    "/internal/game/users/player/ai-impressions",
    headers=headers,
    json={"category": "expression_style", "content": "偏好先给结论"},
)
assert created.json()["pinned"] is True
memory = client.get("/internal/game/users/player/ai-memory", headers=headers).json()
assert memory["impressions"][0]["content"] == "偏好先给结论"
assert "legacy_memory_text" in memory
assert isinstance(memory["activity_facts"], list)
```

Test invalid categories, blank/over-240 content, editing another user's entry, unpinning, deletion, and clearing. Clearing must delete stable entries/candidates/jobs, set the scan cutoff to the latest current inbound, reset pending count, and preserve `legacy_memory_text`.

- [ ] **Step 2: Run API tests and verify they fail**

Run: `pytest tests/core/test_app.py tests/admin/test_app.py -k 'ai_memory or ai_impression' -v`

Expected: FAIL because only the old free-text PUT API exists.

- [ ] **Step 3: Implement repository CRUD and Core API models**

Administrator create/edit operations set `source="admin"`. Create and content/category edits set `pinned=True`; an explicit `pinned=False` request is the only way to release the entry to automatic handling. Validate the same six category keys and 240-character limit used by the worker parser.

- [ ] **Step 4: Implement admin proxy methods and versioned routes**

Use existing `versioned_configuration_response` with scopes containing both platform ID and entry ID. Keep GET read-only and authenticated. Remove the old free-text PUT proxy after the front end is migrated in Task 9.

- [ ] **Step 5: Run API tests**

Run: `pytest tests/core/test_app.py tests/admin/test_app.py -k 'ai_memory or ai_impression' -v`

Expected: PASS.

- [ ] **Step 6: Commit categorized impression APIs**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/core/repository.py src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py tests/core/test_app.py tests/admin/test_app.py
git commit -m "feat: manage categorized player impressions"
```

---

### Task 9: Update AI settings and player-memory administration UI

**Files:**
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `tests/admin/test_app.py`
- Modify: `tests/admin/test_package_data.py`

**Interfaces:**
- Consumes: categorized API from Task 8.
- Changes settings fields to `memory_enabled`, `extraction_prompt`, `batch_message_threshold`, `max_entries_per_category`, and `candidate_expiry_days`.
- Leaves `gameplay_guide` temporarily read-compatible until the knowledge-card plan removes it.

- [ ] **Step 1: Write failing rendered-asset assertions**

```python
def test_admin_renders_structured_ai_memory_controls(client, headers):
    page = client.get("/", headers=headers).text
    script = client.get("/static/admin.js", headers=headers).text
    assert 'id="ai-memory-batch-threshold"' in page
    assert 'id="ai-memory-max-entries"' in page
    assert 'id="ai-memory-candidate-expiry-days"' in page
    assert 'id="employee-memory-impressions"' in page
    assert 'id="employee-memory-activity-facts"' in page
    assert 'data-impression-category' in script
    assert 'memory_text:' not in script
```

- [ ] **Step 2: Run the UI test and verify it fails**

Run: `pytest tests/admin/test_app.py::test_admin_renders_structured_ai_memory_controls -v`

Expected: FAIL because the old free-text controls are still rendered.

- [ ] **Step 3: Replace settings controls and payload fields**

Use numeric bounds:

- batch threshold `5..200`, default `20`;
- entries per category `1..10`, default `3`;
- candidate expiry `1..365` days, default `30`.

The summary card must say `每 20 条有效普通消息更新` using the configured value. Remove the obsolete first-history and free-text length controls. Keep the extraction prompt as an advanced text area.

- [ ] **Step 4: Replace the player modal**

Render six category sections. Each existing entry gets Edit, Delete, and Pin/Unpin controls. Add-entry controls select one of the six localized categories. Render activity facts as read-only rows containing participation, win, loss, latest result, and latest time. Show the legacy backup in a closed `<details>` element and never send it back automatically.

The “清空印象” action must call DELETE and update the UI without claiming that old messages will be reprocessed.

- [ ] **Step 5: Run admin tests**

Run: `pytest tests/admin -v`

Expected: PASS.

- [ ] **Step 6: Commit the structured memory UI**

```bash
git add src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css src/dzmm_bot/admin/app.py src/dzmm_bot/core/app.py src/dzmm_bot/core/api_models.py tests/admin/test_app.py tests/admin/test_package_data.py
git commit -m "feat: show stable impressions in admin"
```

---

### Task 10: Inject only stable impressions into normal AI replies

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_app.py`

**Interfaces:**
- Produces: `_format_player_impressions(entries: Sequence[AIPlayerImpressionRecord]) -> str`.
- Changes: `_build_ai_system_prompt(..., player_impressions: str)` replaces `player_memory`.

- [ ] **Step 1: Write the failing prompt-priority test**

```python
def test_ai_prompt_uses_stable_and_pinned_impressions_but_not_legacy_memory(repository, now):
    user, _ = repository.create_user("prompt-user", "玩家", now, 0)
    repository.set_ai_player_legacy_memory_for_test(user.id, "旧的混乱记忆")
    repository.create_ai_player_impression("prompt-user", "expression_style", "偏好先给结论", now)
    claim = _enqueue_and_claim_ai(repository, user, now)
    assert "【稳定玩家印象】" in claim.system_prompt
    assert "偏好先给结论" in claim.system_prompt
    assert "旧的混乱记忆" not in claim.system_prompt
    assert claim.system_prompt.index("【实时玩家资料】") < claim.system_prompt.index("【稳定玩家印象】")
```

Use direct test setup for the legacy row; do not add a production-only test helper.

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/core/test_repository.py::test_ai_prompt_uses_stable_and_pinned_impressions_but_not_legacy_memory -v`

Expected: FAIL because the prompt still reads `AIPlayerMemoryRecord.memory_text`.

- [ ] **Step 3: Format stable entries deterministically**

Order categories by the fixed six-category order, then pinned entries before automatic entries, then creation time. Format only category labels and content. Enforce a final 2400-character cap on the entire impression block; truncate automatic entries before pinned entries if necessary.

- [ ] **Step 4: Remove legacy memory injection**

`claim_ai_request` must query `AIPlayerImpressionRecord` and pass the formatted block. Keep real-time nickname, rank, department, balance, and currency ahead of impressions. No candidate or activity fact is injected by default; activity facts are available for the later authoritative-knowledge context only when relevant.

- [ ] **Step 5: Run AI/Core tests**

Run: `pytest tests/core/test_repository.py tests/core/test_app.py tests/ai -v`

Expected: PASS.

- [ ] **Step 6: Commit stable prompt injection**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py tests/core/test_app.py
git commit -m "feat: personalize AI with stable impressions"
```

---

### Task 11: Deploy the independent Memory Worker and verify isolation

**Files:**
- Create: `deploy/systemd/dzmm-ai-memory-worker.service`
- Modify: `deploy/scripts/deploy.sh`
- Modify: `tests/deploy/test_artifacts.py`
- Modify: `tests/runtime/test_production_entrypoints.py`
- Modify: `rule.md`

**Interfaces:**
- Produces: systemd unit invoking `python -m dzmm_bot.ai.memory_main`.
- Keeps: existing `dzmm-ai-worker.service` for visible replies only.

- [ ] **Step 1: Write failing deployment assertions**

```python
def test_deployment_starts_a_separate_ai_memory_worker():
    memory_worker = (ROOT / "deploy/systemd/dzmm-ai-memory-worker.service").read_text()
    deploy = (ROOT / "deploy/scripts/deploy.sh").read_text()
    assert "Description=DZMM DeepSeek AI Memory Worker" in memory_worker
    assert "-m dzmm_bot.ai.memory_main" in memory_worker
    assert "After=network-online.target dzmm-core.service" in memory_worker
    assert "dzmm-ai-memory-worker.service" in deploy
```

- [ ] **Step 2: Run deployment tests and verify they fail**

Run: `pytest tests/deploy/test_artifacts.py tests/runtime/test_production_entrypoints.py -v`

Expected: FAIL because the new unit is absent.

- [ ] **Step 3: Add and deploy the systemd unit**

Use the same `User`, `WorkingDirectory`, `EnvironmentFile`, and `Restart=on-failure` values as the visible AI worker. Add the new service to the single `systemctl restart` line after `dzmm-ai-worker.service`.

- [ ] **Step 4: Update the rule baseline**

Add a concise “AI 玩家印象” section stating that ordinary chat may produce delayed stable impressions, commands and gameplay dialogue are excluded, activity results come only from settlement, and administrator-pinned entries cannot be overwritten. Do not expose internal confidence or candidate mechanics as player commands.

- [ ] **Step 5: Run the complete verification suite**

Run: `pytest -q`

Expected: all tests PASS.

Run: `git diff --check`

Expected: no output.

- [ ] **Step 6: Commit deployment and documentation**

```bash
git add deploy/systemd/dzmm-ai-memory-worker.service deploy/scripts/deploy.sh tests/deploy/test_artifacts.py tests/runtime/test_production_entrypoints.py rule.md
git commit -m "ops: deploy isolated AI memory worker"
```
