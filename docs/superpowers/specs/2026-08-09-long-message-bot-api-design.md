# Long Message Bot API Design

## Goal

Send long group replies as one message through DZMM's Bot API while preserving the existing browser WebSocket path for ordinary messages.

## Routing

- A group reply longer than 1,000 characters or containing more than 10 newline characters uses `POST /api/bot/send-message` with `X-Bot-Token`.
- Ordinary group replies continue through the browser WebSocket gateway.
- Direct messages and messages scheduled for recall continue through the browser gateway because their existing destination and recall behavior must remain unchanged.
- If `DZMM_BOT_API_TOKEN` is absent, all existing splitting and browser delivery behavior remains unchanged.

## Data flow

When the token is configured, Core keeps qualifying long group replies intact instead of splitting them. The outbound claim includes `recall_after_seconds`, allowing Browser Worker to exclude recalled messages from Bot API routing. Browser Worker extracts the group chatroom ID from `DZMM_CHAT_URL`, sends qualifying text through `DzmmBotSender`, and confirms the returned platform message ID through the existing fenced acknowledgement endpoint.

## Failure behavior

Bot API non-200 responses, malformed JSON, unsuccessful response bodies, and missing message IDs raise a send error. The existing Worker failure path releases or fails the outbound lease; it does not silently fall back to WebSocket, which avoids duplicate delivery when the Bot API response is ambiguous.

## Configuration and security

`DZMM_BOT_API_TOKEN` is optional and never logged. When configured, `DZMM_CHAT_URL` must contain the group `c` query parameter. The production environment already provides a non-empty token.

## Verification

Unit tests cover request shape, token header, response validation, routing thresholds, exclusions for direct and recalled messages, intact Core queueing, and settings parsing. Deployment verification runs the complete test suite, checks all services and persisted listener status, then checks production logs after a long-message send.
