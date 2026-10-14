# Mistrealm Classic 120 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver the approved 120-card original-art game using Witcher 3 in-game rules, editable decks, hidden pre-match selections and verified multiplayer play.

**Architecture:** Keep the deployed v1 state engine intact while developing a separate classic catalogue and pure rules engine. Repository/API select the engine by a persisted rules_version, validate saved and locked deck snapshots, and project only permitted information. A separate classic frontend renders server-supplied legal choices; it never reimplements authoritative scoring.

**Tech Stack:** Python/FastAPI/SQLAlchemy/Alembic/PostgreSQL; existing vanilla JavaScript/CSS, Gamefy SDK; pytest/Node/Playwright; built-in imagegen and deterministic WebP conversion.

**Spec:** docs/superpowers/specs/2026-10-15-mistrealm-classic-120.md

## Global Constraints

- 120 collectable definitions: 102 units, 10 leaders, 8 specials. Two transformation definitions are separate.
- Three rows, no invented per-row card cap; minimum22 units, maximum10 specials, one same-faction leader; inventory limits from copies.
- Preserve UID trust and avatarUrl/name display; no employee, currency or token coupling.
- No production deploy during implementation; existing v1 remains playable.
- Original art/name/text only; no copied Witcher media. No new gameplay mechanics to patch difficult original interactions.
- Reuse /Users/zhijian/.codex/worktrees/mistrealm/DDZM; do not change the dirty primary checkout.
- Run deterministic/local tests without enrolling synthetic players in the production public queue.

## Review Focus

- Recursive medic/spy/muster interactions must finish exactly once and maintain card conservation; Task3.
- A malicious opponent must not infer unlocked faction, deck order or pending choice options from HTTP/SSE; Task4.
- Saving a deck during matchmaking cannot change the locked deck; stale tickets and requests retain existing protections; Task4.
- v1 rooms, including rematch and timeout, must never be parsed as classic state; Task4/7.
- Missing avatar/art, long names, more than9 row units, rapid double taps, reconnect during a medic choice and skewed client clocks must remain usable; Task5/6.

## Task 1: Rule contracts and original 120-card catalogue

Files: create src/dzmm_bot/core/mistrealm_classic_cards.py, tests/core/test_mistrealm_classic_cards.py, scripts/export_mistrealm_classic.py; update the spec's evidence section.

Interfaces: CLASSIC_CARDS keyed stable IDs c001..c120; each has name,faction,type,rows,power,abilities,hero,copies,art. Separate TRANSFORMS. validate_deck(faction,leader,counts)->normalized snapshot or ValueError. STARTER_DECKS contains two per faction. Export identical catalogue to gamefy/mistrealm/publish/classic/cards.json.

- [ ] Verify unresolved digital-version edge cases from source material; record each rule, evidence and expected scenario. Do not silently guess hero eligibility or leader interactions.
- [ ] Write failing assertions:120 unique IDs/names,102 units/10 leaders/8 specials, five factions plus neutral, valid summon groups/transforms, no legacy damage/armor effects. Reject21 units,11 specials,other-faction leaders/cards,negative/noninteger/excess counts,unknown IDs.
- [ ] Run the new test file and record expected failures.
- [ ] Implement catalogue using approved rows and explicit copies. Build10 legal starter decks; each meaningful strategy uses its faction mechanisms.
- [ ] Export from authoritative data; test equality and all10 starter deck validators; commit.

## Task 2: Classic board, scoring and round lifecycle

Files: create src/dzmm_bot/core/mistrealm_classic_state.py, src/dzmm_bot/core/mistrealm_classic_scoring.py, tests/core/test_mistrealm_classic_scoring.py, tests/core/test_mistrealm_classic_state.py.

Interfaces: new_state(host,deck_snapshot,now_ms)->dict with rules_version=2; apply_action(state,seat,action,payload,now_ms,rng)->new dict; advance(state,now_ms,rng)->new dict; project(state,seat)->dict. Keep signatures compatible with v1 where possible; deck/lock data are explicit arguments and actions. score_rows(state,seat)->list[int]; derived power recalculates from base and board effects, not accumulated edits.

- [ ] Write failing cases for three rows, >9 units,10-card start/max2 replacement/no replacement instantly redrawn, no automatic later draw,pass locking,2-gem ties, faction tie advantage and mirror, winner/first-choice progression, no first-unit bonus.
- [ ] Write scoring fixtures for two/three bonded copies; weather+bond+morale+horn; hero immunity; duplicate horns; morale excludes own source; clear weather restores derived power.
- [ ] Run red tests, implement score and lifecycle against evidence from Task1, run green. Inject RNG for all random selection.
- [ ] Keep failed actions copy-on-write and enforce turn/phase; prove invalid actions leave input unchanged; commit.

## Task 3: Effects, leader passives and nested choices

Files: create src/dzmm_bot/core/mistrealm_classic_effects.py, tests/core/test_mistrealm_classic_effects.py; modify classic_state.py.

Interfaces: resolve_effects(state,seat,card,now_ms,rng) resolves automatic effects until a pending choice is required; pending records actor,kind,eligible IDs,continuation. choose action accepts one server-provided option; options project only to actor. One hand play remains one action even with a medic chain. Persist continuation as JSON, never Python closures.

- [ ] Add failing cases:spy draw2/deck exhaustion;decoy 0-power placeholder;medic->medic->spy;hero medic;hero spy;no revive hero;revived muster draws correct hand/deck group exactly once.
- [ ] Add scorch global highest ties/hero protection;row scorch threshold;one/two horn sources;all8 specials;all10 leaders including cancellation of passive/active effects;faction leave/random third-round returns;both transformations and round cleanup.
- [ ] Test reconnect during nested choice, duplicate request, illegal target, empty eligible list and timeout fallback. Timeout chooses a deterministic legal fallback to finish the existing action before normal turn progression.
- [ ] Implement minimal effect resolver, run all classic tests, assert physical card IDs remain unique across zones except explicit placeholders/transforms; commit.

## Task 4: Saved decks, matchmaking snapshots and private selections

Files: modify schema.py, mistrealm_repository.py, mistrealm_api.py; create migrations/versions/20261015_113_mistrealm_classic_decks.py (confirm head before naming), tests/core/test_mistrealm_classic_repository.py, tests/core/test_mistrealm_classic_api.py.

Interfaces: player-owned saved decks in dedicated table (id,player_id,name,faction,leader,counts,updated_at). POST /decks saves; GET /decks lists caller only; POST /decks/{id}/delete deletes caller-owned unlocked record. Classic create/join/queue APIs use distinct /classic prefix during development; payloads pass deck_id, server fetches and validates. Snapshot is stored on queue and room, not a mutable pointer. Existing v1 queue candidates cannot pair with v2.

- [ ] Red tests for other-owner read/write/delete denial,illegal counts,invalid leader,old deck edited after queue,late cancellation/heartbeat,simultaneous pairing,copy-private projection and no pre-lock reveal.
- [ ] Implement saved-deck schema/migration and versioned queue snapshots. Branch repository operations using persisted rules_version; absent version means v1. Never derive opponent deck from client payload.
- [ ] Self-owned saved decks and own private selections are visible; opponent sees identity and lock status until both lock, then faction/leader only. No raw room.state in API/errors/SSE.
- [ ] Local SQLite tests then disposable PostgreSQL migrations110->112->113 and113->112,concurrent seats and queue snapshots. Do not reuse production DB for destructive tests.
- [ ] Confirm all existing v1 API/matchmaking tests unchanged and green; commit.

## Task 5: Deck builder and classic match UI

Files: create gamefy/mistrealm/publish/classic/index.html, game.js, client.js, style.css; reuse shared original asset files. Add gamefy/mistrealm/tests/classic_client.test.mjs and classic_browser.py.

Interfaces: home has saved-deck selection/build/quickmatch/create/join; builder counts units/specials/copies and chooses leader, surfaces server validation. Board consumes project() legal choices and scores. Own deck previews never become opponent previews.

- [ ] Red browser cases:construct/save/reload valid deck;illegal limit feedback;lock before matchmaking;two-seat hidden faction then reveal;avatarUrl and missing avatar;leader display;three-row battle,weather,horn,medic target selection.
- [ ] Implement UI in existing original visual language. For large boards use responsive card width/row scroll rather than gameplay capacity restriction. Clearly show base/current power and sources without exposing hidden cards.
- [ ] Synchronize timers to server time or elapsed duration, not raw device Date.now. Reuse proven epoch/heartbeat protections. No localStorage in sandbox.
- [ ] Browser run1366/844-landscape/390 widths,50+row card stress,skew clock,reload while choosing,disconnect recovery; zero overflow/unhandled exceptions. Human-inspect screenshots; commit.

## Task 6: Original asset production and integration

Files: create gamefy/mistrealm/art-updates/classic-120-manifest.json; original PNGs under source-art/classic; WebP under publish/assets/classic; add tests/test_classic_assets.py.

Interfaces: manifest maps every card/transform to status,prompt,reference,original path,WebP path; art path in catalogue must resolve uniquely or have explicit reviewed reuse. Generation status does not become complete until file and visual review exist.

- [ ] Inventory current16 card illustrations; record retain/repaint/archive decisions against new effects. Existing recall artwork must be reconsidered for new medic role. Define five faction visual guides and unique silhouette briefs.
- [ ] Read imagegen skill; use built-in imagegen, preserve original style but do not use Witcher reference art. Generate in inspectable batches grouped by faction; inspect every result for identity consistency,duplicate composition and baked-in text.
- [ ] Complete120 playable illustrations plus2 transformation images,5 original emblems and required three-row/weather/ability UI. Reuse only documented approved originals; never deliver repeated placeholders as finished art.
- [ ] Convert deterministically to WebP, retain PNG/prompt records. Export catalogue, verify all resources and MIME decoding. Target package under40MiB and per-art under800KiB, measure actual Gamefy upload and weak-network load rather than relying on100MiB advertised limit.
- [ ] Human-inspect catalogue/room/battle at phone sizes; commit asset batch receipts and final manifest.

## Task 7: Integration review and release preparation

Files: update README.md, docs/mistrealm-deployment.md, docs/mistrealm-validation.md; add classic_e2e.py and classic_postgres tests.

- [ ] Full matrix:10 starter decks legal;all120 cards reachable;all abilities executed;all5 faction passives;both seats;10 leaders;three-round endings,ties,concessions,rematch.
- [ ] Run v1 regression plus classic unit/API/client/browser/PostgreSQL tests. Fresh review of rules fidelity,hidden-info projection,queue locking and original art completeness; fix concrete findings.
- [ ] Gamefy staging preview with two platform test identities,weak-network/reload. Inspect actual screenshots, not just exit codes. No public queue test players.
- [ ] Produce concrete release bundle and migration/rollback steps. v1 continues existing rooms; v2 becomes new-game default only during authorized cutover. Never reinterpret v1 state or forcibly kill active games.
- [ ] Before production: back up code/DB/config, rehearse migration on isolated copy, record active-room counts, deploy backend then frontend, verify all uploaded files. Public listing quota is separate; report actual state.

## Execution proposal

Native execution in this same isolated worktree is recommended: card schema, scoring, effects and UI are tightly dependent, so one implementation context reduces divergent interpretations. A fresh reviewer is used after the full implementation. No additional implementation subagents are assumed.

Review required by writing-plans before implementation: confirm this plan covers the already-approved design; then execute Tasks1–7 in order, reporting actual progress and unfinished asset batches honestly.
