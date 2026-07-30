from .ports import MessageSender, MessageSource, SeenMessageStore


class MemorySeenMessageStore:
    def __init__(self):
        self._message_ids: set[str] = set()
        self._claimed_message_ids: set[str] = set()

    def claim(self, message_id: str) -> bool:
        if message_id in self._message_ids or message_id in self._claimed_message_ids:
            return False
        self._claimed_message_ids.add(message_id)
        return True

    def mark_seen(self, message_id: str) -> None:
        self._claimed_message_ids.discard(message_id)
        self._message_ids.add(message_id)

    def release_claim(self, message_id: str) -> None:
        self._claimed_message_ids.discard(message_id)


class BotService:
    def __init__(self, source: MessageSource, sender: MessageSender, seen_store: SeenMessageStore | None = None):
        self._source = source
        self._sender = sender
        self._seen_store = seen_store or MemorySeenMessageStore()

    def run_once(self) -> int:
        replies = 0
        for message in self._source.read_new():
            if not self._seen_store.claim(message.message_id):
                continue
            if self._sender.send(message, "测试开始"):
                self._seen_store.mark_seen(message.message_id)
                replies += 1
            else:
                self._seen_store.release_claim(message.message_id)
        return replies
