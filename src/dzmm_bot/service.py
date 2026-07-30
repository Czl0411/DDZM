import secrets

from .ports import MessageSender, MessageSource, SeenMessageStore


class MemorySeenMessageStore:
    def __init__(self):
        self._message_ids: set[str] = set()
        self._claimed_message_ids: dict[str, str] = {}

    def claim(self, message_id: str) -> str | None:
        if message_id in self._message_ids or message_id in self._claimed_message_ids:
            return None
        claim_token = secrets.token_urlsafe(16)
        self._claimed_message_ids[message_id] = claim_token
        return claim_token

    def mark_seen(self, message_id: str, claim_token: str) -> bool:
        if self._claimed_message_ids.get(message_id) != claim_token:
            return False
        del self._claimed_message_ids[message_id]
        self._message_ids.add(message_id)
        return True

    def release_claim(self, message_id: str, claim_token: str) -> None:
        if self._claimed_message_ids.get(message_id) == claim_token:
            del self._claimed_message_ids[message_id]


class BotService:
    def __init__(self, source: MessageSource, sender: MessageSender, seen_store: SeenMessageStore | None = None):
        self._source = source
        self._sender = sender
        self._seen_store = seen_store or MemorySeenMessageStore()

    def run_once(self) -> int:
        replies = 0
        for message in self._source.read_new():
            claim_token = self._seen_store.claim(message.message_id)
            if not claim_token:
                continue
            if self._sender.send(message, "测试开始"):
                self._seen_store.mark_seen(message.message_id, claim_token)
                replies += 1
            else:
                self._seen_store.release_claim(message.message_id, claim_token)
        return replies
