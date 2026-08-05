from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from dzmm_bot.runtime.contracts import InboundMessage

from .repository import CoreRepository


class CommandHandler(Protocol):
    def handle(self, message: InboundMessage) -> str | None: ...


class NoopCommandHandler:
    def handle(self, message: InboundMessage) -> None:
        return None


@dataclass(frozen=True)
class ReceiveResult:
    message_id: UUID
    inserted: bool


class CoreService:
    def __init__(
        self,
        repository: CoreRepository,
        command_handler: CommandHandler | None = None,
    ) -> None:
        self._repository = repository
        self._command_handler = command_handler or NoopCommandHandler()

    def receive_inbound(self, message: InboundMessage) -> ReceiveResult:
        with self._repository.transaction():
            stored, inserted = self._repository.accept_inbound(message)
            if not inserted:
                return ReceiveResult(stored.id, False)
            self._repository.record_activity(
                message.sender_platform_id, message.received_at, message.content
            )
            reply = self._command_handler.handle(message)
            if reply is not None:
                self._repository.enqueue_outbound(stored.id, reply)
            return ReceiveResult(stored.id, True)
