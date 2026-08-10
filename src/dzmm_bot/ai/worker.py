from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from .client import DeepSeekCallError
from .core_client import AICorePort
from .impressions import parse_impression_operations, render_impression_prompt


class AIWorker:
    def __init__(
        self,
        worker_id: str,
        core: AICorePort,
        client,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(ZoneInfo("Asia/Shanghai")),
        lease_seconds: int = 90,
    ) -> None:
        self._worker_id = worker_id
        self._core = core
        self._client = client
        self._clock = clock
        self._lease_seconds = lease_seconds

    def run_once(self) -> bool:
        claim = self._core.claim_ai_request(
            self._worker_id, self._clock(), self._lease_seconds
        )
        if claim is not None:
            try:
                text = self._client.complete(
                    claim.system_prompt,
                    claim.user_content,
                    max_chars=claim.max_response_chars,
                    timeout_seconds=claim.timeout_seconds,
                )[: claim.max_response_chars]
            except DeepSeekCallError as error:
                self._core.fail_ai_request(
                    claim.id,
                    self._worker_id,
                    claim.lease_token,
                    error.category,
                    self._clock(),
                )
            else:
                self._core.complete_ai_request(
                    claim.id,
                    self._worker_id,
                    claim.lease_token,
                    text,
                    self._clock(),
                )
            return True
        memory_claim = self._core.claim_ai_memory_job(
            self._worker_id, self._clock(), self._lease_seconds
        )
        if memory_claim is None:
            return False
        try:
            response = self._client.complete(
                render_impression_prompt(
                    memory_claim.extraction_prompt,
                    stable_entries=[
                        (entry.id, entry.category, entry.content, entry.pinned)
                        for entry in memory_claim.stable_entries
                    ],
                    candidates=[
                        (
                            candidate.id,
                            candidate.category,
                            candidate.content,
                            candidate.support_batches,
                            candidate.conflict_entry_id,
                        )
                        for candidate in memory_claim.candidates
                    ],
                ),
                "\n".join(memory_claim.source_messages),
                max_chars=memory_claim.max_memory_chars,
                timeout_seconds=20,
            )[: memory_claim.max_memory_chars]
            operations = parse_impression_operations(response)
        except DeepSeekCallError as error:
            self._core.fail_ai_memory_job(
                memory_claim.user_id,
                self._worker_id,
                memory_claim.lease_token,
                error.category,
                self._clock(),
            )
        except ValueError:
            self._core.fail_ai_memory_job(
                memory_claim.user_id,
                self._worker_id,
                memory_claim.lease_token,
                "invalid_response",
                self._clock(),
            )
        else:
            self._core.complete_ai_memory_job(
                memory_claim.user_id,
                self._worker_id,
                memory_claim.lease_token,
                memory_claim.target_message_id,
                operations,
                memory_claim.source_message_count,
                self._clock(),
            )
        return True
