# Lucky Red Packet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/发红包 人数 总金额` and `/抢红包` as a persistent, real-balance random red-packet feature with unique extrema, expiry refunds, a Beijing-time daily limit, editable replies, and admin settings.

**Architecture:** Put the constrained integer allocation algorithm in a small pure module, while keeping persistence and balance transactions in `CoreRepository` to match the existing transaction boundary. Persist one active global packet plus ordered shares, expose timeout/probability through the existing Core → Admin API relay, and route commands through `GroupCommandHandler` without registering the packet as an active game.

**Tech Stack:** Python 3.12+, SQLAlchemy 2, Alembic, FastAPI, vanilla HTML/JavaScript admin UI, pytest.

## Global Constraints

- `/发红包` and `/抢红包` perform balance mutations only for group messages from joined employees; direct messages only receive a “return to the group” reply.
- Player count is a half-width integer from `2` through `50`; total amount is a half-width integer from player count through `99999`.
- One global packet may be active at a time, but it does not enter unified gameplay state and does not block games or random events.
- The issuer may claim their own packet; one user may claim each packet at most once.
- Successful creation immediately deducts the full total and consumes one of exactly `5` daily starts, scoped to the Beijing calendar date.
- Default expiry is `10` minutes and configurable from `1` through `60`; default empty probability is `5%` and configurable from `0%` through `30%`.
- At most one share is zero; minimum and maximum amounts are each unique; middle amounts may tie.
- `2` players with total `2`, and `3+` players with total below `2 × player_count`, force an empty share. Otherwise configured probability decides.
- Expiry refunds only unclaimed shares. Creation funding, claims, and refunds use `red_packet_fund`, `red_packet_claim`, and `red_packet_refund` balance sources.
- Preserve `.env`, `.DS_Store`, and `docs/BOT_MESSAGE_TRANSPORT_HANDOFF.md`; do not stage or modify them.
- Do not deploy until the user explicitly requests production deployment after local verification.

---

### Task 1: Constrained Share Allocation

**Files:**
- Create: `src/dzmm_bot/core/red_packet.py`
- Create: `tests/core/test_red_packet.py`

**Interfaces:**
- Consumes: `player_count: int`, `total_amount: int`, `empty_probability_percent: int`, and an injected random source.
- Produces: `RedPacketAllocation(shares: tuple[int, ...], has_empty: bool)` and `generate_red_packet_allocation(player_count, total_amount, empty_probability_percent, rng) -> RedPacketAllocation` for repository creation.

- [ ] **Step 1: Write failing boundary and property tests**

```python
def test_five_players_five_coins_forces_one_empty_and_unique_extrema():
    result = generate_red_packet_allocation(5, 5, 5, StubRandom())
    assert sorted(result.shares) == [0, 1, 1, 1, 2]
    assert result.has_empty is True


@pytest.mark.parametrize("players,total", [(2, 2), (3, 3), (5, 9)])
def test_low_totals_force_empty(players, total):
    result = generate_red_packet_allocation(players, total, 0, StubRandom())
    assert result.shares.count(0) == 1


def test_generated_allocations_preserve_sum_and_unique_extrema():
    for players in (2, 3, 5, 50):
        for total in (players, max(players + 1, players * 2), 99999):
            result = generate_red_packet_allocation(players, total, 5, Random(7))
            assert len(result.shares) == players
            assert sum(result.shares) == total
            assert result.shares.count(0) <= 1
            assert result.shares.count(min(result.shares)) == 1
            assert result.shares.count(max(result.shares)) == 1
```

Also test rejection of booleans, full-width/non-integer equivalents passed at the command layer later, out-of-range numeric values, forced versus configured empty selection, and reproducible shuffling with a seeded random source.

- [ ] **Step 2: Run the allocation tests and verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/pytest tests/core/test_red_packet.py -q
```

Expected: collection fails because `dzmm_bot.core.red_packet` does not exist.

- [ ] **Step 3: Implement the minimal constructive allocator**

```python
@dataclass(frozen=True)
class RedPacketAllocation:
    shares: tuple[int, ...]
    has_empty: bool


def generate_red_packet_allocation(
    player_count: int,
    total_amount: int,
    empty_probability_percent: int,
    rng,
) -> RedPacketAllocation:
    _validate(player_count, total_amount, empty_probability_percent)
    forced_empty = (
        (player_count == 2 and total_amount == 2)
        or (player_count >= 3 and total_amount < player_count * 2)
    )
    has_empty = forced_empty or rng.randrange(100) < empty_probability_percent
    shares = (
        [0, *([1] * (player_count - 2)), 2]
        if has_empty
        else [1, 2]
        if player_count == 2
        else [1, *([2] * (player_count - 2)), 3]
    )
    remaining = total_amount - sum(shares)
    maximum_index = len(shares) - 1
    while remaining:
        eligible = [maximum_index, *(
            index
            for index in range(1, maximum_index)
            if shares[index] + 1 < shares[maximum_index]
        )]
        shares[rng.choice(eligible)] += 1
        remaining -= 1
    rng.shuffle(shares)
    _assert_invariants(shares, total_amount)
    return RedPacketAllocation(tuple(shares), has_empty)
```

Keep validation and invariant helpers private. Use `SystemRandom` in production and injected `Random`/stub objects in tests.

- [ ] **Step 4: Run allocation tests and verify GREEN**

Run:

```bash
PYTHONPATH=src .venv/bin/pytest tests/core/test_red_packet.py -q
```

Expected: all allocator tests pass.

- [ ] **Step 5: Commit the allocator**

```bash
git add src/dzmm_bot/core/red_packet.py tests/core/test_red_packet.py
git commit -m "feat: add constrained red packet allocation"
```

---

### Task 2: Persistent Schema, Migration, and Settings

**Files:**
- Create: `migrations/versions/20260811_36_lucky_red_packets.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/deploy/test_artifacts.py`

**Interfaces:**
- Consumes: SQLAlchemy `Base`, `UserRecord`, `BeijingDateTime`, and migration head `20260811_35`.
- Produces: `RedPacketSettings`, four mapped tables, `get_red_packet_settings()`, and `set_red_packet_settings(expiry_minutes, empty_probability_percent)`.

- [ ] **Step 1: Write failing metadata, defaults, validation, and migration tests**

Assert that metadata contains `red_packet_settings`, `red_packets`, `red_packet_shares`, and `red_packet_daily_starts`; that the active packet partial unique index is named `ux_red_packet_one_active`; and that constraints include `(packet_id, display_order)`, `(packet_id, claimant_user_id)`, and `(user_id, play_date)`.

```python
def test_red_packet_settings_defaults_and_validation(repository):
    assert repository.get_red_packet_settings() == RedPacketSettings(
        expiry_minutes=10,
        empty_probability_percent=5,
    )
    assert repository.set_red_packet_settings(20, 8) == RedPacketSettings(20, 8)
    with pytest.raises(ValueError, match="过期时间"):
        repository.set_red_packet_settings(0, 8)
    with pytest.raises(ValueError, match="空包概率"):
        repository.set_red_packet_settings(10, 31)
```

Extend the migration artifact test to expect head `20260811_36`, seeded settings `(10, 5)`, the four new tables, and successful downgrade back through revision 35.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/pytest tests/core/test_repository.py -k red_packet_settings -q
PYTHONPATH=src .venv/bin/pytest tests/deploy/test_artifacts.py::test_number_bomb_migration_extends_runtime_schema -q
```

Expected: metadata/settings assertions fail and migration head remains `20260811_35`.

- [ ] **Step 3: Add mapped records and settings repository methods**

Add:

```python
@dataclass(frozen=True)
class RedPacketSettings:
    expiry_minutes: int
    empty_probability_percent: int
```

Map these records:

- `RedPacketSettingsRecord(id, expiry_minutes, empty_probability_percent)`;
- `RedPacketRecord(id, active_key, issuer_user_id, target_count, total_amount, state, has_empty, created_at, expires_at, finished_at, refunded_amount)`;
- `RedPacketShareRecord(id, packet_id, display_order, amount, claimant_user_id, claimed_at)`;
- `RedPacketDailyStartRecord(id, user_id, play_date, count)`.

Use `active_key="global"` while open and set it to `None` on completion/expiry. Mirror the existing SQLite/PostgreSQL partial unique index pattern used by number bomb.

- [ ] **Step 4: Add Alembic revision 36**

Create all four tables, constraints, the partial unique active index, and the singleton settings row:

```python
revision = "20260811_36"
down_revision = "20260811_35"

op.bulk_insert(
    red_packet_settings,
    [{"id": 1, "expiry_minutes": 10, "empty_probability_percent": 5}],
)
```

Downgrade drops child tables before parents and leaves all earlier migrations untouched.

- [ ] **Step 5: Run focused schema and migration tests**

Run the two commands from Step 2.

Expected: PASS with migration head `20260811_36`.

- [ ] **Step 6: Commit persistence scaffolding**

```bash
git add migrations/versions/20260811_36_lucky_red_packets.py \
  src/dzmm_bot/core/schema.py src/dzmm_bot/core/repository.py \
  tests/core/test_repository.py tests/deploy/test_artifacts.py
git commit -m "feat: persist lucky red packets"
```

---

### Task 3: Atomic Creation, Claims, Settlement, and Expiry

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `tests/core/test_repository.py`

**Interfaces:**
- Consumes: `generate_red_packet_allocation`, red-packet mapped records, `BalanceTransactionRecord`, and repository transaction/session helpers.
- Produces: `create_red_packet(...)`, `claim_red_packet(...)`, `expire_red_packets(...)`, and result dataclasses used by commands and daily jobs.

- [ ] **Step 1: Write failing creation and accounting tests**

Cover joined/unjoined users, ASCII numeric bounds supplied as integers, insufficient balance, one active packet, exactly five successful Beijing-day starts, issuer funding transaction, generated share persistence, and rollback when share insertion fails.

```python
result = repository.create_red_packet("issuer", 5, 5, now)
assert result.status == "created"
assert repository.find_user("issuer").balance == 95
assert [share.amount for share in repository.list_red_packet_shares(result.packet_id)] == result.shares
```

Assert failed attempts create no packet, daily counter, or balance transaction.

- [ ] **Step 2: Run creation tests and verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/pytest tests/core/test_repository.py -k 'red_packet and (create or daily or funding)' -q
```

Expected: failures because lifecycle methods and result types do not exist.

- [ ] **Step 3: Implement creation in one transaction**

Define stable result contracts:

```python
@dataclass(frozen=True)
class RedPacketCreateResult:
    status: str
    packet_id: UUID | None = None
    issuer_display_name: str | None = None
    player_count: int = 0
    total_amount: int = 0
    expires_at: datetime | None = None
```

Implement `create_red_packet(self, platform_id: str, player_count: int, total_amount: int, now: datetime) -> RedPacketCreateResult`. Lock the singleton settings row, lazily expire a stale active packet, lock the issuer and daily counter, validate all state, allocate shares, apply `-total_amount` with `red_packet_fund`, increment the daily count, and flush the packet/shares before returning `created`.

- [ ] **Step 4: Write failing claim, completion, and expiry tests**

Cover issuer self-claim, one claim per employee, an empty share consuming a slot without a zero transaction, immediate positive credit, claim order, unique best/worst, final settlement, expiry refund of only unclaimed amounts, exact expiry boundary, and repeated expiry execution.

```python
claim = repository.claim_red_packet("issuer", now + timedelta(seconds=1))
assert claim.status in {"claimed", "completed"}
assert claim.claimed_count == 1

notices = repository.expire_red_packets(now + timedelta(minutes=10))
assert len(notices) == 1
assert repository.expire_red_packets(now + timedelta(minutes=11)) == ()
```

Add a concurrent/session-level regression showing the database constraints reject a duplicate claimant and a second active packet.

- [ ] **Step 5: Run claim/expiry tests and verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/pytest tests/core/test_repository.py -k 'red_packet and (claim or complete or expire or refund)' -q
```

Expected: failures because claim and expiry methods do not exist.

- [ ] **Step 6: Implement claim and expiry transactions**

Define:

```python
@dataclass(frozen=True)
class RedPacketClaimSummary:
    display_name: str
    amount: int
    display_order: int


@dataclass(frozen=True)
class RedPacketClaimResult:
    status: str
    claimant_display_name: str | None = None
    amount: int = 0
    claimed_count: int = 0
    player_count: int = 0
    claims: tuple[RedPacketClaimSummary, ...] = ()
```

Implement `claim_red_packet(self, platform_id: str, now: datetime) -> RedPacketClaimResult` and `expire_red_packets(self, now: datetime) -> tuple[str, ...]`.

Claim locks the active packet, rejects an existing `(packet_id, claimant_user_id)`, locks the first unclaimed share by `display_order`, writes the claimant/time, applies `red_packet_claim` only for positive amounts, and clears `active_key` on the last share. On completion, return all claims sorted by claim time/order so commands can render the unique extrema.

Expiry locks the active packet, sums unclaimed shares, applies one `red_packet_refund`, records `refunded_amount`, clears `active_key`, and returns exactly one rendered-data notice payload/message per newly expired packet.

- [ ] **Step 7: Integrate expiry with daily jobs**

In `run_daily_jobs`, enqueue every message returned by `expire_red_packets(now)` inside the existing outer transaction:

```python
for message in self.expire_red_packets(now):
    self.enqueue_system_outbound(message)
```

Tests must call `run_daily_jobs` twice and assert one refund and one outbound message.

- [ ] **Step 8: Run all repository red-packet tests**

Run:

```bash
PYTHONPATH=src .venv/bin/pytest tests/core/test_repository.py -k red_packet -q
```

Expected: all repository lifecycle tests pass.

- [ ] **Step 9: Commit lifecycle behavior**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: add atomic red packet lifecycle"
```

---

### Task 4: Group Commands, Editable Replies, and Help

**Files:**
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/service.py`
- Modify: `tests/core/test_group_commands.py`
- Modify: `tests/core/test_service.py`
- Modify: `tests/core/test_repository.py`
- Modify: `rule.md`

**Interfaces:**
- Consumes: `RedPacketCreateResult`, `RedPacketClaimResult`, `create_red_packet`, and `claim_red_packet`.
- Produces: `/发红包` and `/抢红包` routing, group/direct replies, completion rendering, command definitions, help entries, and managed templates.

- [ ] **Step 1: Write failing command and message tests**

Test exact command parsing and replies for:

- `/发红包 5 5` creation;
- full-width, missing, decimal, negative, count/amount limit rejection;
- direct-message rejection sent back to `message.chatroom_id` without a balance write;
- `/抢红包` success, issuer self-claim, duplicate claim, no active packet, empty claim;
- the final claim returning an immediate claim reply followed by full ordered statistics with unique best/worst labels;
- repeated platform message IDs not duplicating funding or claims;
- commands remaining usable while a random event is active.

```python
assert _latest_replies(factory)[-2:] == [
    "张三抢到 2 摸鱼币，剩余 0/2 份。",
    "【红包已抢完】\n1. 李四：空包\n2. 张三：2 摸鱼币\n手气最佳：张三（2）\n手气最差：李四（空包）",
]
```

- [ ] **Step 2: Run focused command/service tests and verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/pytest tests/core/test_group_commands.py tests/core/test_service.py -k red_packet -q
```

Expected: no replies because neither command is registered.

- [ ] **Step 3: Register commands and reply templates**

Add command definitions with exact syntax:

```python
("/发红包", "/发红包 人数 总金额", "创建随机运气红包"),
("/抢红包", "/抢红包", "领取当前随机运气红包"),
```

Add managed reply scenarios for usage, group-only, not joined, invalid parameters, insufficient balance, daily limit, active packet, created, no active packet, duplicate claim, claimed, completed, and expired. Variables include issuer, player count, total, expiry minutes, claimant, amount, remaining/total shares, ordered claim list, best, worst, refund, currency, and date as appropriate.

- [ ] **Step 4: Implement routing and rendering**

Parse with ASCII-only `str.isascii()` plus `str.isdigit()`. Return a direct `CommandReply` targeting `message.chatroom_id` when `source_type == "direct"`; otherwise call repository methods.

For completion, sort `result.claims` by `display_order`, locate the single min/max, render `0` as `空包`, and return `[claim_reply, settlement_reply]` in that order.

Add both commands to `/帮助 基础` and document the feature in `rule.md` using the approved rules.

- [ ] **Step 5: Keep red packets independent from event/game gates**

Allow `/发红包` and `/抢红包` through the direct-message dispatch branch so they can return group-only guidance, and bypass random-event command blocking for these two exact commands. Do not add red packets to `active_gameplay_summary`, `user_has_active_game_context`, or force-end routing.

- [ ] **Step 6: Run command, template, and service tests**

Run:

```bash
PYTHONPATH=src .venv/bin/pytest tests/core/test_group_commands.py tests/core/test_service.py tests/core/test_repository.py -k red_packet -q
```

Expected: all command, idempotency, template, and event-independence tests pass.

- [ ] **Step 7: Commit command integration**

```bash
git add src/dzmm_bot/core/commands.py src/dzmm_bot/core/reply_templates.py \
  src/dzmm_bot/core/repository.py src/dzmm_bot/core/service.py rule.md \
  tests/core/test_group_commands.py tests/core/test_service.py tests/core/test_repository.py
git commit -m "feat: add lucky red packet commands"
```

---

### Task 5: Core and Admin Configuration Surface

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `tests/core/test_app.py`
- Modify: `tests/admin/test_app.py`
- Modify: `tests/admin/test_package_data.py`

**Interfaces:**
- Consumes: `get_red_packet_settings()` and `set_red_packet_settings(expiry_minutes, empty_probability_percent)`.
- Produces: Core `/internal/game/red-packet/settings`, Admin `/api/game/red-packet/settings`, and the minigame settings card/modal.

- [ ] **Step 1: Write failing Core and Admin API tests**

```python
response = client.get("/internal/game/red-packet/settings", headers=headers)
assert response.json() == {"expiry_minutes": 10, "empty_probability_percent": 5}

updated = client.patch(
    "/internal/game/red-packet/settings",
    headers=headers,
    json={"expiry_minutes": 20, "empty_probability_percent": 8},
)
assert updated.json() == {"expiry_minutes": 20, "empty_probability_percent": 8}
```

Admin tests must verify authentication, exact request keys, optimistic configuration version/idempotency behavior, Core relay payload, and 422 responses outside `1–60`/`0–30`.

- [ ] **Step 2: Run API tests and verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/pytest tests/core/test_app.py tests/admin/test_app.py -k red_packet -q
```

Expected: 404 or missing client method failures.

- [ ] **Step 3: Add API models, Core endpoints, and Admin relay**

```python
class RedPacketSettingsResponse(ApiModel):
    expiry_minutes: int
    empty_probability_percent: int


class SetRedPacketSettingsRequest(ApiModel):
    expiry_minutes: int = Field(ge=1, le=60)
    empty_probability_percent: int = Field(ge=0, le=30)
```

Implement exact GET/PATCH paths in Core and Admin, add methods to the Admin Core protocol/client, and use the existing `versioned_configuration_response` with scope `red-packet-settings`.

- [ ] **Step 4: Write failing package/UI contract tests**

Assert the rendered HTML and packaged JavaScript contain:

- a “随机运气红包” settings card;
- inputs `red-packet-expiry-minutes` and `red-packet-empty-probability`;
- a modal save button;
- GET/PATCH calls to `/api/game/red-packet/settings`;
- client-side range validation matching server limits.

- [ ] **Step 5: Run UI contract tests and verify RED**

Run:

```bash
PYTHONPATH=src .venv/bin/pytest tests/admin/test_package_data.py tests/admin/test_app.py -k red_packet -q
```

Expected: missing selectors and endpoint strings.

- [ ] **Step 6: Add the minigame settings card and modal**

Follow the existing number-bomb UI pattern without refactoring the page. Load red-packet settings with the minigame pane, render `10 分钟` and `5%`, populate the modal, validate ranges, PATCH with `If-Match` and `Idempotency-Key`, refresh the card, and show the existing success/error toast.

- [ ] **Step 7: Run all settings/UI tests**

Run:

```bash
PYTHONPATH=src .venv/bin/pytest tests/core/test_app.py tests/admin/test_app.py tests/admin/test_package_data.py -k red_packet -q
```

Expected: all red-packet API and UI tests pass.

- [ ] **Step 8: Commit the configuration surface**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py \
  src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/app.py \
  src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js \
  tests/core/test_app.py tests/admin/test_app.py tests/admin/test_package_data.py
git commit -m "feat: manage lucky red packet settings"
```

---

### Task 6: Full Regression and Release Readiness

**Files:**
- Modify only files required to correct failures caused by Tasks 1–5.

**Interfaces:**
- Consumes: all red-packet implementation commits.
- Produces: a clean, tested feature branch ready for user-approved merge and deployment.

- [ ] **Step 1: Run focused red-packet coverage**

```bash
PYTHONPATH=src .venv/bin/pytest \
  tests/core/test_red_packet.py tests/core/test_repository.py \
  tests/core/test_group_commands.py tests/core/test_service.py \
  tests/core/test_app.py tests/admin/test_app.py tests/admin/test_package_data.py \
  tests/deploy/test_artifacts.py -k 'red_packet or migration_extends_runtime_schema' -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the full suite**

```bash
PYTHONPATH=src .venv/bin/pytest -q
```

Expected: zero failures; optional environment-dependent tests may remain skipped.

- [ ] **Step 3: Verify migration and source hygiene**

```bash
git diff --check
PYTHONPATH=src .venv/bin/alembic -c alembic.ini heads
git status --short
```

Expected: one head, `20260811_36`; no whitespace errors; only the three pre-existing untracked user files remain outside committed changes.

- [ ] **Step 4: Self-review against the approved design**

Verify every approved invariant, refusal path, template variable, admin range, and balance source has a direct automated assertion. Inspect `git diff main...HEAD` for unrelated edits and remove only changes introduced by this feature.

- [ ] **Step 5: Commit any test-only corrections**

If Task 6 required changes, commit only those exact files:

```bash
git add tests/core/test_red_packet.py tests/core/test_repository.py \
  tests/core/test_group_commands.py tests/core/test_service.py \
  tests/core/test_app.py tests/admin/test_app.py \
  tests/admin/test_package_data.py tests/deploy/test_artifacts.py
git commit -m "test: complete lucky red packet coverage"
```

If no files changed, do not create an empty commit.

- [ ] **Step 6: Report readiness and wait for deployment authority**

Report branch name, commit range, exact passed/skipped counts, migration head, and preserved untracked files. Do not merge, push, or deploy until the user explicitly authorizes those actions.
