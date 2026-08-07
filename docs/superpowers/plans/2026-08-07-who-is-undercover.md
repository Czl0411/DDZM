# 谁是卧底 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a group-scoped Who Is the Undercover game with private card dealing, persistent game state, timed voting, continuous rounds, role configuration, and an admin configuration page.

**Architecture:** Persist a group game session separately from immutable per-round game snapshots. The core owns all eligibility, role allocation, state transitions, vote settlement, and timers; the browser worker discovers pre-existing one-on-one rooms and sends typed outbound messages to either the group or a direct room. The admin web app only reads and updates game rules through the existing core API/versioning pattern.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy/Alembic, PostgreSQL/SQLite test suite, Socket.IO browser worker, vanilla JS admin UI, pytest.

## Global Constraints

- All persisted timestamps and date logic use Beijing time.
- Reuse the seeded `undercover_word_sets`; no runtime AI generation and no economy rewards, fees, penalties, or daily limits.
- Initial lobby command is `/谁是卧底 N`, where `N` is an integer in `[4, 8]`.
- A player must have an already discovered one-on-one chat room with the bot before creating or joining.
- Player votes are `/投票 编号`, exactly once per player per vote round, and cannot be changed.
- Random events and all multiplayer games are mutually exclusive with Who Is the Undercover. Existing random-event block copy and command allowlists remain authoritative.
- A completed session remains available for `/继续` for 20 minutes; any active participant can issue `/结束游戏` to close it immediately.
- Do not stage the local `.env` file or unrelated untracked files.

---

## File Structure

- `src/dzmm_bot/core/schema.py`: new direct-chat mapping and undercover persistence records.
- `migrations/versions/20260807_26_undercover_game.py`: schema and default settings/role rules.
- `src/dzmm_bot/core/repository.py`: settings, eligibility, session/game state machine, votes, settlement, expiration, and outbound delivery callbacks.
- `src/dzmm_bot/core/commands.py`: parse and render `/谁是卧底`, `/加入`, `/开始投票`, `/投票`, `/继续`, `/退出谁是卧底`, `/结束游戏`.
- `src/dzmm_bot/core/reply_templates.py`: command definitions and default copy for all group-facing outcomes.
- `src/dzmm_bot/core/service.py`: invoke scheduled undercover expiration/vote jobs and dispatch direct/public reply destinations.
- `src/dzmm_bot/core/api_models.py`, `src/dzmm_bot/core/app.py`: settings and current-session internal APIs, plus direct-chat discovery sync and outbound delivery callbacks.
- `src/dzmm_bot/browser/aikda_socket.py`: list existing one-on-one rooms, map them to non-bot senders, and send text to a supplied chatroom id.
- `src/dzmm_bot/browser/core_client.py`, `src/dzmm_bot/browser/worker.py`: sync discovered direct rooms and route claimed outbound records by destination.
- `src/dzmm_bot/admin/core_client.py`, `src/dzmm_bot/admin/repository.py`, `src/dzmm_bot/admin/app.py`: proxy settings/current state with existing auth, revision and idempotency semantics.
- `src/dzmm_bot/admin/templates/index.html`, `src/dzmm_bot/admin/static/admin.js`, `src/dzmm_bot/admin/static/admin.css`: add the Who Is the Undercover menu, settings modal, role-rule editor and current-session summary.
- `rule.md`: record the approved multiplayer lock, private-deal, vote and continuation rules.
- `tests/core/test_repository.py`, `tests/core/test_group_commands.py`, `tests/core/test_app.py`: persistence, command and internal API coverage.
- `tests/browser/test_aikda_socket.py`, `tests/browser/test_core_client.py`, `tests/browser/test_worker.py`: direct-room discovery, targeted sends and delivery lifecycle.
- `tests/admin/test_app.py`: admin proxy/UI contract tests.

### Task 1: Persist rules, direct-room mappings, sessions, games and votes

**Files:**
- Modify: `src/dzmm_bot/core/schema.py`
- Create: `migrations/versions/20260807_26_undercover_game.py`
- Modify: `tests/core/test_repository.py`

**Interfaces:**
- Produces `UndercoverSettingsRecord`, `UndercoverRoleRuleRecord`, `DirectChatRecord`, `UndercoverSessionRecord`, `UndercoverSessionMemberRecord`, `UndercoverGameRecord`, `UndercoverGamePlayerRecord`, and `UndercoverVoteRecord`.
- Produces migration revision `20260807_26` with `down_revision = "20260807_25"`.
- `UndercoverSessionRecord.active_key` has a partial unique index while not null, matching the existing memory-assessment active-game pattern.
- The migration also adds nullable `destination_chatroom_id` and `delivery_kind` fields to `outbound_messages`; existing rows remain group messages.

- [ ] **Step 1: Write migration/schema tests first**

Add tests that assert every new table exists after the migration, one active session is permitted, role rules are unique by player count, direct mappings are unique by platform user and room id, and votes are unique by `(game_id, round_number, voter_user_id)`.

```python
def test_undercover_migration_creates_game_tables(migrated_postgres_url):
    with create_engine(migrated_postgres_url).connect() as connection:
        names = inspect(connection).get_table_names()
    assert {"undercover_settings", "undercover_role_rules", "direct_chats",
            "undercover_sessions", "undercover_session_members", "undercover_games",
            "undercover_game_players", "undercover_votes"} <= set(names)
```

- [ ] **Step 2: Run the new migration/schema tests and verify they fail**

Run: `pytest tests/core/test_repository.py -k undercover_migration -v`

Expected: failure because the revision and record classes do not exist.

- [ ] **Step 3: Add the record classes and migration**

Create only these durable fields:

```python
class UndercoverSettingsRecord(Base):
    __tablename__ = "undercover_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    vote_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    whiteboard_win_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

class UndercoverRoleRuleRecord(Base):
    __tablename__ = "undercover_role_rules"
    player_count: Mapped[int] = mapped_column(Integer, primary_key=True)
    civilian_count: Mapped[int] = mapped_column(Integer, nullable=False)
    undercover_count: Mapped[int] = mapped_column(Integer, nullable=False)
    whiteboard_count: Mapped[int] = mapped_column(Integer, nullable=False)
```

The migration seeds the approved default rows `(4,3,1,0)`, `(5,3,1,1)`, `(6,4,1,1)`, `(7,4,2,1)`, `(8,5,2,1)`. Store frozen civilian and undercover word values in `undercover_games`, game role/state and stable seat numbers in `undercover_game_players`, and `vote_deadline` plus `await_continue_deadline` in the session/game records as applicable.

- [ ] **Step 4: Run the migration/schema tests and static checks**

Run: `pytest tests/core/test_repository.py -k undercover_migration -v && git diff --check`

Expected: PASS with the seeded five role rules and no whitespace errors.

- [ ] **Step 5: Commit the persistence foundation**

```bash
git add src/dzmm_bot/core/schema.py migrations/versions/20260807_26_undercover_game.py tests/core/test_repository.py
git commit -m "feat: persist who is undercover games"
```

### Task 2: Implement the repository state machine and deterministic settlement

**Files:**
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `tests/core/test_repository.py`

**Interfaces:**
- Produces `UndercoverSettings`, `UndercoverRoleRule`, `UndercoverGameResult`, and `UndercoverSessionSummary` dataclasses.
- Produces repository methods: `get_undercover_settings`, `set_undercover_settings`, `list_undercover_role_rules`, `upsert_direct_chats`, `start_undercover_signup`, `join_undercover`, `start_undercover_vote`, `cast_undercover_vote`, `leave_undercover`, `continue_undercover`, `end_undercover`, `run_undercover_jobs`, and `record_undercover_card_delivery`.
- Consumes user/word-set records and the active random-event/memory-duel state check.

- [ ] **Step 1: Write repository tests for the full state progression**

Add independent tests for: invalid lobby sizes; absent direct-chat eligibility; automatic start at target capacity; role allocation exactly matching a frozen rule; vote duplicate rejection; unique elimination; tied vote state; whiteboard/civilian/undercover winner branches; exit re-evaluation; queued joins; continuation; 20-minute close; and manual end.

```python
def test_undercover_tied_vote_requires_a_new_vote_round(repository, now):
    game = _started_undercover_game(repository, now, player_count=4)
    assert repository.start_undercover_vote(game.id, game.player_ids[0], now).status == "voting"
    assert repository.cast_undercover_vote(game.id, game.player_ids[0], 2, now).status == "recorded"
    assert repository.cast_undercover_vote(game.id, game.player_ids[1], 3, now).status == "recorded"
    assert repository.cast_undercover_vote(game.id, game.player_ids[2], 2, now).status == "recorded"
    assert repository.cast_undercover_vote(game.id, game.player_ids[3], 3, now).status == "tied"
```

- [ ] **Step 2: Run the focused repository tests and verify they fail**

Run: `pytest tests/core/test_repository.py -k undercover -v`

Expected: failures because the result models and transition methods do not exist.

- [ ] **Step 3: Implement narrow transactional transitions**

Use `with self.transaction()` plus row locks for every mutating transition. Use states `signup`, `dealing`, `speaking`, `voting`, `tie_break`, `settled`, `awaiting_continue`, and `closed`. Allocate seats once per round and retain original session members after settlement unless they explicitly leave. When a continuation has more than eight candidates, include original unexited members first, then queued members by `queued_at`.

Expose `active_multiplayer_game_state()` from the repository. It returns the active Who Is the Undercover state, active memory-assessment duel state, or active random-event state. Call it before creating a Who Is the Undercover session, before starting/joining a memory-assessment duel, and before moving a scheduled random event into signup, so the mutual exclusion is enforced in both directions rather than only in command rendering.

Implement settlement with this single ordered predicate:

```python
if living_whiteboards and living_total == settings.whiteboard_win_remaining:
    winner = "whiteboard"
elif not living_undercover and not living_whiteboards:
    winner = "civilian"
elif len(living_undercover) >= len(living_civilians):
    winner = "undercover"
else:
    winner = None
```

Do not apply balance transactions in any branch. `run_undercover_jobs(now)` closes expired voting rounds and expires only `awaiting_continue` sessions after 20 minutes.

- [ ] **Step 4: Run focused repository tests**

Run: `pytest tests/core/test_repository.py -k undercover -v`

Expected: PASS, including duplicate-create and duplicate-vote concurrency protection.

- [ ] **Step 5: Commit the state machine**

```bash
git add src/dzmm_bot/core/repository.py tests/core/test_repository.py
git commit -m "feat: run who is undercover sessions"
```

### Task 3: Add direct-chat discovery and destination-aware outbound delivery

**Files:**
- Modify: `src/dzmm_bot/runtime/contracts.py`
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/browser/aikda_socket.py`
- Modify: `src/dzmm_bot/browser/core_client.py`
- Modify: `src/dzmm_bot/browser/worker.py`
- Modify: `tests/browser/test_aikda_socket.py`
- Modify: `tests/browser/test_core_client.py`
- Modify: `tests/browser/test_worker.py`
- Modify: `tests/core/test_app.py`

**Interfaces:**
- `DirectChatRoom(platform_user_id: str, chatroom_id: str)` represents one robot-accessible direct room.
- `AikdaSocketGateway.discover_direct_chats() -> list[DirectChatRoom]` and `send_to(chatroom_id: str, text: str) -> str`.
- Claimed outbound messages expose `destination_chatroom_id: str | None`; `None` remains the configured group room.
- Core API `POST /internal/direct-chats/sync` upserts mappings and delivery endpoints report direct-card success/failure by outbound id.

- [ ] **Step 1: Write failing browser/core transport tests**

Use fake request/socket objects to prove that `chat.listAll` only selects `chatType == "one_on_one"`, `chatroom.getMessages` identifies the non-bot `sent_by`, `message:send` receives the supplied direct room id, and a worker sends an outbound claim to that room instead of the group.

```python
def test_gateway_discovers_direct_room_from_non_bot_history(fake_gateway):
    assert fake_gateway.discover_direct_chats() == [
        DirectChatRoom(platform_user_id="employee-1", chatroom_id="direct-1")
    ]
```

- [ ] **Step 2: Run direct-chat tests and verify they fail**

Run: `pytest tests/browser/test_aikda_socket.py tests/browser/test_worker.py -k "direct or destination" -v`

Expected: failure because outbound claims have no destination and the gateway only handles the group room.

- [ ] **Step 3: Implement discovery, routing and card-delivery callbacks**

Add nullable `destination_chatroom_id` to outbound records. Keep all existing group replies unchanged when it is null. The worker periodically calls `discover_direct_chats`, sends mappings to the core, and routes each claim through `gateway.send_to(claim.destination_chatroom_id, claim.text)` when populated.

For card delivery, persist the outbound id on the game player. A successful direct-card confirmation marks that player delivered; after the final delivery, atomically change `dealing` to `speaking` and enqueue the public opening. On a failed direct-card send, atomically restore the session to `signup`, discard the pending game snapshot, and enqueue one group-facing delivery-failed notice. Never read, persist, or reply to private message content for this feature.

- [ ] **Step 4: Run the targeted transport and core API tests**

Run: `pytest tests/browser/test_aikda_socket.py tests/browser/test_core_client.py tests/browser/test_worker.py tests/core/test_app.py -k "direct or destination or delivery" -v`

Expected: PASS; group sends retain their existing destination and direct card sends never appear in the group queue.

- [ ] **Step 5: Commit direct-card transport**

```bash
git add src/dzmm_bot/runtime/contracts.py src/dzmm_bot/core/schema.py src/dzmm_bot/core/repository.py src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/browser/aikda_socket.py src/dzmm_bot/browser/core_client.py src/dzmm_bot/browser/worker.py tests/browser tests/core/test_app.py
git commit -m "feat: deliver undercover cards by direct chat"
```

### Task 4: Route group commands and render configurable group replies

**Files:**
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/service.py`
- Modify: `src/dzmm_bot/core/reply_templates.py`
- Modify: `tests/core/test_group_commands.py`
- Modify: `tests/core/test_service.py`

**Interfaces:**
- Add commands `/谁是卧底`, `/开始投票`, `/投票`, `/结束游戏` to `_COMMANDS`.
- Add `CommandReply(destination_platform_id: str | None = None, delivery_kind: str = "group")` without changing existing callers.
- `GroupCommandHandler` emits direct card replies only from an auto-start/continue result and group copy for all visible state transitions.

- [ ] **Step 1: Write command tests for happy path and all public rejects**

Cover `/谁是卧底 4`, invalid sizes, no direct room, `/加入` while signup and while active, `/开始投票`, invalid/dead/duplicate votes, tie handling, `/继续`, `/退出谁是卧底`, `/结束游戏`, existing random-event blocked copy, and collision with a memory-assessment duel.

```python
def test_undercover_join_queues_during_active_game(handler, repository, now):
    _start_undercover_game(repository, now, count=4)
    assert "下一局" in handler.handle(_message("u5", "/加入", now))
    assert repository.undercover_session_summary().queued_count == 1
```

- [ ] **Step 2: Run the group-command tests and verify they fail**

Run: `pytest tests/core/test_group_commands.py -k undercover -v`

Expected: failure because commands and templates are absent.

- [ ] **Step 3: Add minimal command routing and template definitions**

Route no-argument `/加入` to undercover only when an undercover session is active; keep `/加入 身份` routed to a random event. Route `/继续` to undercover only when an undercover session is `awaiting_continue`; otherwise preserve memory-assessment behavior. Every non-silent outcome uses a named template scenario and only the approved variables `{人数}`, `{当前人数}`, `{玩家列表}`, `{投票秒数}`, `{淘汰玩家}`, `{身份}`, `{胜利阵营}`.

Call `repository.run_undercover_jobs(now)` from `CoreRepository.run_daily_jobs(now)`, which is already invoked every browser-worker loop through `/internal/daily-jobs/run`, so 2-minute vote expiry and 20-minute waiting expiry emit system outbound messages without an inbound command.

- [ ] **Step 4: Run group command/service tests**

Run: `pytest tests/core/test_group_commands.py tests/core/test_service.py -k "undercover or random_event" -v`

Expected: PASS; no random-event block is bypassed and existing commands retain their current behavior outside an undercover session.

- [ ] **Step 5: Commit command integration**

```bash
git add src/dzmm_bot/core/commands.py src/dzmm_bot/core/service.py src/dzmm_bot/core/reply_templates.py tests/core/test_group_commands.py tests/core/test_service.py
git commit -m "feat: add who is undercover group commands"
```

### Task 5: Expose rule configuration and current session over the internal/admin APIs

**Files:**
- Modify: `src/dzmm_bot/core/api_models.py`
- Modify: `src/dzmm_bot/core/app.py`
- Modify: `src/dzmm_bot/admin/core_client.py`
- Modify: `src/dzmm_bot/admin/repository.py`
- Modify: `src/dzmm_bot/admin/app.py`
- Modify: `tests/core/test_app.py`
- Modify: `tests/admin/test_app.py`

**Interfaces:**
- Core APIs: `GET/PUT /internal/game/undercover/settings` and `GET /internal/game/undercover/session`.
- Admin APIs: `GET/PUT /api/game/undercover/settings` and `GET /api/game/undercover/session`.
- Request model includes `enabled`, `vote_seconds`, `whiteboard_win_remaining`, and exactly five player-count role rules.

- [ ] **Step 1: Write core/admin API tests**

Validate optimistic revision/idempotency behavior matches memory-assessment settings; reject values outside player counts 4–8, role totals that do not equal the count, vote duration below one second, and whiteboard thresholds below two. Verify current-session output does not expose private words or identities before settlement.

```python
def test_undercover_settings_reject_invalid_role_total(client, headers):
    response = client.put("/internal/game/undercover/settings", headers=headers, json={
        "enabled": True, "vote_seconds": 120, "whiteboard_win_remaining": 3,
        "roles": [{"player_count": 4, "civilian_count": 3, "undercover_count": 2, "whiteboard_count": 0}],
    })
    assert response.status_code == 422
```

- [ ] **Step 2: Run the focused API tests and verify they fail**

Run: `pytest tests/core/test_app.py tests/admin/test_app.py -k undercover -v`

Expected: failure because the API contracts and admin proxy methods are absent.

- [ ] **Step 3: Implement API models, routes and proxies**

Use the existing settings revision helpers. The current-session response contains only state, target/actual player counts, vote deadline, round number, and public roster/queue counts. Private words, pending direct-room ids and role cards are never returned to the admin browser while a game is live.

- [ ] **Step 4: Run focused API tests**

Run: `pytest tests/core/test_app.py tests/admin/test_app.py -k undercover -v`

Expected: PASS, including stale revision and idempotent replay paths.

- [ ] **Step 5: Commit API contracts**

```bash
git add src/dzmm_bot/core/api_models.py src/dzmm_bot/core/app.py src/dzmm_bot/admin/core_client.py src/dzmm_bot/admin/repository.py src/dzmm_bot/admin/app.py tests/core/test_app.py tests/admin/test_app.py
git commit -m "feat: configure who is undercover rules"
```

### Task 6: Build the administrative configuration surface

**Files:**
- Modify: `src/dzmm_bot/admin/templates/index.html`
- Modify: `src/dzmm_bot/admin/static/admin.js`
- Modify: `src/dzmm_bot/admin/static/admin.css`
- Modify: `tests/admin/test_app.py`

**Interfaces:**
- New navigation `data-view="undercover"`.
- `loadUndercover()`, `openUndercoverSettingsModal()`, `saveUndercoverSettings()` and `renderUndercoverSession()` in the existing admin script.

- [ ] **Step 1: Write UI contract tests first**

Assert the navigation exists, the main view shows a concise current-session card, settings open in a modal rather than rendering inline, every row has counts for 4–8 players, and save uses the configured revision/idempotency headers.

```python
def test_admin_exposes_undercover_configuration_modal(client):
    page = client.get("/", headers=_admin_headers()).text
    assert 'data-view="undercover"' in page
    assert 'id="undercover-settings-modal"' in page
    assert "saveUndercoverSettings" in page
```

- [ ] **Step 2: Run UI contract tests and verify they fail**

Run: `pytest tests/admin/test_app.py -k undercover -v`

Expected: failure because the menu/modal/client script do not exist.

- [ ] **Step 3: Implement the smallest readable UI**

Add one sidebar item and one summary card with enabled state, vote duration, whiteboard threshold, active session state and participant counts. Open a scrollable modal for editing the five role rows plus the three scalar settings. Reuse existing disabled/saving button, success/error toast, revision conflict, pagination and modal scroll patterns; do not add a separate page framework.

- [ ] **Step 4: Run UI tests and manually inspect the rendered route**

Run: `pytest tests/admin/test_app.py -k undercover -v`

Expected: PASS.

Then run: `python -m dzmm_bot.admin.app` with the existing local environment and verify the modal body scrolls while its title/actions remain visible.

- [ ] **Step 5: Commit admin UI**

```bash
git add src/dzmm_bot/admin/templates/index.html src/dzmm_bot/admin/static/admin.js src/dzmm_bot/admin/static/admin.css tests/admin/test_app.py
git commit -m "feat: manage who is undercover in admin"
```

### Task 7: Record global rules and verify the integrated feature

**Files:**
- Modify: `rule.md`
- Modify: `tests/core/test_repository.py`
- Modify: `tests/core/test_group_commands.py`
- Modify: `tests/browser/test_worker.py`
- Modify: `tests/admin/test_app.py`

**Interfaces:**
- `rule.md` becomes the canonical concise source for who-is-undercover command, lock, private-card, voting, continuation, timeout and manual-end rules.

- [ ] **Step 1: Add final regression tests before documentation**

Add one integrated test that performs: direct mapping sync → create four-player lobby → all private cards delivered → vote → settlement → queued fifth player → `/继续` → updated role selection. Add one concurrency regression that confirms an active random event or memory duel prevents lobby creation and an active undercover session prevents a second multiplayer game.

- [ ] **Step 2: Run the integration regression**

Run: `pytest tests/core/test_group_commands.py tests/browser/test_worker.py -k "undercover and integration" -v`

Expected: PASS, proving the composed behavior works before the final full-suite run.

- [ ] **Step 3: Update `rule.md`**

Add the approved rules verbatim: 4–8 initial lobby size; private-chat prerequisite; one vote per round; tied candidates add speech then a new vote; whiteboard/police winner order; original-player/queue continuation; 20-minute waiting release; `/结束游戏`; and mutual exclusion with random events and multiplayer games.

- [ ] **Step 4: Run the full test suite**

Run: `pytest -q`

Expected: all existing and new tests pass. Record the exact pass/skip count in the implementation handoff.

- [ ] **Step 5: Commit final rules and regression coverage**

```bash
git add rule.md tests/core/test_repository.py tests/core/test_group_commands.py tests/browser/test_worker.py tests/admin/test_app.py
git commit -m "docs: record who is undercover rules"
```
