from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from .client import DeepSeekCallError
from .core_client import AICorePort


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
        if claim is None:
            return False
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
