# Hide and Seek Penalty Timing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Charge the configured hide-and-seek amount only when a player is found.

**Architecture:** Reuse the existing frozen `entry_fee` field as the penalty amount. Move the ledger debit from game creation to the `found` branch of choice resolution, leaving timeout cancellation to return only the daily play quota.

**Tech Stack:** Python 3.12, SQLAlchemy, pytest, existing admin static UI.

## Global Constraints

- Opening a game never changes a player's balance.
- A found player is debited the frozen amount even if settings later change.
- The existing `hide_and_seek_entry` ledger reason is replaced by `hide_and_seek_penalty`.
- Existing stored numeric settings retain their value and become the penalty amount.

---

### Task 1: Move the balance change to the found branch

**Files:**
- Modify: `tests/core/test_repository.py`
- Modify: `src/dzmm_bot/core/repository.py`

**Interfaces:**
- Consumes: `CoreRepository.start_hide_and_seek()` and `choose_hide_and_seek()`.
- Produces: a found result with a balance reduced by `entry_fee`; a start result with no ledger entry.

- [ ] **Step 1: Write failing tests**

```python
started = repository.start_hide_and_seek("u1", now)
assert repository.find_user("u1").balance == 0
found = repository.choose_hide_and_seek("u1", 1, now)
assert found.balance == -1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/core/test_repository.py -k hide_and_seek -v`

Expected: FAIL because start still debits the configured amount.

- [ ] **Step 3: Make the minimal repository change**

```python
# Do not debit in start_hide_and_seek.
if game.state == "found":
    self._apply_balance_change(user, -game.entry_fee, "hide_and_seek_penalty", now)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/core/test_repository.py -k hide_and_seek -v`

Expected: PASS.

### Task 2: Align player and admin copy

**Files:**
- Modify: `tests/core/test_group_commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`

**Interfaces:**
- Consumes: frozen `entry_fee` as `{惩罚金额}`.
- Produces: player start text that says no balance is charged; admin label “被发现扣除”.

- [ ] **Step 1: Write a failing group-command test**

```python
_receive(service, "start", "u1", "/开始摸鱼躲藏", now)
assert "开局不扣除" in _latest_reply(factory)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/core/test_group_commands.py -k hide_and_seek -v`

Expected: FAIL because the default start template still says it has deducted the amount.

- [ ] **Step 3: Update only default copy and labels**

```python
"开局不扣除；被系统找到时扣除 {入场费} {货币}。"
```

- [ ] **Step 4: Run focused tests and commit**

Run: `.venv/bin/pytest tests/core/test_group_commands.py tests/core/test_repository.py -k hide_and_seek -v`

Expected: PASS.

```bash
git add src tests
git commit -m "feat: charge hide and seek penalty on discovery"
```
