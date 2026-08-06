# 躲猫猫分轮消息 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让躲猫猫的第一轮和第二轮巡查作为按序独立的群消息发送。

**Architecture:** `GroupCommandHandler` 返回字符串列表，`CoreService` 将同一入站产生的所有回复按 `reply_index` 入队。出站表取消对入站 ID 的唯一限制，Worker 领取时按照创建时间和回复索引排序。躲猫猫新增首轮未命中和首轮发现模板场景。

**Tech Stack:** Python 3.13、SQLAlchemy、Alembic、pytest、PostgreSQL。

## Global Constraints

- 第一轮巡查 3 个地点，未命中时第二轮巡查另 2 个地点。
- 第一轮和第二轮必须作为两条独立出站消息发送。
- 同一入站消息保持幂等，不重复产生游戏结算或出站消息。
- 仅迁移未编辑的默认模板。

---

### Task 1: 支持同一入站的有序多回复

**Files:**
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/service.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Create: `migrations/versions/20260806_17_ordered_multi_replies.py`
- Test: `tests/core/test_service.py`

**Interfaces:**
- Consumes: `CommandHandler.handle(message) -> str | list[str] | None`。
- Produces: `OutboundRecord.reply_index`，并按同一入站消息的索引顺序排队。

- [ ] **Step 1: Write failing service tests**

```python
handler.handle = lambda _: ["第一条", "第二条"]
assert [record.text for record in outbounds] == ["第一条", "第二条"]
assert [record.reply_index for record in outbounds] == [0, 1]
```

- [ ] **Step 2: Run service tests and verify failure**

Run: `.venv/bin/pytest tests/core/test_service.py -k reply -v`

- [ ] **Step 3: Add reply list normalization, reply index, and migration**

```python
replies = [] if reply is None else [reply] if isinstance(reply, str) else reply
for reply_index, text in enumerate(replies):
    repository.enqueue_outbound(stored.id, text, reply_index)
```

- [ ] **Step 4: Run service tests and verify pass**

Run: `.venv/bin/pytest tests/core/test_service.py -k reply -v`

### Task 2: 拆分躲猫猫模板与消息

**Files:**
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Create: `migrations/versions/20260806_18_hide_and_seek_patrol_reply_templates.py`
- Test: `tests/core/test_group_commands.py`

**Interfaces:**
- Consumes: `HideAndSeekGameResult.patrol_numbers` 和 `patrol_scenes`。
- Produces: 首轮未命中时两条按顺序的回复，首轮命中时一条回复。

- [ ] **Step 1: Write failing group command tests**

```python
assert replies[0].startswith("【系统巡查·第一轮】")
assert "奇怪，人躲哪里去了......." in replies[0]
assert replies[1].startswith("【系统巡查·第二轮】")
```

- [ ] **Step 2: Run group command tests and verify failure**

Run: `.venv/bin/pytest tests/core/test_group_commands.py -k hide_and_seek -v`

- [ ] **Step 3: Add first-round template scenarios and return reply lists**

```python
return [first_round_reply, second_round_settlement_reply]
```

- [ ] **Step 4: Run group command tests and verify pass**

Run: `.venv/bin/pytest tests/core/test_group_commands.py -k hide_and_seek -v`

### Task 3: 验证与部署

**Files:**
- Verify: `tests/`
- Verify: `migrations/versions/`

- [ ] **Step 1: Run full verification**

Run: `.venv/bin/pytest && git diff --check && .venv/bin/alembic -c alembic.ini heads`

- [ ] **Step 2: Commit and deploy**

Run: `git commit -m "feat: send hide and seek patrol rounds separately"` followed by the established deployment command.

- [ ] **Step 3: Verify production**

Run the production Alembic current command and check the three systemd services are active.
