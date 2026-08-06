# 躲猫猫双轮巡查 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让单人躲猫猫以固定的“第一轮 3 个地点、第二轮 2 个地点”方式完成巡查与结算。

**Architecture:** 在现有 `HideAndSeekGameRecord` 上记录当前巡查轮次，仓储层按轮抽取未巡查地点；命令层将每轮结果拆成独立群消息，最后一条包含结算文案。巡查数量不进入管理端设置，保持固定常量。

**Tech Stack:** Python 3.13、SQLAlchemy、FastAPI、pytest、Alembic。

## Global Constraints

- 每局固定提供 7 个候选地点。
- 第一轮巡查 3 个地点，第二轮仅在未命中时巡查另 2 个地点。
- 不新增运营端配置或改变既有经济、超时与每日次数规则。
- 扣除与奖励均按游戏开始时冻结的数值结算。

---

### Task 1: 保存并执行双轮巡查

**Files:**
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Create: `migrations/versions/20260806_16_hide_and_seek_two_round_patrol.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Consumes: `CoreRepository.choose_hide_and_seek(platform_id, scene_number, now)`。
- Produces: `HideAndSeekGameResult`，可提供每一轮的巡查编号和地点名称。

- [ ] **Step 1: Write the failing repository tests**

```python
assert result.patrol_rounds == ((1, 2, 3), (4, 5))
assert result.status == "won"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `.venv/bin/pytest tests/core/test_repository.py -k hide_and_seek -v`

- [ ] **Step 3: Add the minimum game-state field, migration, and repository selection logic**

```python
first_patrol = _sample_distinct(remaining_numbers, 3)
second_patrol = _sample_distinct(remaining_numbers, 2)
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `.venv/bin/pytest tests/core/test_repository.py -k hide_and_seek -v`

### Task 2: 输出每轮巡查消息

**Files:**
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Test: `tests/core/test_group_commands.py`

**Interfaces:**
- Consumes: `HideAndSeekGameResult.patrol_rounds`。
- Produces: 第一轮和第二轮分别发送的 `GroupReply`，最后一条携带结算文本。

- [ ] **Step 1: Write the failing command test**

```python
assert replies[0].text.startswith("【系统巡查·第一轮】")
assert replies[1].text.startswith("【系统巡查·第二轮】")
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `.venv/bin/pytest tests/core/test_group_commands.py -k hide_and_seek -v`

- [ ] **Step 3: Render one system reply per patrol round, then the final settlement**

```python
for round_number, patrols in enumerate(result.patrol_rounds, start=1):
    replies.append(GroupReply(f"【系统巡查·第{round_number}轮】巡查 {patrols}"))
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `.venv/bin/pytest tests/core/test_group_commands.py -k hide_and_seek -v`

### Task 3: 全量验证与部署

**Files:**
- Verify: `tests/`
- Verify: `migrations/versions/`

- [ ] **Step 1: Run full verification**

Run: `.venv/bin/pytest && git diff --check && .venv/bin/alembic -c alembic.ini heads`

- [ ] **Step 2: Commit and deploy**

Run: `git commit -m "feat: add two round hide and seek patrol"` followed by the established release deployment command.

- [ ] **Step 3: Verify production migration and services**

Run the deployment host's Alembic current command and `systemctl is-active dzmm-core dzmm-admin-web dzmm-browser-worker`.
