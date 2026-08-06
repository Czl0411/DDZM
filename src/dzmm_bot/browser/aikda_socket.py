from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import Event, Lock
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from dzmm_bot.runtime.contracts import InboundMessage


class AikdaSocketGateway:
    _HISTORY_SYNC_INTERVAL = timedelta(seconds=5)

    def __init__(
        self,
        chat_url: str,
        *,
        token_provider: Callable[[], str],
        request: Callable[[str, dict[str, Any] | None], dict[str, Any]],
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
        self._socket_factory = socket_factory or _socket_client
        self._clock = clock
        self._socket = None
        self._bot_id: str | None = None
        self._authenticated = False
        self._joined = Event()
        self._reconcile_needed = True
        self._last_history_sync_at: datetime | None = None
        self._pending: deque[InboundMessage] = deque()
        self._seen_ids: set[str] = set()
        self._pending_lock = Lock()

    def read_new(self) -> list[InboundMessage]:
        self._ensure_connected()
        now = self._clock()
        initial_sync = self._reconcile_needed
        if initial_sync or self._history_sync_due(now):
            recovered = self._reconcile_history(now)
            if recovered and not initial_sync:
                self._invalidate_stale_socket()
        with self._pending_lock:
            messages, self._pending = self._pending, deque()
        return sorted(messages, key=lambda message: message.received_at)

    def send(self, text: str) -> str:
        self._ensure_connected()
        if not text.strip():
            raise ValueError("text must be nonempty")
        message_id = str(uuid4())
        message = {
            "message_id": message_id,
            "sent_by": self._bot_id,
            "chatroom_id": self.chatroom_id,
            "sent_at": _utc_iso(self._clock()),
            "content": {"type": "text", "text": text},
        }
        acknowledgement = self._socket.call(
            "message:send",
            {"chatroomId": self.chatroom_id, "message": message},
            timeout=10,
        )
        if not acknowledgement or acknowledgement.get("success") is not True:
            error = acknowledgement.get("error", "message acknowledgement failed") if acknowledgement else "message acknowledgement failed"
            raise RuntimeError(error)
        return message_id

    def retract(self, message_id: str) -> None:
        self._ensure_connected()
        acknowledgement = self._socket.call(
            "message:delete",
            {"chatroomId": self.chatroom_id, "messageId": message_id},
            timeout=10,
        )
        if not acknowledgement or acknowledgement.get("success") is not True:
            error = acknowledgement.get("error", "message retraction acknowledgement failed") if acknowledgement else "message retraction acknowledgement failed"
            raise RuntimeError(error)

    def is_authenticated(self) -> bool:
        try:
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
        self._socket.connect(
            self._origin,
            socketio_path="ws/matching",
            auth={"token": token},
            transports=["websocket", "polling"],
        )
        if not self._joined.wait(timeout=10):
            self._socket.disconnect()
            raise RuntimeError("socket join timed out")
        self._authenticated = True
        self._reconcile_needed = True

    def _history_sync_due(self, now: datetime) -> bool:
        return (
            self._last_history_sync_at is None
            or now - self._last_history_sync_at >= self._HISTORY_SYNC_INTERVAL
        )

    def _reconcile_history(self, now: datetime) -> bool:
        seen_before = len(self._seen_ids)
        payload = self._request("chatroom.getMessages", {"chatroomId": self.chatroom_id})
        for message in payload.get("messages", []):
            self._accept_message(self.chatroom_id, message)
        self._reconcile_needed = False
        self._last_history_sync_at = now
        return len(self._seen_ids) > seen_before

    def _invalidate_stale_socket(self) -> None:
        self._socket.disconnect()
        self._authenticated = False
        self._joined.clear()
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
        self._reconcile_needed = True

    def _accept_message(self, chatroom_id: str | None, message: dict[str, Any]) -> None:
        if chatroom_id != self.chatroom_id or message.get("sent_by") == self._bot_id:
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
        inbound = InboundMessage(
            message_id,
            sent_by,
            content["text"],
            _shanghai_time(sent_at),
        )
        with self._pending_lock:
            if message_id in self._seen_ids:
                return
            self._seen_ids.add(message_id)
            self._pending.append(inbound)


def _socket_client():
    import socketio

    return socketio.Client(reconnection=False)


def _shanghai_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        ZoneInfo("Asia/Shanghai")
    )


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
