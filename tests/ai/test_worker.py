from datetime import datetime
from uuid import uuid4

from dzmm_bot.core.repository import ClaimedAIRequest
from dzmm_bot.core.schema import BEIJING


NOW = datetime(2026, 8, 8, 10, 0, tzinfo=BEIJING)


class FakeCore:
    def __init__(self, claim):
        self.claim = claim
        self.completed: list[tuple] = []
        self.failed: list[tuple] = []

    def claim_ai_request(self, worker_id, now, lease_seconds):
        claim, self.claim = self.claim, None
        return claim

    def complete_ai_request(self, *args):
        self.completed.append(args)

    def fail_ai_request(self, *args):
        self.failed.append(args)


class TimeoutClient:
    def complete(self, *args, **kwargs):
        from dzmm_bot.ai.client import MinimaxCallError

        raise MinimaxCallError("timeout")


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
