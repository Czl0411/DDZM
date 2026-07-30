import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from dzmm_bot.dzmm_source import DzmmMessageSource
except ModuleNotFoundError:
    DzmmMessageSource = None

from dzmm_bot.models import ChatMessage


class FakePage:
    def __init__(self, rows):
        self.rows = rows
        self.selectors = None

    def evaluate(self, script, selectors):
        self.selectors = selectors
        return self.rows


class DzmmMessageSourceTests(unittest.TestCase):
    def test_reads_non_self_messages_using_their_dom_index(self):
        self.assertIsNotNone(DzmmMessageSource)
        page = FakePage([
            {"source_index": "42", "position": 0, "sender": "甲", "text": "你好", "is_self": False},
            {"source_index": "43", "position": 1, "sender": "机器人", "text": "测试开始", "is_self": True},
            {"source_index": "44", "position": 2, "sender": "乙", "text": "在吗", "is_self": False},
        ])

        messages = DzmmMessageSource(page, group_key="main").read_new()

        self.assertEqual(
            messages,
            [
                ChatMessage("main:42", "甲", "你好"),
                ChatMessage("main:44", "乙", "在吗"),
            ],
        )

    def test_ignores_messages_without_a_stable_dom_identifier(self):
        self.assertIsNotNone(DzmmMessageSource)
        page = FakePage([
            {"source_index": "", "position": 0, "sender": "甲", "text": "你好", "is_self": False},
            {"source_index": "", "position": 1, "sender": "乙", "text": "在吗", "is_self": False},
        ])

        messages = DzmmMessageSource(page, group_key="main").read_new()

        self.assertEqual(messages, [])

    def test_keeps_dom_identity_when_the_recent_window_shifts(self):
        self.assertIsNotNone(DzmmMessageSource)
        page = FakePage([
            {"source_index": "42", "position": 0, "sender": "甲", "text": "你好", "is_self": False},
            {"source_index": "43", "position": 1, "sender": "乙", "text": "在吗", "is_self": False},
        ])
        source = DzmmMessageSource(page, group_key="main")

        first = source.read_new()
        page.rows = [
            {"source_index": "43", "position": 0, "sender": "乙", "text": "在吗", "is_self": False},
            {"source_index": "44", "position": 1, "sender": "丙", "text": "来了", "is_self": False},
        ]
        second = source.read_new()

        self.assertEqual(first[1].message_id, second[0].message_id)


if __name__ == "__main__":
    unittest.main()
