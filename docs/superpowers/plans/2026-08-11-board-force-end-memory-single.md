# Board Force-End Memory Single Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow board members and authenticated administrators to force-end a stuck single-player memory assessment without granting the ability to ordinary nonparticipants.

**Architecture:** Extend the existing exact-identity `CoreRepository.force_end_gameplay()` path to support `memory_single`. Route board members' `/结束游戏` through that same path before participant-specific lifecycle handling, so both management surfaces share cancellation and notification semantics.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, pytest, PostgreSQL/SQLite test fixtures.

## Global Constraints

- Only ranks with `is_board=true` gain group-chat force-end authority.
- `has_group_management=true` alone does not grant force-end authority.
- Ordinary player lifecycle behavior remains unchanged.
- Forced endings do not award coins, apply penalties, or write AI activity facts.
- The exact active game type and ID must still match.
- A successful forced ending emits exactly one existing `admin_forced` group notification.

---

### Task 1: Add single-player memory assessment to exact force-end

**Files:**
- Modify: `tests/core/test_app.py`
- Modify: `src/dzmm_bot/core/repository.py`

**Interfaces:**
- Consumes: `CoreRepository.force_end_gameplay(game_type: str, game_id: UUID, now: datetime) -> bool`
- Produces: support for `game_type == "memory_single"` through the existing internal API.

- [ ] **Step 1: Write the failing API regression test**

Create a user, start a single memory assessment, call `/internal/gameplay/memory_single/{game_id}/force-end`, and assert:

```python
assert response.json() == {"accepted": True}
assert repository.active_gameplay_summary("memory-single-player", NOW).game_type is None
assert game.state == "cancelled"
assert participant.state == "cancelled"
assert outbounds == ["【记忆考核】管理员已强制结束当前游戏。"]
assert activity_events == []
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `.venv/bin/pytest tests/core/test_app.py::test_admin_can_force_end_single_memory_assessment -q`

Expected: FAIL because `memory_single` is not present in the force-end game type mapping.

- [ ] **Step 3: Implement the minimal repository change**

Add `"memory_single": "记忆考核"` to the force-end mapping. Handle both memory types in the memory branch while requiring the requested type to match `game.mode`:

```python
elif game_type in {"memory_duel", "memory_single"}:
    expected_mode = "duel" if game_type == "memory_duel" else "single"
    game = session.get(MemoryAssessmentGameRecord, game_id, with_for_update=True)
    if game is not None and game.active_key == "global" and game.mode == expected_mode:
        game.state = "cancelled"
        game.active_key = None
        game.signup_deadline = None
        game.answer_deadline = None
        game.finished_at = now
        for participant in session.scalars(
            select(MemoryAssessmentParticipantRecord)
            .where(MemoryAssessmentParticipantRecord.game_id == game.id)
            .with_for_update()
        ):
            participant.state = "cancelled"
        ended = True
```

- [ ] **Step 4: Run the focused API test and nearby force-end tests**

Run: `.venv/bin/pytest tests/core/test_app.py -k 'force_end or gameplay_current' -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add tests/core/test_app.py src/dzmm_bot/core/repository.py
git commit -m "fix: force end single memory assessments"
```

### Task 2: Route board members' group command to force-end

**Files:**
- Modify: `tests/core/test_group_commands.py`
- Modify: `src/dzmm_bot/core/commands.py`

**Interfaces:**
- Consumes: `CoreRepository.get_user_profile(platform_id)` and `profile.rank.is_board`.
- Consumes: `CoreRepository.force_end_gameplay(summary.game_type, summary.game_id, received_at)`.
- Produces: board-only group force-end behavior for `/结束游戏`.

- [ ] **Step 1: Write failing command tests**

Add one test that promotes a nonparticipant to the seeded board rank, starts another user's single memory assessment, sends `/结束游戏`, and asserts:

```python
assert repository.active_gameplay_summary("board", now).game_type is None
assert _latest_reply(factory) == "【记忆考核】管理员已强制结束当前游戏。"
```

Add a companion test for an ordinary nonparticipant:

```python
assert _latest_reply(factory) == "当前没有你可以结束的游戏。"
assert repository.active_gameplay_summary("ordinary", now).game_type == "memory_single"
```

- [ ] **Step 2: Run the focused command tests and verify RED**

Run: `.venv/bin/pytest tests/core/test_group_commands.py -k 'board_force_end or nonparticipant_cannot_force_end' -q`

Expected: the board test FAILS because `/结束游戏` currently follows nonparticipant player routing.

- [ ] **Step 3: Implement board-first routing**

Before participant-specific `/结束游戏` routing:

```python
profile = self._repository.get_user_profile(message.sender_platform_id)
if (
    profile is not None
    and profile.rank.is_board
    and summary.game_type not in {None, "conflict"}
    and summary.game_id is not None
):
    if self._repository.force_end_gameplay(summary.game_type, summary.game_id, received_at):
        return None
```

Returning `None` is required because the repository already queues the single administrator notification.

- [ ] **Step 4: Run focused routing and service tests**

Run: `.venv/bin/pytest tests/core/test_group_commands.py -k 'end_game or force_end or current_game' -q`

Expected: PASS, including existing participant behavior.

- [ ] **Step 5: Commit Task 2**

```bash
git add tests/core/test_group_commands.py src/dzmm_bot/core/commands.py
git commit -m "fix: let board members force end active games"
```

### Task 3: Verify, integrate, deploy, and release the current game

**Files:**
- Verify only; no additional production files.

**Interfaces:**
- Produces: tested branch, merged `main`, production migration unchanged at `20260811_35`, and healthy runtime services.

- [ ] **Step 1: Run syntax and focused verification**

Run: `git diff --check && .venv/bin/pytest tests/core/test_app.py tests/core/test_group_commands.py -q`

Expected: PASS.

- [ ] **Step 2: Run the complete suite**

Run: `.venv/bin/pytest -q`

Expected: all mandatory tests pass; only documented optional tests may skip.

- [ ] **Step 3: Merge and push without overwriting user files**

Fast-forward `main` from `codex/board-force-end-memory-single`, preserve untracked `.env`, `.DS_Store`, and `docs/BOT_MESSAGE_TRANSPORT_HANDOFF.md`, then push `main` normally without force.

- [ ] **Step 4: Deploy the Git archive**

Use `git archive --format=tar HEAD` and the existing `deploy/scripts/deploy.sh` workflow so untracked `.env` is not uploaded and `/etc/dzmm/dzmm.env` remains unchanged.

- [ ] **Step 5: Verify production and clear the stuck game**

Verify both health endpoints, all five systemd units, migration head, Browser Worker `ready/listening=true`, no post-ready errors, and an exact `memory_single` force-end. Confirm `/internal/gameplay/current` no longer reports game ID `e80ef7e5-2ebe-45f6-bfb2-c2b8ff639ffc`.
