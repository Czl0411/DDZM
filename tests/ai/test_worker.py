from datetime import datetime
from uuid import uuid4

from dzmm_bot.ai.core_client import AIMemoryClaim
from dzmm_bot.core.repository import ClaimedAIRequest
from dzmm_bot.core.schema import BEIJING


NOW = datetime(2026, 8, 8, 10, 0, tzinfo=BEIJING)


class FakeCore:
    def __init__(self, claim, memory_claim=None):
        self.claim = claim
        self.memory_claim = memory_claim
        self.completed: list[tuple] = []
        self.failed: list[tuple] = []
        self.memory_completed: list[tuple] = []
        self.memory_failed: list[tuple] = []

    def claim_ai_request(self, worker_id, now, lease_seconds):
        claim, self.claim = self.claim, None
        return claim

    def complete_ai_request(self, *args):
        self.completed.append(args)

    def fail_ai_request(self, *args):
        self.failed.append(args)

    def claim_ai_memory_job(self, worker_id, now, lease_seconds):
        claim, self.memory_claim = self.memory_claim, None
        return claim

    def complete_ai_memory_job(self, *args):
        self.memory_completed.append(args)

    def fail_ai_memory_job(self, *args):
        self.memory_failed.append(args)


class TimeoutClient:
    def complete(self, *args, **kwargs):
        from dzmm_bot.ai.client import DeepSeekCallError

        raise DeepSeekCallError("timeout")


def test_ai_worker_reports_timeout_without_provider_details():
    from dzmm_bot.ai.worker import AIWorker

    claim = ClaimedAIRequest(
        id=uuid4(),
        lease_token=uuid4(),
        system_prompt="system",
        user_content="user",
        max_response_chars=20,
        timeout_seconds=10,
    )
    core = FakeCore(claim)

    assert AIWorker("ai-1", core, TimeoutClient(), clock=lambda: NOW).run_once() is True
    assert core.completed == []
    assert core.failed == [
        (claim.id, "ai-1", claim.lease_token, "timeout", NOW)
    ]


def test_ai_worker_completes_one_claim_and_leaves_empty_queue_idle():
    from dzmm_bot.ai.worker import AIWorker

    claim = ClaimedAIRequest(
        id=uuid4(),
        lease_token=uuid4(),
        system_prompt="system",
        user_content="user",
        max_response_chars=5,
        timeout_seconds=10,
    )
    core = FakeCore(claim)

    class SuccessClient:
        def complete(self, *args, **kwargs):
            return "123456"

    worker = AIWorker("ai-1", core, SuccessClient(), clock=lambda: NOW)

    assert worker.run_once() is True
    assert core.completed == [(claim.id, "ai-1", claim.lease_token, "12345", NOW)]
    assert worker.run_once() is False


def test_ai_worker_extracts_memory_only_after_reply_queue_is_empty():
    from dzmm_bot.ai.worker import AIWorker

    claim = AIMemoryClaim(
        user_id=uuid4(),
        target_message_id=uuid4(),
        lease_token=uuid4(),
        extraction_prompt="只记录稳定偏好",
        max_memory_chars=100,
        current_memory="喜欢桌游",
        source_messages=("我也喜欢短回复",),
    )
    core = FakeCore(None, memory_claim=claim)

    class SuccessClient:
        def complete(self, system_prompt, user_content, **kwargs):
            assert "已有记忆：喜欢桌游" in system_prompt
            assert user_content == "我也喜欢短回复"
            return "喜欢桌游；偏好简短回复"

    assert AIWorker("ai-1", core, SuccessClient(), clock=lambda: NOW).run_once() is True
    assert core.memory_completed == [
        (
            claim.user_id,
            "ai-1",
            claim.lease_token,
            claim.target_message_id,
            "喜欢桌游；偏好简短回复",
            NOW,
        )
    ]
