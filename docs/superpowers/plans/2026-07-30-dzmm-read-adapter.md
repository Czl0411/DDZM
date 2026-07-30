# DZMM Read-Only Adapter Implementation Plan

> **For agentic workers:** Execute inline with TDD. Steps use checkbox syntax for tracking.

**Goal:** Add a configurable, read-only DZMM message source and durable de-duplication store.

**Architecture:** A source adapts a Playwright-compatible page to `ChatMessage`; browser setup stays in a CLI. `BotService` delegates seen-ID state to a store port backed by either memory or SQLite.

**Tech Stack:** Python 3.13 standard library; Playwright is imported only by the CLI at runtime.

## Global Constraints

- No automated test opens a browser or sends an external message.
- Runtime configuration and browser profiles are never committed.
- The CLI only reads and prints messages.

---

### Task 1: Read-only source and durable seen-message store

**Files:**
- Modify: `src/dzmm_bot/ports.py`
- Modify: `src/dzmm_bot/service.py`
- Create: `src/dzmm_bot/store.py`
- Create: `src/dzmm_bot/dzmm_source.py`
- Create: `src/dzmm_bot/cli.py`
- Create: `config.example.json`
- Modify: `.gitignore`
- Test: `tests/test_dzmm_source.py`
- Modify: `tests/test_service.py`

**Interfaces:**
- Consumes: `Page.evaluate(script, selectors)` returning DOM message dictionaries.
- Produces: `DzmmMessageSource.read_new() -> list[ChatMessage]` and `SQLiteSeenMessageStore` methods `is_seen(str) -> bool`, `mark_seen(str) -> None`.

- [ ] Write failing tests for source extraction, self-message filtering, stable IDs, and SQLite-backed duplicate suppression after service recreation.
- [ ] Run `python3 -m unittest discover -s tests -v` and observe the expected failures.
- [ ] Implement the source, store, service port integration, ignored local configuration, and read-only CLI.
- [ ] Run `python3 -m unittest discover -s tests -v` and `python3 -m compileall -q src`.
- [ ] Commit the implementation on `feat/dzmm-read-adapter`.
