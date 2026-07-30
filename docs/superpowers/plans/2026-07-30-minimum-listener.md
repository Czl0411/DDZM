# Minimum Listener Implementation Plan

> **For agentic workers:** Execute inline with TDD. Steps use checkbox syntax for tracking.

**Goal:** Create a testable core that replies `测试开始` once per newly received message.

**Architecture:** `BotService` consumes message-source and message-sender ports. It retains seen message IDs in memory and has no browser or platform-specific dependency.

**Tech Stack:** Python 3.13 standard library and `unittest`.

## Global Constraints

- No real DZMM browser session or external message send in automated tests.
- Reply text is exactly `测试开始`.
- A message ID is committed only after its reply succeeds.

---

### Task 1: Listener service

**Files:**
- Create: `pyproject.toml`
- Create: `src/dzmm_bot/__init__.py`
- Create: `src/dzmm_bot/models.py`
- Create: `src/dzmm_bot/ports.py`
- Create: `src/dzmm_bot/service.py`
- Create: `tests/test_service.py`

**Interfaces:**
- Consumes: `MessageSource.read_new() -> list[ChatMessage]` and `MessageSender.send(ChatMessage, str) -> bool`.
- Produces: `BotService.run_once() -> int`, the count of successful replies in one polling cycle.

- [ ] Write tests for a successful reply, duplicate suppression, and retry after a failed send.
- [ ] Run `python3 -m unittest discover -s tests -v` and observe the expected import failure.
- [ ] Implement the smallest message model, ports, and service to satisfy the tests.
- [ ] Run `python3 -m unittest discover -s tests -v` and confirm all tests pass.
- [ ] Commit the implementation to the new Git repository.
