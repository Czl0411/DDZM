import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

import httpx

from dzmm_bot.runtime.contracts import DirectChatRoom, InboundMessage, LoginState


@dataclass(frozen=True)
class OutboundClaim:
    id: UUID
    inbound_message_id: str | None
    text: str
    lease_token: UUID
    destination_chatroom_id: str | None = None
    delivery_kind: str = "group"
    recall_after_seconds: int | None = None


@dataclass(frozen=True)
class OutboundRecallClaim:
    id: UUID
    platform_sent_id: str
    lease_token: UUID


@dataclass(frozen=True)
class WorkerCommand:
    id: UUID
    command: str
    lease_token: UUID


class CorePort(Protocol):
    def submit_inbound(self, message: InboundMessage) -> None: ...

    def run_daily_jobs(self, now: datetime) -> None: ...

    def sync_direct_chats(self, rooms: list[DirectChatRoom], now: datetime) -> None: ...

    def direct_inbound_chatroom_ids(self) -> tuple[str, ...]: ...

    def claim_outbound(
        self, worker_id: str, now: datetime, lease_seconds: int
    ) -> OutboundClaim | None: ...

    def confirm_sent(
        self,
        message_id: UUID,
        worker_id: str,
        lease_token: UUID,
        platform_sent_id: str,
        now: datetime,
    ) -> None: ...

    def mark_outbound_failed(
        self,
        message_id: UUID,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
    ) -> None: ...

    def release_outbound(
        self,
        message_id: UUID,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
    ) -> None: ...

    def claim_outbound_recall(
        self, worker_id: str, now: datetime, lease_seconds: int
    ) -> OutboundRecallClaim | None: ...

    def confirm_outbound_recalled(
        self,
        message_id: UUID,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
    ) -> None: ...

    def heartbeat(
        self,
        worker_id: str,
        login_state: LoginState,
        listening: bool,
        recorded_at: datetime,
    ) -> bool: ...

    def claim_command(
        self, worker_id: str, now: datetime, lease_seconds: int
    ) -> WorkerCommand | None: ...

    def complete_command(
        self,
        command_id: UUID,
        worker_id: str,
        lease_token: UUID,
        status: str,
        now: datetime,
    ) -> None: ...

    def record_audit(
        self, event_type: str, worker_id: str, recorded_at: datetime
    ) -> None: ...


class CoreClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            base_url=base_url,
            headers={"X-Core-Token": token},
            timeout=10,
        )
        self._logger = logging.getLogger(__name__)

    def submit_inbound(self, message: InboundMessage) -> None:
        reference = message.reference
        payload = {
            "platform_message_id": message.platform_message_id,
            "sender_platform_id": message.sender_platform_id,
            "content": message.content,
            "received_at": message.received_at.isoformat(),
            "source_type": message.source_type,
            "chatroom_id": message.chatroom_id,
        }
        if reference is not None:
            payload["reference"] = {
                "message_id": reference.message_id,
                "sender_platform_id": reference.sender_platform_id,
                "content_type": reference.content_type,
                "image_url": reference.image_url,
                "alt": reference.alt,
                "width": reference.width,
                "height": reference.height,
                "blurhash": reference.blurhash,
            }
        self._post(
            "/internal/inbound",
            payload,
        )

    def run_daily_jobs(self, now: datetime) -> None:
        self._post("/internal/daily-jobs/run", {"now": now.isoformat()})

    def sync_direct_chats(self, rooms: list[DirectChatRoom], now: datetime) -> None:
        self._post(
            "/internal/direct-chats/sync",
            {
                "rooms": [
                    {
                        "platform_user_id": room.platform_user_id,
                        "chatroom_id": room.chatroom_id,
                    }
                    for room in rooms
                ],
                "now": now.isoformat(),
            },
        )

    def direct_inbound_chatroom_ids(self) -> tuple[str, ...]:
        data = self._get("/internal/direct-inbound/rooms")
        return tuple(data["chatroom_ids"])

    def claim_outbound(
        self, worker_id: str, now: datetime, lease_seconds: int
    ) -> OutboundClaim | None:
        data = self._post(
            "/internal/outbound/claim",
            _claim_payload(worker_id, now, lease_seconds),
        )
        if data is None:
            return None
        return OutboundClaim(
            id=UUID(data["id"]),
            inbound_message_id=data["inbound_message_id"],
            text=data["text"],
            lease_token=UUID(data["lease_token"]),
            destination_chatroom_id=data["destination_chatroom_id"],
            delivery_kind=data["delivery_kind"],
            recall_after_seconds=data["recall_after_seconds"],
        )

    def confirm_sent(
        self,
        message_id: UUID,
        worker_id: str,
        lease_token: UUID,
        platform_sent_id: str,
        now: datetime,
    ) -> None:
        self._post(
            f"/internal/outbound/{message_id}/sent",
            {
                "worker_id": worker_id,
                "lease_token": str(lease_token),
                "platform_sent_id": platform_sent_id,
                "now": now.isoformat(),
            },
        )

    def mark_outbound_failed(
        self,
        message_id: UUID,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
    ) -> None:
        self._post(
            f"/internal/outbound/{message_id}/failed",
            {
                "worker_id": worker_id,
                "lease_token": str(lease_token),
                "now": now.isoformat(),
            },
        )

    def release_outbound(
        self,
        message_id: UUID,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
    ) -> None:
        self._post(
            f"/internal/outbound/{message_id}/retry",
            {
                "worker_id": worker_id,
                "lease_token": str(lease_token),
                "now": now.isoformat(),
            },
        )

    def claim_outbound_recall(
        self, worker_id: str, now: datetime, lease_seconds: int
    ) -> OutboundRecallClaim | None:
        data = self._post(
            "/internal/outbound/recall/claim",
            _claim_payload(worker_id, now, lease_seconds),
        )
        if data is None:
            return None
        return OutboundRecallClaim(
            id=UUID(data["id"]),
            platform_sent_id=data["platform_sent_id"],
            lease_token=UUID(data["lease_token"]),
        )

    def confirm_outbound_recalled(
        self,
        message_id: UUID,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
    ) -> None:
        self._post(
            f"/internal/outbound/{message_id}/recalled",
            {
                "worker_id": worker_id,
                "lease_token": str(lease_token),
                "now": now.isoformat(),
            },
        )

    def heartbeat(
        self,
        worker_id: str,
        login_state: LoginState,
        listening: bool,
        recorded_at: datetime,
    ) -> bool:
        response = self._post(
            "/internal/heartbeat",
            {
                "worker_id": worker_id,
                "login_state": login_state.value,
                "listening": listening,
                "recorded_at": recorded_at.isoformat(),
            },
        )
        return bool(response["listening_desired"])

    def claim_command(
        self, worker_id: str, now: datetime, lease_seconds: int
    ) -> WorkerCommand | None:
        data = self._post(
            "/internal/worker-commands/claim",
            _claim_payload(worker_id, now, lease_seconds),
        )
        if data is None:
            return None
        return WorkerCommand(
            id=UUID(data["id"]),
            command=data["command"],
            lease_token=UUID(data["lease_token"]),
        )

    def complete_command(
        self,
        command_id: UUID,
        worker_id: str,
        lease_token: UUID,
        status: str,
        now: datetime,
    ) -> None:
        self._post(
            f"/internal/worker-commands/{command_id}/complete",
            {
                "worker_id": worker_id,
                "lease_token": str(lease_token),
                "status": status,
                "now": now.isoformat(),
            },
        )

    def record_audit(
        self, event_type: str, worker_id: str, recorded_at: datetime
    ) -> None:
        self._logger.warning(
            "browser audit event=%s worker_id=%s recorded_at=%s",
            event_type,
            worker_id,
            recorded_at.isoformat(),
        )

    def _post(self, path: str, payload: dict):
        response = self._client.post(path, json=payload)
        response.raise_for_status()
        return response.json()

    def _get(self, path: str):
        response = self._client.get(path)
        response.raise_for_status()
        return response.json()


def _claim_payload(worker_id: str, now: datetime, lease_seconds: int) -> dict:
    return {
        "worker_id": worker_id,
        "now": now.isoformat(),
        "lease_seconds": lease_seconds,
    }
