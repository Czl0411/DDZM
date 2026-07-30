# DZMM Read-Only Adapter Design

## Goal

Read recent, non-self messages from a configured DZMM group through Playwright without sending any external message.

## Architecture

`DzmmMessageSource` implements the existing `MessageSource` port. It is given an already-open page and selector settings, extracts a bounded DOM snapshot, filters the bot's own messages, and emits `ChatMessage` objects. The browser lifecycle remains in a CLI runner so the source stays independently testable.

`SQLiteSeenMessageStore` implements persistent message de-duplication for `BotService`. The service receives the store through a small port; a memory store remains the default for existing tests.

## Safety Rules

- The runner is read-only and has no sender implementation.
- `config.local.json`, browser profiles, URLs, and SQLite runtime data are ignored by Git.
- A DOM `data-index` creates the preferred message ID. Where it is absent, the source creates a deterministic hash from the group key, DOM position, sender, and text; a later platform-API adapter can replace this fallback with a platform message ID.
