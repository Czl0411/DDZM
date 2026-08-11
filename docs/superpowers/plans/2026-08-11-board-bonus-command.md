# Board Bonus Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an atomic, audited `/发奖金` command that only core board members can use for one employee or every employee.

**Architecture:** Put authorization, exact target resolution, row locking, balance changes, and audit creation in one repository transaction. Keep command parsing and editable public responses in `GroupCommandHandler`, while relying on existing inbound idempotency to prevent duplicate grants.

**Tech Stack:** Python 3.12+, SQLAlchemy, FastAPI command pipeline, pytest, existing reply-template and command-definition tables.

## Global Constraints

- Only ranks with `is_board=true` may grant bonuses.
- The system funds every bonus; the issuer balance is never deducted.
- Supported forms are `/发奖金 员工名 金额` and `/发奖金 全部 金额`.
- Amount is an ASCII integer from `1` through `99999`.
- Exact target `全部` selects every employee before any name lookup.
- Single-name lookup rejects zero matches and more than one match without changing balances.
- Every recipient gets one `board_bonus` balance transaction and every successful command gets one `board_bonus` audit event.
- All-recipient grants are atomic and include the issuer and all other board members.
- The command has no daily count or amount cap.

---

### Task 1: Implement the atomic board bonus transaction

**Files:**
- Modify: `tests/core/test_repository.py`
- Modify: `src/dzmm_bot/core/repository.py`

**Interfaces:**
- Produces: `BoardBonusResult(status: str, issuer_display_name: str | None = None, recipient_display_name: str | None = None, amount: int = 0, recipient_count: int = 0)`.
- Produces: `CoreRepository.grant_board_bonus(issuer_platform_id: str, target: str, amount: int, occurred_at: datetime) -> BoardBonusResult`.

- [ ] **Step 1: Write failing repository tests**

Add tests that assign the seeded `is_board=true` rank to an issuer and verify:

```python
single = repository.grant_board_bonus("board", "苏白", 10, now)
assert single.status == "granted"
assert repository.find_user("recipient").balance == 10
assert [(row.amount, row.source) for row in transactions] == [(10, "board_bonus")]
assert audit.event_type == "board_bonus"
assert audit.actor == "board"
assert audit.payload["scope"] == "single"
```

For an all-recipient grant:

```python
everyone = repository.grant_board_bonus("board", "全部", 7, now)
assert everyone.recipient_count == 3
assert [user.balance for user in repository.list_users()] == [7, 7, 7]
assert len(transactions) == 3
assert len(audits) == 1
assert audits[0].payload["total_amount"] == 21
```

Also cover a non-board rank with `has_group_management=true`, missing target, duplicate exact names, and invalid amounts; each case must leave balances, transactions, and audits unchanged.

Inject a failure on the second `_apply_balance_change` call during an all-recipient grant and assert that the first recipient's balance and transaction are rolled back.

- [ ] **Step 2: Run the repository tests and verify RED**

Run: `PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_repository.py -k 'board_bonus' -q`

Expected: FAIL because `grant_board_bonus` and `BoardBonusResult` do not exist.

- [ ] **Step 3: Add the result type and repository method**

Implement one transaction that loads the issuer and rank, validates `is_board`, validates `1 <= amount <= 99999`, resolves recipients with deterministic `UserRecord.id` ordering and `with_for_update()`, calls `_apply_balance_change(user, amount, "board_bonus", occurred_at)` for each recipient, and inserts:

```python
payload = {
    "issuer_display_name": issuer.display_name,
    "scope": scope,
    "amount": amount,
    "recipient_count": len(recipients),
    "total_amount": amount * len(recipients),
}
if scope == "single":
    payload.update({
        "recipient_platform_id": recipients[0].platform_id,
        "recipient_display_name": recipients[0].display_name,
    })
session.add(AuditEventRecord(
    event_type="board_bonus",
    actor=issuer.platform_id,
    payload=payload,
))
```

Return statuses `granted`, `not_joined`, `not_authorized`, `invalid_amount`, `target_not_found`, or `ambiguous_target` without partial writes.

- [ ] **Step 4: Run focused and balance tests**

Run: `PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_repository.py -k 'board_bonus or balance' -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add tests/core/test_repository.py src/dzmm_bot/core/repository.py
git commit -m "feat: add audited board bonus transaction"
```

### Task 2: Add `/发奖金` parsing, permission responses, templates, and help

**Files:**
- Modify: `tests/core/test_group_commands.py`
- Modify: `tests/core/test_repository.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`

**Interfaces:**
- Consumes: `CoreRepository.grant_board_bonus(issuer_platform_id: str, target: str, amount: int, occurred_at: datetime) -> BoardBonusResult`.
- Produces: group command `/发奖金 员工名 金额` and `/发奖金 全部 金额`.

- [ ] **Step 1: Write failing command and metadata tests**

Cover these command results through `CoreService.receive_inbound()`:

```python
assert reply == "【奖金】董事向苏白发放 10 摸鱼币。"
assert all_reply == "【奖金】董事向全体 3 名员工每人发放 7 摸鱼币。"
assert unauthorized_reply == "只有核心董事会成员可以发放奖金。"
assert duplicate_reply == "存在多名同名员工，请使用唯一员工名后重试。"
```

Verify `/发奖金 全部 7` still grants to all when one employee's display name is `全部`. Verify duplicate delivery of the same `platform_message_id` changes balances once. Verify malformed, zero, negative, decimal, non-ASCII digit, too-large, and missing amounts return usage or amount errors without writes.

Verify command metadata and templates:

```python
assert commands["/发奖金"] == "/发奖金 员工名 金额；/发奖金 全部 金额"
assert {template.scenario for template in repository.list_reply_templates("/发奖金")} == {
    "usage", "not_joined", "not_authorized", "invalid_amount",
    "target_not_found", "ambiguous_target", "single_granted", "all_granted",
}
```

- [ ] **Step 2: Run command tests and verify RED**

Run: `PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_group_commands.py tests/core/test_repository.py -k 'board_bonus or grant_bonus' -q`

Expected: FAIL because `/发奖金` is not registered or routed.

- [ ] **Step 3: Register and route the command**

Add `/发奖金` to `_COMMANDS` and `_COMMAND_DEFINITIONS`. Parse with `content.split()` so the final token is the amount and the joined middle tokens are the exact target. Require the amount token to satisfy `token.isascii() and token.isdigit()` before converting it.

Map repository statuses to reply scenarios and render successful replies with `{发放者}`, `{收款人}`, `{金额}`, `{人数}`, and the existing `{货币}` context.

- [ ] **Step 4: Add editable templates and help entry**

Add eight `TemplateDefinition` records for the scenarios listed in Step 1. Add `/发奖金` to the basic help category with both supported forms and the core-board-only description.

- [ ] **Step 5: Run focused command, template, and idempotency tests**

Run: `PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_group_commands.py tests/core/test_repository.py -k 'board_bonus or grant_bonus or command_definitions or reply_template' -q`

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add tests/core/test_group_commands.py tests/core/test_repository.py src/dzmm_bot/core/commands.py src/dzmm_bot/core/repository.py src/dzmm_bot/core/reply_templates.py
git commit -m "feat: add core board bonus command"
```

### Task 3: Verify and prepare both pending changes for deployment

**Files:**
- Verify only; no additional production files.

**Interfaces:**
- Produces: one tested branch containing the board force-end fix and board bonus command.

- [ ] **Step 1: Run focused core verification**

Run: `git diff --check && PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest tests/core/test_app.py tests/core/test_group_commands.py tests/core/test_repository.py -q`

Expected: PASS.

- [ ] **Step 2: Run the complete suite**

Run: `PYTHONPATH=src /Users/zhijian/Desktop/DDZM/.venv/bin/pytest -q`

Expected: all mandatory tests pass; only documented optional tests may skip.

- [ ] **Step 3: Review the exact diff**

Compare `main...HEAD`, verify no unrelated files changed, and verify the user-owned root `.env`, `.DS_Store`, and `docs/BOT_MESSAGE_TRANSPORT_HANDOFF.md` remain untouched.

- [ ] **Step 4: Integrate and deploy only after the branch completion decision**

Use the finishing-development-branch flow. If local merge is selected, fast-forward `main`, rerun the complete suite on merged `main`, push normally without force, deploy a Git archive through `deploy/scripts/deploy.sh`, and verify both health endpoints, all five services, Browser Worker listening state, and post-ready logs.
