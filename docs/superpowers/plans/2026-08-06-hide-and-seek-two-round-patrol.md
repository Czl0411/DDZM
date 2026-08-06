# 躲猫猫双轮巡查 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让单人躲猫猫以固定的“第一轮 3 个地点、第二轮 2 个地点”方式完成巡查与结算。

**Architecture:** 仓储层一次抽取最多 5 个不重复地点，前 3 个是第一轮，后 2 个仅在第一轮未命中时纳入结果；命令层将两轮过程组装为一条群消息。巡查数量不进入管理端设置，保持固定常量。

**Tech Stack:** Python 3.13、SQLAlchemy、FastAPI、pytest、Alembic。

## Global Constraints

- 每局固定提供 7 个候选地点。
- 第一轮巡查 3 个地点，第二轮仅在未命中时巡查另 2 个地点。
- 不新增运营端配置或改变既有经济、超时与每日次数规则。
- 扣除与奖励均按游戏开始时冻结的数值结算。

---

### Task 1: 保存并执行双轮巡查

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Consumes: `CoreRepository.choose_hide_and_seek(platform_id, scene_number, now)`。
- Produces: `HideAndSeekGameResult`，可提供每一轮的巡查编号和地点名称。

- [ ] **Step 1: Write the failing repository tests**

```python
assert result.patrol_numbers == (1, 2, 3, 4, 5)
assert result.status == "won"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `.venv/bin/pytest tests/core/test_repository.py -k hide_and_seek -v`

- [ ] **Step 3: Add the minimum repository selection logic**

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
- Create: `migrations/versions/20260806_16_hide_and_seek_two_round_patrol.py`
- Test: `tests/core/test_group_commands.py`

**Interfaces:**
- Consumes: `HideAndSeekGameResult.patrol_numbers`。
- Produces: 一条包含第一轮、过渡文案、第二轮与结算文本的群回复。

- [ ] **Step 1: Write the failing command test**

```python
assert "【系统巡查·第一轮】" in reply
assert "奇怪，人躲哪里去了......." in reply
assert "【系统巡查·第二轮】" in reply
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `.venv/bin/pytest tests/core/test_group_commands.py -k hide_and_seek -v`

- [ ] **Step 3: Render both patrol rounds in the existing settlement reply**

```python
patrols = "【系统巡查·第一轮】巡查 ...\n奇怪，人躲哪里去了.......\n【系统巡查·第二轮】巡查 ..."
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
