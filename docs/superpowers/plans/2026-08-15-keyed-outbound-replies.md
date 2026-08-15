# 按会话并发发送与回复定位 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让不同会话的消息有界并发发送，并让所有入站触发回复定位到原消息。

**Architecture:** Core 在出站入队时固化发送键和原消息引用快照，领取查询只选择每个发送键最早的可用消息。Browser Worker 用固定大小线程池并发处理不同键，Gateway 生成带 `content.reference` 的 Socket 载荷；同键顺序由数据库领取门禁保证。

**Tech Stack:** Python 3.12、SQLAlchemy 2、Alembic、Socket.IO、FastAPI、pytest。

## Global Constraints

- 默认并发 4，范围 1–16。
- 同一会话严格串行，不同会话允许并发。
- 所有入站触发回复均定位；无入站来源的系统消息不定位。
- 带引用长消息使用 Socket 分片，不使用当前不支持引用的 Bot API。

---

### Task 1: 持久化发送键与引用快照

**Files:**
- Modify: `src/dzmm_bot/core/schema.py`
- Modify: `src/dzmm_bot/core/repository.py`
- Modify: `src/dzmm_bot/runtime/contracts.py`
- Create: `migrations/versions/20260815_42_outbound_reply_references.py`
- Test: `tests/core/test_repository.py`
- Test: `tests/deploy/test_outbound_reply_reference_migration.py`

**Interfaces:**
- Produces: `OutboundMessage.delivery_key`, `reference_message_id`, `reference_sender_platform_id`, `reference_content_type`, `reference_text`.
- Produces: `CoreRepository.claim_outbound(..., excluded_delivery_keys=())` returning only a key's earliest unfinished row.

- [ ] Write repository tests that enqueue from an inbound message and assert the persisted reference snapshot and delivery key.
- [ ] Run `PYTHONPATH=src .venv/bin/pytest tests/core/test_repository.py -k 'outbound and (reference or delivery_key)' -q` and verify the new tests fail because fields are absent.
- [ ] Add nullable reference columns, non-null delivery key, migration backfill, contract fields, and populate them in both text/image enqueue paths.
- [ ] Add a claim test proving an earlier pending/leased row blocks the same key while another key remains claimable; verify it fails before the query change.
- [ ] Change `claim_outbound` to exclude active keys and reject rows having an earlier unfinished row for the same key.
- [ ] Run the focused repository and migration tests until green, then run `git diff --check`.

### Task 2: Socket 引用载荷

**Files:**
- Modify: `src/dzmm_bot/browser/session.py`
- Modify: `src/dzmm_bot/browser/aikda_socket.py`
- Modify: `tests/browser/test_aikda_socket.py`

**Interfaces:**
- Produces: gateway `send*` methods accepting `reference: MessageReference | None` in addition to the outgoing `message_id`.

- [ ] Add failing tests asserting text/image `message:send` payloads contain the exact `reference` object and ordinary system sends omit it.
- [ ] Run `PYTHONPATH=src .venv/bin/pytest tests/browser/test_aikda_socket.py -k reference -q` and verify failure due to the missing argument/payload.
- [ ] Extend the gateway protocol and Socket gateway to serialize the reference snapshot without altering the outgoing UUID.
- [ ] Run `PYTHONPATH=src .venv/bin/pytest tests/browser/test_aikda_socket.py -q` until green.

### Task 3: Worker 按会话有界并发

**Files:**
- Modify: `src/dzmm_bot/runtime/settings.py`
- Modify: `src/dzmm_bot/browser/main.py`
- Modify: `src/dzmm_bot/browser/worker.py`
- Modify: `deploy/env/dzmm.example.env`
- Test: `tests/runtime/test_settings.py`
- Test: `tests/browser/test_worker.py`

**Interfaces:**
- Consumes: keyed claim and outbound reference fields from Task 1; gateway reference argument from Task 2.
- Produces: `DZMM_OUTBOUND_CONCURRENCY`, default 4.

- [ ] Add failing settings tests for default 4 and bounds 1–16.
- [ ] Add worker tests with blocking fake gateways proving different keys overlap, the same key stays ordered, and one failure does not cancel another key.
- [ ] Run `PYTHONPATH=src .venv/bin/pytest tests/runtime/test_settings.py tests/browser/test_worker.py -k 'outbound or concurrency or reference' -q` and verify expected failures.
- [ ] Replace the single outbound future with a fixed pool and active-key map; fill vacant slots by claiming rows excluding active keys and confirm each future independently.
- [ ] Pass stored reference snapshots to all Socket text/image sends.
- [ ] Make long-message routing use Bot API only when the outbound has no reference; referenced messages remain chunked Socket records.
- [ ] Run the focused worker/settings tests until green.

### Task 4: 回归与文档

**Files:**
- Modify: `docs/BOT_MESSAGE_TRANSPORT_HANDOFF.md`
- Test: `tests/core/test_service.py`
- Test: `tests/browser/test_worker.py`

**Interfaces:**
- Verifies the complete transport contract.

- [ ] Add service tests proving every reply chunk/image from one inbound retains the same reference snapshot and scheduled outbounds remain unreferenced.
- [ ] Update the transport handoff with keyed ordering, concurrency configuration and reply payload.
- [ ] Run `PYTHONPATH=src .venv/bin/pytest tests/browser tests/core/test_service.py tests/core/test_repository.py tests/deploy/test_outbound_reply_reference_migration.py -q`.
- [ ] Run `PYTHONPATH=src .venv/bin/python -m pytest -q`, `node --check src/dzmm_bot/admin/static/admin.js`, `.venv/bin/alembic heads`, and `git diff --check`.
