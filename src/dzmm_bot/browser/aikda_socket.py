from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
import logging
from threading import Event, Lock
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from dzmm_bot.runtime.contracts import DirectChatRoom, InboundMessage


_LOGGER = logging.getLogger(__name__)


class AikdaSocketGateway:

    def __init__(
        self,
        chat_url: str,
        *,
        token_provider: Callable[[], str],
        request: Callable[[str, dict[str, Any] | None], dict[str, Any]],
        cookie_provider: Callable[[], str] | None = None,
        socket_factory: Callable[[], Any] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(ZoneInfo("Asia/Shanghai")),
    ) -> None:
        parsed = urlsplit(chat_url)
        chatroom_id = parse_qs(parsed.query).get("c", [None])[0]
        if not parsed.scheme or not parsed.netloc or not chatroom_id:
            raise ValueError("chat_url must contain an absolute URL with c query parameter")
        self.chatroom_id = chatroom_id
        self._origin = f"{parsed.scheme}://{parsed.netloc}"
        self._token_provider = token_provider
        self._request = request
        self._cookie_provider = cookie_provider
        self._socket_factory = socket_factory or _socket_client
        self._clock = clock
        self._socket = None
        self._bot_id: str | None = None
        self._authenticated = False
        self._joined = Event()
        self._reconcile_needed = True
        self._pending: deque[InboundMessage] = deque()
        self._seen_ids: set[str] = set()
        self._pending_lock = Lock()
        self._message_handler: Callable[[InboundMessage], None] | None = None
        self._direct_chatroom_ids: set[str] = set()
        self._joined_direct_chatroom_ids: set[str] = set()

    def set_message_handler(
        self, handler: Callable[[InboundMessage], None]
    ) -> None:
        self._message_handler = handler

    def read_new(
        self, direct_chatroom_ids: tuple[str, ...] = ()
    ) -> list[InboundMessage]:
        self._ensure_connected()
        self._set_direct_targets(direct_chatroom_ids)
        return self._drain_pending()

    def reconcile_history(
        self, direct_chatroom_ids: tuple[str, ...] = ()
    ) -> list[InboundMessage]:
        self._ensure_connected()
        self._set_direct_targets(direct_chatroom_ids)
        initial_sync = self._reconcile_needed
        recovered = self._reconcile_history(self._clock())
        if recovered and not initial_sync:
            self._invalidate_stale_socket()
        return self._drain_pending()

    def _set_direct_targets(self, direct_chatroom_ids: tuple[str, ...]) -> None:
        targets = set(direct_chatroom_ids)
        if targets != self._direct_chatroom_ids:
            self._direct_chatroom_ids = targets
            self._reconcile_needed = True
        for chatroom_id in direct_chatroom_ids:
            if chatroom_id not in self._joined_direct_chatroom_ids:
                self._join_direct_room(chatroom_id)

    def _drain_pending(self) -> list[InboundMessage]:
        with self._pending_lock:
            messages, self._pending = self._pending, deque()
        return sorted(messages, key=lambda message: message.received_at)

    def _join_direct_room(self, chatroom_id: str) -> None:
        joined = self._socket.call(
            "message:join-room", {"chatroomId": chatroom_id}, timeout=10
        )
        if not joined or joined.get("success") is not True:
            error = joined.get("error", "message room join failed") if joined else "message room join failed"
            raise RuntimeError(error)
        self._joined_direct_chatroom_ids.add(chatroom_id)

    def send(self, text: str) -> str:
        return self.send_to(self.chatroom_id, text)

    def send_to(self, chatroom_id: str, text: str) -> str:
        self._ensure_connected()
        if not chatroom_id:
            raise ValueError("chatroom_id must be nonempty")
        if not text.strip():
            raise ValueError("text must be nonempty")
        message_id = str(uuid4())
        message = {
            "message_id": message_id,
            "sent_by": self._bot_id,
            "chatroom_id": chatroom_id,
            "sent_at": _utc_iso(self._clock()),
            "content": {"type": "text", "text": text},
        }
        if chatroom_id not in self._joined_direct_chatroom_ids:
            self._join_direct_room(chatroom_id)
        acknowledgement = self._socket.call(
            "message:send",
            {"chatroomId": chatroom_id, "message": message},
            timeout=10,
        )
        if not acknowledgement or acknowledgement.get("success") is not True:
            error = acknowledgement.get("error", "message acknowledgement failed") if acknowledgement else "message acknowledgement failed"
            code = acknowledgement.get("code") if acknowledgement else None
            _LOGGER.warning(
                "aikda message:send rejected destination=%s chars=%s lines=%s code=%s error=%s",
                chatroom_id,
                len(text),
                text.count("\n") + 1,
                code or "-",
                error,
            )
            raise RuntimeError(error)
        return message_id

    def discover_direct_chats(self) -> list[DirectChatRoom]:
        self._ensure_connected()
        rooms = self._request("chat.listAll")
        entries = rooms if isinstance(rooms, list) else rooms.get("items", [])
        discovered: list[DirectChatRoom] = []
        seen_users: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            data = entry.get("data")
            if not isinstance(data, dict) or data.get("chatType") != "one_on_one":
                continue
            chatroom_id = data.get("chatroomId")
            if not isinstance(chatroom_id, str) or not chatroom_id:
                continue
            history = self._request("chatroom.getMessages", {"chatroomId": chatroom_id})
            user_id = next(
                (
                    message.get("sent_by")
                    for message in history.get("messages", [])
                    if isinstance(message, dict)
                    and isinstance(message.get("sent_by"), str)
                    and message["sent_by"] != self._bot_id
                ),
                None,
            )
            if user_id is None or user_id in seen_users:
                continue
            seen_users.add(user_id)
            discovered.append(DirectChatRoom(user_id, chatroom_id))
        return discovered

    def retract(self, message_id: str) -> None:
        self._ensure_connected()
        acknowledgement = self._socket.call(
            "message:recall",
            {"chatroomId": self.chatroom_id, "messageId": message_id},
            timeout=10,
        )
        if not acknowledgement or acknowledgement.get("success") is not True:
            error = acknowledgement.get("error", "message retraction acknowledgement failed") if acknowledgement else "message retraction acknowledgement failed"
            raise RuntimeError(error)

    def is_authenticated(self) -> bool:
        try:
            if not self._request("user.getMe").get("id"):
                raise RuntimeError("bot identity unavailable")
            self._ensure_connected()
        except Exception:
            self._authenticated = False
        return self._authenticated

    def close(self) -> None:
        if self._socket is not None:
            self._socket.disconnect()
        self._authenticated = False

    def _ensure_connected(self) -> None:
        if self._socket is not None and self._socket.connected and self._joined.is_set():
            self._authenticated = True
            return
        profile = self._request("user.getMe")
        bot_id = profile.get("id")
        if not bot_id:
            raise RuntimeError("bot identity unavailable")
        token = self._token_provider()
        if not token:
            raise RuntimeError("socket token unavailable")
        self._bot_id = bot_id
        if self._socket is None:
            self._socket = self._socket_factory()
            self._socket.on("message:new", self._on_message)
            self._socket.on("message:joined", self._on_joined)
            self._socket.on("disconnect", self._on_disconnect)
        self._joined.clear()
        cookie = self._cookie_provider() if self._cookie_provider is not None else ""
        connect_options: dict[str, Any] = {
            "socketio_path": "ws/matching",
            "auth": {"token": token},
            "transports": ["websocket", "polling"],
        }
        if cookie:
            connect_options["headers"] = {"Cookie": cookie}
        self._socket.connect(
            self._origin,
            **connect_options,
        )
        if not self._joined.wait(timeout=10):
            self._socket.disconnect()
            raise RuntimeError("socket join timed out")
        self._authenticated = True
        self._reconcile_needed = True

    def _reconcile_history(self, now: datetime) -> bool:
        seen_before = len(self._seen_ids)
        for chatroom_id in (self.chatroom_id, *sorted(self._direct_chatroom_ids)):
            payload = self._request(
                "chatroom.getMessages", {"chatroomId": chatroom_id}
            )
            for message in payload.get("messages", []):
                self._accept_message(chatroom_id, message)
        self._reconcile_needed = False
        return len(self._seen_ids) > seen_before

    def _invalidate_stale_socket(self) -> None:
        self._socket.disconnect()
        self._authenticated = False
        self._joined.clear()
        self._joined_direct_chatroom_ids.clear()
        self._reconcile_needed = True

    def _on_message(self, payload: dict[str, Any]) -> None:
        message = payload.get("message")
        if isinstance(message, dict):
            self._accept_message(payload.get("chatroomId"), message)

    def _on_joined(self, _payload: dict[str, Any] | None = None) -> None:
        self._joined.set()

    def _on_disconnect(self) -> None:
        self._authenticated = False
        self._joined.clear()
        self._joined_direct_chatroom_ids.clear()
        self._reconcile_needed = True

    def _accept_message(self, chatroom_id: str | None, message: dict[str, Any]) -> None:
        if message.get("sent_by") == self._bot_id:
            return
        content = message.get("content")
        message_id = message.get("message_id")
        sent_by = message.get("sent_by")
        sent_at = message.get("sent_at")
        if (
            not isinstance(content, dict)
            or content.get("type") != "text"
            or not isinstance(content.get("text"), str)
            or not isinstance(message_id, str)
            or not isinstance(sent_by, str)
            or not isinstance(sent_at, str)
        ):
            return
        if chatroom_id is None:
            return
        source_type = "group" if chatroom_id == self.chatroom_id else "direct"
        inbound = InboundMessage(
            message_id,
            sent_by,
            content["text"],
            _shanghai_time(sent_at),
            source_type=source_type,
            chatroom_id=chatroom_id,
        )
        with self._pending_lock:
            if message_id in self._seen_ids:
                return
            self._seen_ids.add(message_id)
            handler = self._message_handler
            if handler is None:
                self._pending.append(inbound)
        if handler is not None:
            handler(inbound)


def _socket_client():
    import socketio

    return socketio.Client(reconnection=False)


def _shanghai_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        ZoneInfo("Asia/Shanghai")
    )


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
