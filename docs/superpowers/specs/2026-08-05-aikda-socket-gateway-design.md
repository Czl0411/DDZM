# Aikda Socket Gateway Design

## Goal

Replace the Worker’s fragile DOM message listener and sender with Aikda’s
documented-by-client Socket.IO message flow, while retaining the existing
authenticated persistent browser profile only as the source of a short-lived
access token.

## Scope

- Target exactly `DZMM_CHAT_URL`’s `c` query parameter.
- Receive live `message:new` events and send text through `message:send`.
- Fetch `chatroom.getMessages` after connecting and reconnecting to close any
  gap in live delivery.
- Resolve the sender with `user.getChatroomUser` when a message is accepted.
- Filter messages authored by the bot account returned by `user.getMe`.
- Keep all timestamps as timezone-aware values and preserve the existing
  core-side idempotency by platform message ID.

Out of scope: other media message types, reply threads, DOM listener fallback,
and changes to gameplay commands or the administration UI.

## Alternatives considered

1. **Direct Socket.IO client — selected.** It uses the client’s actual
   `message:send` ACK protocol and avoids DOM selectors.
2. Browser-page bridge. It avoids handling a token outside the page, but would
   require injecting and supervising application state in Chromium.
3. HTTP polling plus DOM send. It still leaves half of the integration
   dependent on brittle rendered UI.

## Architecture

`BrowserSession` remains responsible for owning or attaching to the isolated
persistent Chromium profile. It exposes an authenticated token request helper
that performs `GET /api/auth/token` in the active Aikda page; the returned
token is held only in the Worker process memory.

`AikdaSocketGateway` implements the existing `ChatGateway` protocol. It:

1. parses the configured chat URL to determine the target chatroom ID;
2. calls `user.getMe`, establishes Socket.IO at `/ws/matching` with the token,
   and waits for `message:joined`;
3. records `message:new` events for the target room and drains them through
   `read_new()`;
4. calls `chatroom.getMessages` on initial connection and each reconnect,
   returning unseen text messages ordered by `sent_at`;
5. sends a text message as:

   ```json
   {
     "chatroomId": "<target-room>",
     "message": {
       "message_id": "<uuid>",
       "sent_by": "<bot-user-id>",
       "chatroom_id": "<target-room>",
       "sent_at": "<UTC ISO-8601>",
       "content": {"type": "text", "text": "<reply>"}
     }
   }
   ```

   via `message:send`, and treats only an ACK with `success: true` as sent.

The existing `BrowserWorker` remains the sole component that submits inbound
messages to Core and confirms outbound messages. Its existing set of seen IDs
prevents replay after a reconnect; the Core database remains the durable
idempotency boundary across process restarts.

## Failure handling

- Connection or ACK failure raises from the gateway. The Worker does not
  confirm that outbound message, so Core can lease it again.
- A disconnected Socket.IO client reconnects with a freshly acquired token and
  immediately runs message history reconciliation.
- If token acquisition, identity lookup, or connection fails, the gateway is
  unauthenticated and the existing Worker authentication-required flow applies.
- There is deliberately no DOM polling fallback. A failure is observable and
  recoverable through reconnect plus history, rather than silently losing data.

## Testing

Unit tests will use a fake Socket.IO client and fake authenticated HTTP
transport. They cover target-room filtering, self-message filtering, history
reconciliation, duplicate event suppression, token refresh on reconnect, and
ACK-gated outbound confirmation. Existing Worker lifecycle tests must continue
to pass unchanged.
