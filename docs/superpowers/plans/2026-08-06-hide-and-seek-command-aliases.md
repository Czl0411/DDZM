# Hide and Seek Command Aliases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the solo hide-and-seek player commands with concise commands and expose the frozen entry fee as a penalty template variable.

**Architecture:** Keep `/摸鱼躲猫猫` as the internal command-definition/template key so existing administrator template customizations remain intact. Only `GroupCommandHandler` changes its accepted player input; the found-result template receives `{惩罚金额}` from `HideAndSeekGameResult.entry_fee`.

**Tech Stack:** Python 3.12, pytest, existing reply-template registry.

## Global Constraints

- `/开始摸鱼躲藏` starts a game and `/躲 序号` selects the location.
- The legacy `/摸鱼躲猫猫 …` command text no longer triggers a game.
- `{惩罚金额}` is the frozen entry fee for that game, never the current configurable setting.
- Keep existing saved reply templates and the management command key `/摸鱼躲猫猫` intact.

---

### Task 1: Add the command and template regression tests

**Files:**
- Modify: `tests/core/test_group_commands.py`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_app.py`

**Interfaces:**
- Consumes: `GroupCommandHandler.handle(platform_id, content, received_at)`.
- Produces: tests that require new command text and a `{惩罚金额}` template variable.

- [ ] **Step 1: Write the failing tests**

```python
_receive(service, "start", "u1", "/开始摸鱼躲藏", now)
_receive(service, "choose", "u1", "/躲 7", now)
assert "扣除 1 摸鱼币" in _latest_reply(factory)
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `.venv/bin/pytest tests/core/test_group_commands.py -k hide_and_seek -v`

Expected: FAIL because the handler still only recognizes `/摸鱼躲猫猫 …`.

- [ ] **Step 3: Add the minimal command parsing and value propagation**

```python
if content == "/开始摸鱼躲藏":
    return self._start_hide_and_seek(platform_id, received_at)
if len(parts) == 2 and parts[0] == "/躲" and parts[1].isdigit():
    return self._choose_hide_and_seek(platform_id, int(parts[1]), received_at)
```

Pass `{"{惩罚金额}": result.entry_fee}` when rendering the `found` template.

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run: `.venv/bin/pytest tests/core/test_group_commands.py -k hide_and_seek -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dzmm_bot/core/commands.py src/dzmm_bot/core/reply_templates.py tests/core/test_group_commands.py tests/core/test_app.py
git commit -m "feat: simplify hide and seek commands"
```
