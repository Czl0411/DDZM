# DZMM Read-Only Adapter Design

## Goal

Read recent, non-self messages from a configured DZMM group through Playwright without sending any external message.

## Architecture

`DzmmMessageSource` implements the existing `MessageSource` port. It is given an already-open page and selector settings, extracts a bounded DOM snapshot, filters the bot's own messages, and emits `ChatMessage` objects. The browser lifecycle remains in a CLI runner so the source stays independently testable.

`SQLiteSeenMessageStore` implements persistent message de-duplication for `BotService`. Before sending, a service atomically claims a message ID; it confirms the claim after a successful send and releases it after a failed send. Claims expire after five minutes so a stopped process cannot block a later retry indefinitely. A memory store remains the default for existing tests.

## Safety Rules

- The runner is read-only and has no sender implementation.
- `config.local.json`, browser profiles, URLs, and SQLite runtime data are ignored by Git.
- The source accepts only a DOM `data-message-id`, `data-id`, or `data-index`. Rows without one are skipped, because a sliding DOM position cannot safely identify a message across reads. A later platform-API adapter can provide a platform message ID where the DOM lacks one.
