from .ports import MessageSender, MessageSource, SeenMessageStore


class MemorySeenMessageStore:
    def __init__(self):
        self._message_ids: set[str] = set()

    def is_seen(self, message_id: str) -> bool:
        return message_id in self._message_ids

    def mark_seen(self, message_id: str) -> None:
        self._message_ids.add(message_id)


class BotService:
    def __init__(self, source: MessageSource, sender: MessageSender, seen_store: SeenMessageStore | None = None):
        self._source = source
        self._sender = sender
        self._seen_store = seen_store or MemorySeenMessageStore()

    def run_once(self) -> int:
        replies = 0
        for message in self._source.read_new():
            if self._seen_store.is_seen(message.message_id):
                continue
            if self._sender.send(message, "测试开始"):
                self._seen_store.mark_seen(message.message_id)
                replies += 1
        return replies
