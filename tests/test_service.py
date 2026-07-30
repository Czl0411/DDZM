import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from dzmm_bot.models import ChatMessage
    from dzmm_bot.service import BotService
except ModuleNotFoundError:
    ChatMessage = None
    BotService = None

try:
    from dzmm_bot.store import SQLiteSeenMessageStore
except ModuleNotFoundError:
    SQLiteSeenMessageStore = None


class StaticSource:
    def __init__(self, messages):
        self.messages = messages

    def read_new(self):
        return self.messages


class RecordingSender:
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.sent = []

    def send(self, message, text):
        self.sent.append((message.message_id, text))
        return self.outcomes.pop(0) if self.outcomes else True


class BotServiceTests(unittest.TestCase):
    def test_replies_to_each_new_message(self):
        self.assertIsNotNone(ChatMessage)
        self.assertIsNotNone(BotService)
        source = StaticSource([
            ChatMessage("m-1", "甲", "你好"),
            ChatMessage("m-2", "乙", "在吗"),
        ])
        sender = RecordingSender()

        replies = BotService(source, sender).run_once()

        self.assertEqual(replies, 2)
        self.assertEqual(sender.sent, [("m-1", "测试开始"), ("m-2", "测试开始")])

    def test_does_not_reply_twice_to_the_same_message_id(self):
        self.assertIsNotNone(ChatMessage)
        self.assertIsNotNone(BotService)
        source = StaticSource([ChatMessage("m-1", "甲", "你好")])
        sender = RecordingSender()
        service = BotService(source, sender)

        service.run_once()
        replies = service.run_once()

        self.assertEqual(replies, 0)
        self.assertEqual(sender.sent, [("m-1", "测试开始")])

    def test_retries_a_message_when_its_previous_send_failed(self):
        self.assertIsNotNone(ChatMessage)
        self.assertIsNotNone(BotService)
        source = StaticSource([ChatMessage("m-1", "甲", "你好")])
        sender = RecordingSender(outcomes=[False, True])
        service = BotService(source, sender)

        first_replies = service.run_once()
        second_replies = service.run_once()

        self.assertEqual(first_replies, 0)
        self.assertEqual(second_replies, 1)
        self.assertEqual(sender.sent, [("m-1", "测试开始"), ("m-1", "测试开始")])

    def test_persistent_store_prevents_duplicate_reply_after_service_restart(self):
        self.assertIsNotNone(SQLiteSeenMessageStore)
        source = StaticSource([ChatMessage("m-1", "甲", "你好")])
        sender = RecordingSender()
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteSeenMessageStore(Path(directory) / "bot.db")
            BotService(source, sender, seen_store=store).run_once()
            replies = BotService(source, sender, seen_store=store).run_once()

        self.assertEqual(replies, 0)
        self.assertEqual(sender.sent, [("m-1", "测试开始")])

    def test_sqlite_store_grants_a_message_claim_to_only_one_service(self):
        self.assertIsNotNone(SQLiteSeenMessageStore)
        with tempfile.TemporaryDirectory() as directory:
            first = SQLiteSeenMessageStore(Path(directory) / "bot.db")
            second = SQLiteSeenMessageStore(Path(directory) / "bot.db")
            first_token = first.claim("m-1")
            self.assertIsNotNone(first_token)
            self.assertIsNone(second.claim("m-1"))
            first.release_claim("m-1", first_token)
            second_token = second.claim("m-1")
            self.assertIsNotNone(second_token)
            self.assertTrue(second.mark_seen("m-1", second_token))
            self.assertIsNone(first.claim("m-1"))

    def test_stale_sqlite_worker_cannot_release_a_newer_claim(self):
        self.assertIsNotNone(SQLiteSeenMessageStore)
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "bot.db"
            first = SQLiteSeenMessageStore(database_path, claim_ttl_seconds=1)
            second = SQLiteSeenMessageStore(database_path, claim_ttl_seconds=1)
            first_token = first.claim("m-1")
            self.assertIsNotNone(first_token)
            with __import__("sqlite3").connect(database_path) as connection:
                connection.execute("update message_claims set claimed_at = 0 where message_id = 'm-1'")
            second_token = second.claim("m-1")
            self.assertIsNotNone(second_token)

            first.release_claim("m-1", first_token)
            self.assertIsNone(SQLiteSeenMessageStore(database_path).claim("m-1"))
            self.assertFalse(first.mark_seen("m-1", first_token))
            self.assertTrue(second.mark_seen("m-1", second_token))


if __name__ == "__main__":
    unittest.main()
