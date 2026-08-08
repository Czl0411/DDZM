# Long Message Socket Design

## Goal

Allow the bot to send normal multi-paragraph messages through Aikda's WebSocket path without replacing real line breaks.

## Evidence and hypothesis

- A verified reference client sends `message:join-room` before `message:send` and can send 65,536 Unicode characters with 100 real line breaks.
- DZMM currently waits for `message:joined` but never emits `message:join-room` itself.
- DZMM's observed rejection is the generic `请勿发送重复内容`, so it cannot be treated as a platform length limit.

## Design

`AikdaSocketGateway.send_to()` will synchronously call `message:join-room` with the requested `chatroomId`, require a successful acknowledgement, then call the existing `message:send` with unchanged text. Group and direct-message routes already share `send_to()`, so both use this sequence.

An unsuccessful join acknowledgement raises an error and prevents a send. No text rewriting or queue splitting is part of this change.

## Verification

Unit tests prove join-before-send and unchanged newlines. Production verification sends a deliberately long multiline message and confirms it with `chatroom.getMessages`.
