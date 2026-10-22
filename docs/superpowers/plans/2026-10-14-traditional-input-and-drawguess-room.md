# Traditional Command Input and Drawguess Room Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept traditional-Chinese Bot command input and drawguess answers while keeping simplified-Chinese output, then replace the drawguess long page with a fixed-viewport room whose chat remains available throughout the room lifecycle.

**Architecture:** Add one server-side Traditional-to-Simplified normalization boundary shared by command routing and drawguess answer matching. Preserve original inbound content and normalize only the slash command token plus explicitly enumerated control options. Keep the existing drawguess state machine and API, but make chat room-scoped and persistent while reorganizing the existing static Gamefy DOM into a stage workspace plus a stable chat pane.

**Tech Stack:** Python 3.12, `opencc-python-reimplemented==0.1.7`, FastAPI/SQLAlchemy, pytest, native HTML/CSS/ES modules, Node test runner, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-14-traditional-input-and-drawguess-room-design.md`

## Global Constraints

- Bot and Gamefy output remain simplified Chinese; no locale selector and no English UI.
- Persist inbound messages exactly as received; never rewrite names, reasons, chat, URLs, IDs, or other free text.
- Only slash command names and explicitly enumerated fixed control options may be normalized for routing.
- Guess matching remains exact after NFKC, trimming, case folding, and Traditional-to-Simplified conversion; no fuzzy matching.
- Do not change drawguess scoring, rounds, room admission, UID trust, or answer visibility.
- The room page must fit the Gamefy viewport; only chat messages, long ranking content, or a constrained secondary region may scroll internally.
- Preserve unrelated dirty doudizhu, system, generated, and untracked files.

## Review Focus

- A traditional management command must pass through the same authorization checks as its simplified form; Task 2 tests an unauthorized `/確認` path.
- Free-form traditional text following a command must remain byte-for-byte unchanged; Task 1 and Task 2 test `/ban 違規發言`.
- A traditional custom-command name must resolve the canonical simplified record without creating a duplicate; Task 2 tests repository create/read behavior.
- A spectator or drawer may chat but must never score from an answer; Task 3 tests every drawing-role branch.
- Very short mobile viewports must keep the composer and primary game control visible without body scrolling; Task 4 tests 320×700 in addition to the primary sizes.

---

### Task 1: Shared Chinese Input Normalizer

**Files:**
- Create: `src/dzmm_bot/core/chinese_input.py`
- Create: `tests/core/test_chinese_input.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `canonicalize_command_name(value: str) -> str`
- Produces: `canonicalize_command_content(value: str) -> str`
- Produces: `canonicalize_fixed_option(value: str, allowed: Collection[str]) -> str`
- Uses: `opencc.OpenCC("t2s")` and `unicodedata.normalize("NFKC", value)`.

- [ ] **Step 1: Write failing normalizer tests**

Add tests asserting:

```python
assert canonicalize_command_name("/刪除黑歷史") == "/删除黑历史"
assert canonicalize_command_content(" /ban 違規發言 ") == " /ban 違規發言 "
assert canonicalize_command_content("/幫助 遊戲") == "/帮助 遊戲"
assert canonicalize_command_content("普通繁體聊天") == "普通繁體聊天"
assert canonicalize_fixed_option("下一頁", {"下一页", "确认"}) == "下一页"
assert canonicalize_fixed_option("自由內容", {"下一页", "确认"}) == "自由內容"
```

Also collect every built-in/reserved/group command, convert it with an `OpenCC("s2t")` test converter, and assert the production canonicalizer returns the original simplified command.

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv/bin/python -m pytest tests/core/test_chinese_input.py -q`

Expected: collection/import failure because `dzmm_bot.core.chinese_input` does not exist.

- [ ] **Step 3: Add the dependency and minimal pure functions**

Add `opencc-python-reimplemented==0.1.7` to project dependencies, install the editable test environment, and implement the three interfaces. `canonicalize_command_content` must preserve all whitespace and all characters after the first whitespace-delimited token.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/python -m pytest tests/core/test_chinese_input.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add pyproject.toml src/dzmm_bot/core/chinese_input.py tests/core/test_chinese_input.py
git commit -m "feat: normalize traditional command input"
```

### Task 2: Canonical Bot Command Dispatch and Custom Commands

**Files:**
- Modify: `src/dzmm_bot/core/service.py`
- Modify: `src/dzmm_bot/core/commands.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/core/random_event_submissions.py` only where fixed slash options are parsed
- Test: `tests/core/test_service.py`
- Test: `tests/core/test_group_commands.py`
- Test: `tests/core/test_repository.py`

**Interfaces:**
- Consumes: `canonicalize_command_content`, `canonicalize_command_name`, and `canonicalize_fixed_option` from Task 1.
- Produces: one canonical dispatch `InboundMessage` per stored original inbound message.
- Preserves: repository inbound content and every free-form argument exactly as received.

- [ ] **Step 1: Write failing service and repository tests**

Add focused tests proving:

- `/幫助` routes to the existing simplified help response while `InboundRecord.content` remains `/幫助`.
- `/刪除黑歷史` is accepted in direct chat.
- a traditional spelling of a random-event independent command remains available during an event.
- `/ban 違規發言` reaches the same permission path as `/ban` and preserves `違規發言` in the pending reason.
- a traditional management confirmation cannot bypass authorization.
- creating `/导航` and looking it up as `/導航` resolves one record; create/update reject a canonical duplicate.
- a fixed option such as `下一頁` is accepted only at the command-specific enum boundary.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/core/test_service.py tests/core/test_group_commands.py tests/core/test_repository.py -q`

Expected: new traditional-input assertions fail while existing simplified behavior remains green.

- [ ] **Step 3: Implement one dispatch normalization boundary**

Use `dataclasses.replace` to construct a dispatch copy after persisting the original message. Route every command gate and `GroupCommandHandler` call through the dispatch copy. Replace local raw command comparisons in `CoreService` with the canonical token; do not normalize ordinary messages or AI mentions.

- [ ] **Step 4: Canonicalize command definitions and fixed control options**

Normalize command names in reservation checks and custom-command create/update/get paths. Inventory existing exact comparisons against fixed command options, apply `canonicalize_fixed_option` at each enum boundary, and add a parameterized test for the resulting option set. Keep all free-form tails untouched.

- [ ] **Step 5: Verify focused and command regression tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/core/test_service.py \
  tests/core/test_group_commands.py \
  tests/core/test_repository.py \
  tests/core/test_random_event_submissions.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/dzmm_bot/core/service.py src/dzmm_bot/core/commands.py \
  src/dzmm_bot/core/repository.py src/dzmm_bot/core/random_event_submissions.py \
  tests/core/test_service.py tests/core/test_group_commands.py \
  tests/core/test_repository.py
git commit -m "feat: accept traditional bot commands"
```

### Task 3: Traditional Guess Matching and Room-Scoped Chat

**Files:**
- Modify: `src/dzmm_bot/core/drawguess_words.py`
- Modify: `src/dzmm_bot/core/drawguess_repository.py`
- Test: `tests/core/test_drawguess_state.py`
- Test: `tests/core/test_drawguess_repository.py`
- Test: `tests/core/test_drawguess_end_to_end.py`

**Interfaces:**
- Consumes: the Task 1 Traditional-to-Simplified normalizer without changing word display values.
- Produces: exact simplified/traditional answer equivalence in `word_matches(word_id: str, text: str) -> bool`.
- Produces: room-scoped chat visible across turn IDs and rematches, capped at the newest 100 messages.

- [ ] **Step 1: Write failing guess and role tests**

Add tests asserting `蘋果`, `自行車`, and `腳踏車` match their existing simplified words while `我猜是蘋果` does not. Add repository tests proving a current drawer, an already-guessed player, and an employee spectator can send ordinary chat during drawing, but only an eligible unguessed seated player scores.

- [ ] **Step 2: Write failing persistence tests**

Create messages in multiple turn IDs, advance through reveal and a rematch, and assert the room view returns them in chronological order. Insert 101 messages with valid one-second spacing and assert only the newest 100 remain.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/core/test_drawguess_state.py \
  tests/core/test_drawguess_repository.py \
  tests/core/test_drawguess_end_to_end.py -q
```

Expected: traditional answers, role-chat permissions, and cross-turn persistence assertions fail.

- [ ] **Step 4: Implement minimal matching and chat changes**

Normalize guess candidates through the shared t2s function. Stop deleting `Message` rows on turn changes/rematches, query messages by room rather than current turn, allow every employee viewer to chat unless the room is closed, and run guess scoring only for an unguessed seated non-drawer. After each insert, delete rows older than the newest 100 for that room.

- [ ] **Step 5: Verify GREEN and answer privacy**

Run the Task 3 command again plus:

```bash
.venv/bin/python -m pytest tests/core/test_drawguess_api.py -q
```

Expected: all tests pass and no projection exposes an unrevealed answer.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/dzmm_bot/core/drawguess_words.py \
  src/dzmm_bot/core/drawguess_repository.py \
  tests/core/test_drawguess_state.py tests/core/test_drawguess_repository.py \
  tests/core/test_drawguess_end_to_end.py
git commit -m "fix: support traditional guesses and persistent chat"
```

### Task 4: Fixed-Viewport Drawguess Room UI

**Files:**
- Modify: `gamefy/drawguess/publish/index.html`
- Modify: `gamefy/drawguess/publish/game.js`
- Modify: `gamefy/drawguess/publish/style.css`
- Test: `gamefy/drawguess/tests/test_drawguess_sandbox.py`

**Interfaces:**
- Preserves: current `DrawguessClient` request payloads and state transitions.
- Produces: `#room-view` containing one stable `.room-layout`, one `.stage-workspace`, and one persistent `.chat-column`.
- Produces: stage-specific content that is shown/hidden inside the workspace without adding body height.

- [ ] **Step 1: Add failing layout and lifecycle browser tests**

For waiting, selecting, drawing, revealing, and finished snapshots, assert:

- `body.scrollHeight <= innerHeight` and no horizontal overflow at 320×700, 390×844, and 1280×900;
- the room toolbar, current primary action, and chat composer are visible;
- `.chat-column` remains the same DOM node across state refreshes;
- chat messages scroll internally when long;
- a long ranking scrolls only inside its list;
- the canvas and drawing controls fit without page scrolling during the drawer turn.

- [ ] **Step 2: Run Playwright and verify RED**

Run: `.venv/bin/python -m pytest gamefy/drawguess/tests/test_drawguess_sandbox.py -q`

Expected: the new fixed-layout and persistent-chat assertions fail against the stacked page.

- [ ] **Step 3: Restructure the existing DOM without changing API behavior**

Move the toolbar outside the stage workspace, place waiting/choosing/play/reveal/ranking inside `.stage-workspace`, and place `.chat-column` as its stable sibling. Remove chat creation from `#play-area`. Keep one composer for every stage and update only its prompt/permission text.

- [ ] **Step 4: Implement fixed-height responsive CSS**

Make the room shell a minmax-constrained grid occupying the remaining app height. Use desktop two-column and mobile vertical fixed-region layouts. Give overflow only to `.messages`, `.ranking-list`, and the explicitly constrained secondary workspace fallback. Keep 44px controls, focus visibility, safe-area padding, and reduced-motion behavior.

- [ ] **Step 5: Update render permissions and stage overlays**

Keep chat input enabled for every employee viewer unless the room is closed. Represent reveal inside the stage workspace rather than below the canvas. Preserve the existing timer, drawing tools, answer hiding, IME composition guard, reconnect flow, and request payloads.

- [ ] **Step 6: Verify browser and JavaScript tests**

Run:

```bash
node --test gamefy/drawguess/tests/*.test.mjs
.venv/bin/python -m pytest gamefy/drawguess/tests/test_drawguess_sandbox.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Capture visual evidence**

Save waiting and drawing screenshots for 390×844 and 1280×900 under `/tmp/`, inspect them for clipping, nested-scroll confusion, inaccessible controls, and accidental blank space.

- [ ] **Step 8: Commit Task 4**

```bash
git add gamefy/drawguess/publish/index.html \
  gamefy/drawguess/publish/game.js \
  gamefy/drawguess/publish/style.css \
  gamefy/drawguess/tests/test_drawguess_sandbox.py
git commit -m "feat: keep drawguess room and chat on one screen"
```

### Task 5: Full Verification and Deployment

**Files:**
- Modify only generated Gamefy release metadata created by the official deploy command.
- Do not stage unrelated working-tree files.

**Interfaces:**
- Consumes: completed Tasks 1–4.
- Produces: tested server code and a published drawguess Gamefy revision.

- [ ] **Step 1: Run affected Python suites**

Run:

```bash
.venv/bin/python -m pytest \
  tests/core/test_chinese_input.py \
  tests/core/test_service.py \
  tests/core/test_group_commands.py \
  tests/core/test_repository.py \
  tests/core/test_random_event_submissions.py \
  tests/core/test_drawguess_state.py \
  tests/core/test_drawguess_repository.py \
  tests/core/test_drawguess_end_to_end.py \
  tests/core/test_drawguess_api.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the complete project test suite**

Run: `.venv/bin/python -m pytest -q`

Expected: PASS. If unrelated pre-existing failures occur, record every failing test by name before proceeding.

- [ ] **Step 3: Run Gamefy verification**

Run the Node and Playwright commands from Task 4, then run the existing Gamefy CLI check with reload and slow-start diagnostics.

Expected: functional tests pass; report any platform warning exactly rather than describing it as clean.

- [ ] **Step 4: Review the task-only diff**

Run `git diff --check`, inspect `git status --short`, and verify every staged path belongs to this plan. Confirm unrelated doudizhu and untracked system files remain untouched.

- [ ] **Step 5: Deploy the Bot service**

Back up the current server release/config, deploy the committed code and dependency, restart only the relevant DZMM service units, then verify `/healthz`, database availability, listener connection state, and logs without exposing secrets.

- [ ] **Step 6: Smoke-test traditional commands**

In the configured monitored group or a safe direct chat, verify one harmless traditional command returns the normal simplified response and its stored inbound remains original. Do not exercise destructive management commands in production.

- [ ] **Step 7: Publish and check the drawguess Gamefy revision**

Deploy game ID `3767285`, verify the published revision, and confirm the game remains available in the configured game group. Test a three-player room through at least one traditional correct guess when users are available; otherwise report that live multiplayer confirmation remains pending.

- [ ] **Step 8: Commit generated release metadata**

```bash
git add gamefy/drawguess/.dzmm/lock.json gamefy/drawguess/.dzmm/releases.json
git commit -m "chore: publish drawguess room update"
```
