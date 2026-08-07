from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from dzmm_bot.runtime.contracts import InboundMessage

from .repository import CoreRepository


class CommandHandler(Protocol):
    def handle(self, message: InboundMessage) -> str | list[str] | None: ...


class NoopCommandHandler:
    def handle(self, message: InboundMessage) -> None:
        return None


@dataclass(frozen=True)
class CommandReply:
    text: str
    recall_after_seconds: int | None = None
    memory_round_id: UUID | None = None


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
            event_message_status = self._repository.record_random_event_round(
                message.sender_platform_id, message.received_at, message.content
            )
            replies: list[CommandReply] = []
            if event_message_status == "observer_invalid":
                replies.append(
                    CommandReply("当前随机事件进行中，旁观请用（内容）或 (内容) 的形式发言。")
                )
            reply = self._command_handler.handle(message)
            if isinstance(reply, list):
                replies.extend(
                    item if isinstance(item, CommandReply) else CommandReply(item)
                    for item in reply
                )
            elif reply is not None:
                replies.append(
                    reply if isinstance(reply, CommandReply) else CommandReply(reply)
                )
            for reply_index, reply in enumerate(replies):
                if (
                    reply.recall_after_seconds is None
                    and reply.memory_round_id is None
                ):
                    self._repository.enqueue_outbound(
                        stored.id, reply.text, reply_index
                    )
                    continue
                self._repository.enqueue_outbound(
                    stored.id,
                    reply.text,
                    reply_index,
                    recall_after_seconds=reply.recall_after_seconds,
                    memory_round_id=reply.memory_round_id,
                )
            return ReceiveResult(stored.id, True)
