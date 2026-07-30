from typing import Protocol

from .models import ChatMessage


class MessageSource(Protocol):
    def read_new(self) -> list[ChatMessage]: ...


class MessageSender(Protocol):
    def send(self, message: ChatMessage, text: str) -> bool: ...


class SeenMessageStore(Protocol):
    def claim(self, message_id: str) -> str | None: ...

    def mark_seen(self, message_id: str, claim_token: str) -> bool: ...

    def release_claim(self, message_id: str, claim_token: str) -> None: ...
