from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

import httpx


@dataclass(frozen=True)
class AIClaim:
    id: UUID
    lease_token: UUID
    system_prompt: str
    user_content: str
    max_response_chars: int
    timeout_seconds: int


class AICorePort(Protocol):
    def claim_ai_request(
        self, worker_id: str, now: datetime, lease_seconds: int
    ) -> AIClaim | None: ...

    def complete_ai_request(
        self,
        request_id: UUID,
        worker_id: str,
        lease_token: UUID,
        text: str,
        now: datetime,
    ) -> None: ...

    def fail_ai_request(
        self,
        request_id: UUID,
        worker_id: str,
        lease_token: UUID,
        failure_summary: str,
        now: datetime,
    ) -> None: ...


class AICoreClient:
    def __init__(
        self, base_url: str, token: str, *, client: httpx.Client | None = None
    ) -> None:
        self._client = client or httpx.Client(
            base_url=base_url,
            headers={"X-Core-Token": token},
            timeout=10,
        )

    def claim_ai_request(
        self, worker_id: str, now: datetime, lease_seconds: int
    ) -> AIClaim | None:
        data = self._post(
            "/internal/ai/claim",
            {
                "worker_id": worker_id,
                "now": now.isoformat(),
                "lease_seconds": lease_seconds,
            },
        )
        if data is None:
            return None
        return AIClaim(
            id=UUID(data["id"]),
            lease_token=UUID(data["lease_token"]),
            system_prompt=data["system_prompt"],
            user_content=data["user_content"],
            max_response_chars=data["max_response_chars"],
            timeout_seconds=data["timeout_seconds"],
        )

    def complete_ai_request(
        self,
        request_id: UUID,
        worker_id: str,
        lease_token: UUID,
        text: str,
        now: datetime,
    ) -> None:
        self._post(
            f"/internal/ai/{request_id}/completed",
            {
                "worker_id": worker_id,
                "lease_token": str(lease_token),
                "text": text,
                "now": now.isoformat(),
            },
        )

    def fail_ai_request(
        self,
        request_id: UUID,
        worker_id: str,
        lease_token: UUID,
        failure_summary: str,
        now: datetime,
    ) -> None:
        self._post(
            f"/internal/ai/{request_id}/failed",
            {
                "worker_id": worker_id,
                "lease_token": str(lease_token),
                "failure_summary": failure_summary,
                "now": now.isoformat(),
            },
        )

    def _post(self, path: str, payload: dict):
        response = self._client.post(path, json=payload)
        response.raise_for_status()
        return response.json()
