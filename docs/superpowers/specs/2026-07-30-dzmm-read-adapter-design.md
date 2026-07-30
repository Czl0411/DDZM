# DZMM Read-Only Adapter Design

## Goal

Read recent, non-self messages from a configured DZMM group through Playwright without sending any external message.

## Architecture

`DzmmMessageSource` implements the existing `MessageSource` port. It is given an already-open page and selector settings, extracts a bounded DOM snapshot, filters the bot's own messages, and emits `ChatMessage` objects. The browser lifecycle remains in a CLI runner so the source stays independently testable.

`SQLiteSeenMessageStore` implements persistent message de-duplication for `BotService`. Before sending, a service atomically claims a message ID with a unique lease token; it confirms or releases only its own token. Claims expire after five minutes so a stopped process cannot block a later retry indefinitely. This is at-least-once delivery: a process crash after sending but before confirmation can be retried. A memory store remains the default for existing tests.

## Safety Rules

- The runner is read-only and has no sender implementation.
- `config.local.json`, browser profiles, URLs, and SQLite runtime data are ignored by Git.
- The source prefers a DOM `data-message-id`, `data-id`, `data-index`, or the optional `selectors.message_id` value. If none exists, it emits a deterministic fallback from sender, text, and that identical message's occurrence in the current DOM. The fallback permits read-only inspection but is not guaranteed unique if the platform virtualizes its message list; configure `message_id` with a platform-stable timestamp/ID before adding a sender.
