# Minimum Listener Design

## Goal

Build the first executable slice of a new DZMM bot: accept incoming messages, deduplicate them, and send `测试开始` for each new message.

## Architecture

The application core depends on two ports: `MessageSource` supplies batches of incoming messages and `MessageSender` delivers replies. `BotService` owns deduplication and reply selection; it knows neither Playwright nor any webpage selector. A future DZMM Playwright adapter will implement both ports without changing the service.

## Scope

- A `ChatMessage` value object carries an immutable message ID, sender, and text.
- `BotService.run_once()` reads one batch, skips already-seen IDs, sends `测试开始` for each new message, and marks an ID seen only after a successful send.
- Automated tests use in-memory fakes. No browser session, real group access, database, points, commands, or admin interface is included in this stage.

## Safety Rules

- No test sends a real external message.
- The reply text is exactly `测试开始`.
- A failed send remains eligible for retry on the next run.
