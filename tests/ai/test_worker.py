from datetime import datetime
from uuid import uuid4

from dzmm_bot.ai.core_client import (
    AIConversationMessage,
    AIImpressionCandidate,
    AIImpressionEntry,
    AIMemoryClaim,
)
from dzmm_bot.ai.impressions import AIImpressionOperation
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
        history_messages=(),
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
        history_messages=(),
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


def test_ai_worker_forwards_conversation_history_to_provider():
    from dzmm_bot.ai.worker import AIWorker

    history = (
        AIConversationMessage("user", "第一问"),
        AIConversationMessage("assistant", "第一答"),
    )
    claim = ClaimedAIRequest(
        id=uuid4(),
        lease_token=uuid4(),
        system_prompt="system",
        history_messages=history,
        user_content="继续",
        max_response_chars=20,
        timeout_seconds=10,
    )
    core = FakeCore(claim)
    captured = {}

    class CapturingClient:
        def complete(self, system_prompt, user_content, **kwargs):
            captured.update(
                system_prompt=system_prompt,
                user_content=user_content,
                **kwargs,
            )
            return "收到"

    assert AIWorker(
        "ai-1", core, CapturingClient(), clock=lambda: NOW
    ).run_once() is True
    assert captured == {
        "system_prompt": "system",
        "user_content": "继续",
        "history_messages": history,
        "max_chars": 20,
        "timeout_seconds": 10,
    }


def _memory_claim():
    entry = AIImpressionEntry(
        id=uuid4(),
        category="interests",
        content="喜欢桌游",
        pinned=False,
    )
    candidate = AIImpressionCandidate(
        id=uuid4(),
        category="expression_style",
        content="偏好简短回复",
        support_batches=1,
        conflict_entry_id=None,
    )
    return AIMemoryClaim(
        user_id=uuid4(),
        target_message_id=uuid4(),
        lease_token=uuid4(),
        extraction_prompt="只记录稳定偏好",
        max_memory_chars=1000,
        stable_entries=(entry,),
        candidates=(candidate,),
        source_messages=("我也喜欢短回复",),
        source_message_count=1,
    )


def test_reply_worker_never_claims_memory_when_reply_queue_is_empty():
    from dzmm_bot.ai.worker import AIWorker

    claim = _memory_claim()
    core = FakeCore(None, memory_claim=claim)

    assert AIWorker("ai-1", core, object(), clock=lambda: NOW).run_once() is False
    assert core.memory_claim is claim


def test_memory_worker_parses_json_and_completes_structured_operations():
    from dzmm_bot.ai.memory_worker import AIMemoryWorker

    claim = _memory_claim()
    core = FakeCore(None, memory_claim=claim)

    class SuccessClient:
        def complete(self, system_prompt, user_content, **kwargs):
            assert str(claim.stable_entries[0].id) in system_prompt
            assert str(claim.candidates[0].id) in system_prompt
            assert user_content == "我也喜欢短回复"
            assert kwargs == {"max_chars": 8000, "timeout_seconds": 20}
            return (
                '{"operations":[{"action":"reinforce_candidate",'
                f'"candidate_id":"{claim.candidates[0].id}"}}]}}'
            )

    assert AIMemoryWorker(
        "memory-1", core, SuccessClient(), clock=lambda: NOW
    ).run_once() is True
    assert core.memory_completed == [
        (
            claim.user_id,
            "memory-1",
            claim.lease_token,
            claim.target_message_id,
            (
                AIImpressionOperation(
                    action="reinforce_candidate",
                    candidate_id=claim.candidates[0].id,
                ),
            ),
            1,
            NOW,
        )
    ]


def test_memory_worker_maps_invalid_json_and_timeout_to_safe_categories():
    from dzmm_bot.ai.memory_worker import AIMemoryWorker

    invalid_claim = _memory_claim()
    invalid_core = FakeCore(None, memory_claim=invalid_claim)

    class InvalidClient:
        def complete(self, *args, **kwargs):
            return "不是 JSON"

    assert AIMemoryWorker(
        "memory-1", invalid_core, InvalidClient(), clock=lambda: NOW
    ).run_once() is True
    assert invalid_core.memory_failed == [
        (
            invalid_claim.user_id,
            "memory-1",
            invalid_claim.lease_token,
            "invalid_response",
            NOW,
        )
    ]

    timeout_claim = _memory_claim()
    timeout_core = FakeCore(None, memory_claim=timeout_claim)
    assert AIMemoryWorker(
        "memory-1", timeout_core, TimeoutClient(), clock=lambda: NOW
    ).run_once() is True
    assert timeout_core.memory_failed == [
        (
            timeout_claim.user_id,
            "memory-1",
            timeout_claim.lease_token,
            "timeout",
            NOW,
        )
    ]


def test_memory_worker_leaves_an_empty_queue_idle():
    from dzmm_bot.ai.memory_worker import AIMemoryWorker

    assert AIMemoryWorker(
        "memory-1", FakeCore(None), object(), clock=lambda: NOW
    ).run_once() is False
