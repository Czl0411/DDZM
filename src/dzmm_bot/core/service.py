from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from dzmm_bot.runtime.contracts import InboundMessage

from .ai_mentions import BOT_MENTION_PREFIX, normalize_ai_mention
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
            command_parts = message.content.strip().split(maxsplit=1)
            if command_parts and command_parts[0] == "/甩锅":
                self._repository.lock_gameplay_order()
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
            event_state = self._repository.active_random_event_state()
            if event_state is not None:
                if event_message_status in {"participant", "observer_valid"}:
                    self._repository.record_ai_memory_message(
                        stored.id,
                        message.sender_platform_id,
                        False,
                        message.received_at,
                    )
                    return ReceiveResult(stored.id, True)
                settings = self._repository.get_random_event_settings()
                if not _allows_random_event_command(message.content, event_state, settings):
                    self._repository.record_ai_memory_message(
                        stored.id,
                        message.sender_platform_id,
                        False,
                        message.received_at,
                    )
                    self._repository.enqueue_outbound(
                        stored.id, settings.blocked_message, 0
                    )
                    return ReceiveResult(stored.id, True)
            had_active_game_context = self._repository.user_has_active_game_context(
                message.sender_platform_id
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
            if not replies:
                mention_content = _ai_mention_content(message.content)
                if mention_content is not None:
                    result = self._repository.try_enqueue_ai_request(
                        stored.id,
                        message.sender_platform_id,
                        mention_content,
                        message.received_at,
                    )
                    if result.state == "not_joined":
                        replies.append(CommandReply("请先用 /入职 名字 加入摸鱼公司。"))
                    elif result.state == "over_limit":
                        replies.append(
                            CommandReply(
                                self._repository.get_ai_assistant_settings().over_limit_reply
                            )
                        )
            eligible = (
                bool(message.content.strip())
                and not message.content.lstrip().startswith(("/", "(", "（"))
                and event_message_status == "none"
                and not had_active_game_context
                and not self._repository.user_has_active_game_context(
                    message.sender_platform_id
                )
            )
            self._repository.record_ai_memory_message(
                stored.id,
                message.sender_platform_id,
                eligible,
                message.received_at,
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


def _allows_random_event_command(content: str, event_state: str, settings) -> bool:
    parts = content.strip().split(maxsplit=1)
    if not parts:
        return False
    command = {
        "/me": "/我",
        "/开始摸鱼躲藏": "/摸鱼躲猫猫",
        "/躲": "/摸鱼躲猫猫",
    }.get(parts[0], parts[0])
    allowed = (
        settings.signup_allowed_commands
        if event_state == "signup"
        else settings.in_progress_allowed_commands
    )
    return command in allowed


def _ai_mention_content(content: str) -> str | None:
    if not content.startswith(BOT_MENTION_PREFIX):
        return None
    value = normalize_ai_mention(content)
    return value or None
