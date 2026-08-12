from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from .client import DeepSeekCallError
from .core_client import AICorePort
from .impressions import parse_impression_operations, render_impression_prompt


class AIMemoryWorker:
    def __init__(
        self,
        worker_id: str,
        core: AICorePort,
        client,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(
            ZoneInfo("Asia/Shanghai")
        ),
        lease_seconds: int = 90,
    ) -> None:
        self._worker_id = worker_id
        self._core = core
        self._client = client
        self._clock = clock
        self._lease_seconds = lease_seconds

    def run_once(self) -> bool:
        claim = self._core.claim_ai_memory_job(
            self._worker_id, self._clock(), self._lease_seconds
        )
        if claim is None:
            return False
        try:
            response = self._client.complete(
                render_impression_prompt(
                    claim.extraction_prompt,
                    stable_entries=[
                        (entry.id, entry.category, entry.content, entry.pinned)
                        for entry in claim.stable_entries
                    ],
                    candidates=[
                        (
                            candidate.id,
                            candidate.category,
                            candidate.content,
                            candidate.support_batches,
                            candidate.conflict_entry_id,
                        )
                        for candidate in claim.candidates
                    ],
                ),
                "\n".join(claim.source_messages),
                max_chars=8000,
                timeout_seconds=60,
            )[:8000]
            operations = parse_impression_operations(response)
            candidate_ids = {candidate.id for candidate in claim.candidates}
            entry_ids = {entry.id for entry in claim.stable_entries}
            operations = tuple(
                operation
                for operation in operations
                if (
                    operation.candidate_id is None
                    or operation.candidate_id in candidate_ids
                )
                and (operation.entry_id is None or operation.entry_id in entry_ids)
            )
        except DeepSeekCallError as error:
            self._core.fail_ai_memory_job(
                claim.user_id,
                self._worker_id,
                claim.lease_token,
                error.category,
                self._clock(),
            )
        except ValueError:
            self._core.fail_ai_memory_job(
                claim.user_id,
                self._worker_id,
                claim.lease_token,
                "invalid_response",
                self._clock(),
            )
        else:
            self._core.complete_ai_memory_job(
                claim.user_id,
                self._worker_id,
                claim.lease_token,
                claim.target_message_id,
                operations,
                claim.source_message_count,
                self._clock(),
            )
        return True
