from typing import Protocol

from .models import ChatMessage


class MessageSource(Protocol):
    def read_new(self) -> list[ChatMessage]: ...


class MessageSender(Protocol):
    def send(self, message: ChatMessage, text: str) -> bool: ...
