from .ports import MessageSender, MessageSource


class BotService:
    def __init__(self, source: MessageSource, sender: MessageSender):
        self._source = source
        self._sender = sender
        self._seen_message_ids: set[str] = set()

    def run_once(self) -> int:
        replies = 0
        for message in self._source.read_new():
            if message.message_id in self._seen_message_ids:
                continue
            if self._sender.send(message, "测试开始"):
                self._seen_message_ids.add(message.message_id)
                replies += 1
        return replies
