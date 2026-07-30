from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMessage:
    message_id: str
    sender: str
    text: str
