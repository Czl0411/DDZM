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
            memory_text = self._client.complete(
                _memory_system_prompt(memory_claim.extraction_prompt, memory_claim.current_memory),
                "\n".join(memory_claim.source_messages),
                max_chars=memory_claim.max_memory_chars,
                timeout_seconds=20,
            )[: memory_claim.max_memory_chars]
        except DeepSeekCallError as error:
            self._core.fail_ai_memory_job(
                memory_claim.user_id,
                self._worker_id,
                memory_claim.lease_token,
                error.category,
                self._clock(),
            )
        else:
            self._core.complete_ai_memory_job(
                memory_claim.user_id,
                self._worker_id,
                memory_claim.lease_token,
                memory_claim.target_message_id,
                memory_text,
                self._clock(),
            )
        return True


def _memory_system_prompt(extraction_prompt: str, current_memory: str) -> str:
    return "\n\n".join(
        (
            extraction_prompt.strip(),
            "仅输出完整的最新版玩家记忆正文；若没有稳定信息，输出空文本。",
            f"已有记忆：{current_memory.strip() or '无'}",
        )
    )
