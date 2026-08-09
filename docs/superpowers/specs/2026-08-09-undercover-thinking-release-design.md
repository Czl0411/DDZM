# Undercover Gameplay and DeepSeek Thinking Release Design

## Goal

Ship the prepared 谁是卧底 flow improvements and explicitly enable thinking mode for `deepseek-v4-flash` in the same production release as long-message Bot API routing.

## 谁是卧底 changes

- Private role cards reveal only the assigned word for civilian and undercover players; the whiteboard explanation remains explicit because it has no word.
- After all private cards are delivered, the group opening message lists seat numbers and display names in order and explains how to start voting.
- A living player's first `/投票 序号` during speaking or tie-break state transitions the game into a new voting round and records that vote.

These changes remain inside `CoreRepository` and reuse the existing outbound queue, direct-room delivery, deadlines, and game state records.

## DeepSeek thinking mode

Every AI completion request sends `"thinking": {"type": "enabled"}` for `deepseek-v4-flash`. Only the final `content` is returned to the game; `reasoning_content` is not posted to chat or stored as an answer.

## CAPTCHA rollback boundary

The uncommitted CAPTCHA page detection and related manual-auth state changes are excluded from the release and removed from the original working tree. Existing committed browser authentication and persistent listener behavior remain unchanged.

## Verification

Repository tests prove private card text, ordered seat guidance, and first-vote transition. AI client tests prove the explicit official thinking toggle and final-content-only behavior. Full tests and production service/log checks cover integration.
