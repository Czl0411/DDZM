from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4


class LoginState(StrEnum):
    READY = "ready"
    AUTH_REQUIRED = "auth_required"
    AUTH_IN_PROGRESS = "auth_in_progress"


@dataclass(frozen=True)
class InboundMessage:
    platform_message_id: str
    sender_platform_id: str
    content: str
    received_at: datetime


@dataclass(frozen=True)
class DirectChatRoom:
    platform_user_id: str
    chatroom_id: str


@dataclass(frozen=True)
class OutboundMessage:
    inbound_message_id: str
    text: str
    id: UUID = field(default_factory=uuid4)
    status: str = "pending"
    lease_worker_id: str | None = None
    lease_token: UUID | None = None
    lease_expires_at: datetime | None = None
    attempt_count: int = 0
    platform_sent_id: str | None = None
    destination_chatroom_id: str | None = None
    delivery_kind: str = "group"


@dataclass(frozen=True)
class WorkerHeartbeat:
    worker_id: str
    login_state: LoginState
    recorded_at: datetime
