from collections import deque
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from dzmm_bot.browser.aikda_socket import AikdaSocketGateway, _socket_client
from dzmm_bot.runtime.contracts import DirectChatRoom, InboundMessage


NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
TARGET_URL = "https://www.aikda.com/chat?c=room-1"


class FakeSocket:
    def __init__(self):
        self.handlers = {}
        self.connected = False
        self.joined = False
        self.connect_calls = []
        self.call_result = {"success": True}
        self.calls = []
        self.message_after_join = None
        self.joined_payload = {"syncMode": "http"}

    def on(self, event, handler):
        self.handlers[event] = handler

    def connect(self, origin, **kwargs):
        self.connect_calls.append((origin, kwargs))
        self.connected = True
        handler = self.handlers.get("message:joined")
        if handler is not None:
            if self.joined_payload is None:
                handler()
            else:
                handler(self.joined_payload)
            self.joined = True
        if self.message_after_join is not None:
            self.handlers["message:new"](self.message_after_join)

    def call(self, event, payload, timeout):
        if not self.joined:
            raise RuntimeError("server join was not completed")
        self.calls.append((event, payload, timeout))
        return self.call_result

    def disconnect(self):
        self.connected = False

    def trigger(self, event, payload):
        self.handlers[event](payload)


class FakeRequest:
    def __init__(self, messages=None):
        self.messages = messages or []
        self.calls = []
        self.profile = {"id": "bot-1"}

    def __call__(self, procedure, payload=None):
        self.calls.append((procedure, payload))
        if procedure == "user.getMe":
            return self.profile
        if procedure == "chat.listAll":
            return {"items": []}
        if procedure == "chatroom.getMessages":
            return {"messages": self.messages}
        raise AssertionError(f"unexpected procedure {procedure}")


def message(message_id, sent_by, text, sent_at="2026-08-05T04:00:00Z"):
    return {
        "message_id": message_id,
        "sent_by": sent_by,
        "sent_at": sent_at,
        "content": {"type": "text", "text": text},
    }


@pytest.fixture
def gateway():
    socket = FakeSocket()
    request = FakeRequest()
    gateway = AikdaSocketGateway(
        TARGET_URL,
        token_provider=lambda: "short-lived-token",
        request=request,
        socket_factory=lambda: socket,
        clock=lambda: NOW,
    )
    return gateway, socket, request


def test_live_target_room_text_event_is_read_once(gateway):
    """Fails if the event handler does not retain a target-room text message."""
    adapter, socket, _ = gateway
    assert adapter.read_new() == []

    socket.trigger(
        "message:new",
        {"chatroomId": "room-1", "message": message("m-1", "u-1", "/余额")},
    )

    assert adapter.read_new() == [
        InboundMessage(
            "m-1",
            "u-1",
            "/余额",
            datetime(2026, 8, 5, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
    ]
    assert adapter.read_new() == []


def test_self_and_other_room_events_are_ignored(gateway):
    """Fails if the bot replies to itself or another room's traffic."""
    adapter, socket, _ = gateway
    adapter.read_new()

    socket.trigger(
        "message:new",
        {"chatroomId": "room-1", "message": message("m-self", "bot-1", "/余额")},
    )
    socket.trigger(
        "message:new",
        {"chatroomId": "room-2", "message": message("m-other", "u-1", "/余额")},
    )

    assert adapter.read_new() == []


def test_self_message_arriving_during_connection_is_ignored(gateway):
    """Fails if identity is unavailable while the initial socket event arrives."""
    adapter, socket, _ = gateway
    socket.message_after_join = {
        "chatroomId": "room-1",
        "message": message("m-self", "bot-1", "/余额"),
    }

    assert adapter.read_new() == []


def test_history_reconciles_unseen_text_messages_in_timestamp_order():
    """Fails if reconnect history is ignored or returned in API order."""
    socket = FakeSocket()
    request = FakeRequest(
        [
            message("m-2", "u-2", "/打卡", "2026-08-05T04:00:01Z"),
            message("m-1", "u-1", "/余额", "2026-08-05T04:00:00Z"),
        ]
    )
    adapter = AikdaSocketGateway(
        TARGET_URL,
        token_provider=lambda: "short-lived-token",
        request=request,
        socket_factory=lambda: socket,
        clock=lambda: NOW,
    )

    assert [item.platform_message_id for item in adapter.read_new()] == ["m-1", "m-2"]


def test_history_recovers_a_message_when_a_connected_socket_stops_emitting_events():
    """Fails until connected-but-stale sockets periodically reconcile history."""
    now = [NOW]
    socket = FakeSocket()
    request = FakeRequest()
    adapter = AikdaSocketGateway(
        TARGET_URL,
        token_provider=lambda: "short-lived-token",
        request=request,
        socket_factory=lambda: socket,
        clock=lambda: now[0],
    )

    assert adapter.read_new() == []
    request.messages = [message("m-missed", "u-1", "/帮助")]
    now[0] += timedelta(seconds=5)

    assert [item.platform_message_id for item in adapter.read_new()] == ["m-missed"]


def test_history_recovery_reconnects_a_stale_socket_before_the_next_poll():
    """Fails until a missed live event invalidates the stale subscription."""
    now = [NOW]
    socket = FakeSocket()
    request = FakeRequest()
    adapter = AikdaSocketGateway(
        TARGET_URL,
        token_provider=lambda: "short-lived-token",
        request=request,
        socket_factory=lambda: socket,
        clock=lambda: now[0],
    )

    adapter.read_new()
    request.messages = [message("m-missed", "u-1", "/帮助")]
    now[0] += timedelta(seconds=5)
    adapter.read_new()
    adapter.read_new()

    assert len(socket.connect_calls) == 2


def test_send_requires_successful_ack(gateway):
    """Fails if a send is reported before Aikda acknowledges it."""
    adapter, socket, _ = gateway

    platform_message_id = adapter.send("余额：5 摸鱼币")

    assert platform_message_id == socket.calls[0][1]["message"]["message_id"]
    assert socket.calls == [
        (
            "message:send",
            {
                "chatroomId": "room-1",
                "message": {
                    "message_id": platform_message_id,
                    "sent_by": "bot-1",
                    "chatroom_id": "room-1",
                    "sent_at": "2026-08-05T12:00:00Z",
                    "content": {"type": "text", "text": "余额：5 摸鱼币"},
                },
            },
            10,
        )
    ]


def test_send_waits_for_server_join_before_emitting(gateway):
    """Fails if the gateway sends before Aikda marks the socket joined."""
    adapter, socket, _ = gateway

    adapter.send("余额：5 摸鱼币")

    assert socket.joined is True


def test_gateway_discovers_only_direct_rooms_from_non_bot_history(gateway):
    """Fails if group rooms or bot messages are considered employee direct chats."""
    adapter, _, request = gateway
    request.direct_rooms = [
        {"data": {"chatroomId": "group-1", "chatType": "group"}},
        {"data": {"chatroomId": "direct-1", "chatType": "one_on_one"}},
        {"data": {"chatroomId": "direct-empty", "chatType": "one_on_one"}},
    ]

    def direct_request(procedure, payload=None):
        request.calls.append((procedure, payload))
        if procedure == "user.getMe":
            return request.profile
        if procedure == "chat.listAll":
            return request.direct_rooms
        if procedure == "chatroom.getMessages":
            if payload["chatroomId"] == "direct-1":
                return {"messages": [message("own", "bot-1", "已读"), message("dm", "employee-1", "你好")]}
            return {"messages": [message("own-2", "bot-1", "已读")]}
        raise AssertionError(f"unexpected procedure {procedure}")

    adapter._request = direct_request

    assert adapter.discover_direct_chats() == [
        DirectChatRoom(platform_user_id="employee-1", chatroom_id="direct-1")
    ]


def test_send_to_uses_the_supplied_direct_chatroom(gateway):
    """Fails if direct card messages are accidentally sent into the configured group."""
    adapter, socket, _ = gateway

    platform_message_id = adapter.send_to("direct-1", "你的身份：平民。词语：咖啡")

    assert socket.calls == [
        (
            "message:send",
            {
                "chatroomId": "direct-1",
                "message": {
                    "message_id": platform_message_id,
                    "sent_by": "bot-1",
                    "chatroom_id": "direct-1",
                    "sent_at": "2026-08-05T12:00:00Z",
                    "content": {"type": "text", "text": "你的身份：平民。词语：咖啡"},
                },
            },
            10,
        )
    ]


def test_joined_event_without_payload_marks_the_gateway_ready(gateway):
    """Fails for Aikda's real zero-argument message:joined event signature."""
    adapter, socket, _ = gateway
    socket.joined_payload = None

    assert adapter.read_new() == []
    assert adapter.is_authenticated()


def test_authentication_is_lost_when_the_platform_identity_is_unavailable():
    """Fails if a stale socket keeps reporting ready after token expiry."""
    socket = FakeSocket()
    request = FakeRequest()
    adapter = AikdaSocketGateway(
        TARGET_URL,
        token_provider=lambda: "short-lived-token",
        request=request,
        socket_factory=lambda: socket,
        clock=lambda: NOW,
    )

    assert adapter.is_authenticated() is True
    request.profile = {}

    assert adapter.is_authenticated() is False


def test_send_raises_when_ack_rejects_message(gateway):
    """Fails if an Aikda rejection is incorrectly confirmed as delivered."""
    adapter, socket, _ = gateway
    socket.call_result = {"success": False, "error": "rejected"}

    with pytest.raises(RuntimeError, match="rejected"):
        adapter.send("余额：5 摸鱼币")


def test_send_rejection_logs_shape_without_logging_message_text(gateway, caplog):
    """Fails until a rejected outbound ACK carries safe diagnostic context."""
    adapter, socket, _ = gateway
    socket.call_result = {
        "success": False,
        "error": "请勿发送重复内容",
        "code": "content_rejected",
    }

    with pytest.raises(RuntimeError, match="请勿发送重复内容"):
        adapter.send("唯一测试甲\n唯一测试乙")

    assert "destination=room-1 chars=11 lines=2" in caplog.text
    assert "code=content_rejected" in caplog.text
    assert "唯一测试甲" not in caplog.text


def test_retracts_an_acknowledged_message_in_the_target_chatroom(gateway):
    """Fails until a sent message can be withdrawn through the live gateway."""
    adapter, socket, _ = gateway

    adapter.retract("outbound-1")

    assert socket.calls == [
        (
            "message:recall",
            {"chatroomId": "room-1", "messageId": "outbound-1"},
            10,
        )
    ]


def test_socket_client_defers_reconnection_until_a_fresh_token_is_available():
    """Fails if the Socket.IO client retries with an expired connection token."""
    assert _socket_client().reconnection is False


def test_reconnect_acquires_a_fresh_token(gateway):
    """Fails if a disconnected session reuses its previous short-lived token."""
    adapter, socket, _ = gateway
    issued_tokens = []
    adapter._token_provider = lambda: issued_tokens.append("fresh-token") or "fresh-token"

    adapter.read_new()
    socket.connected = False
    adapter.read_new()

    assert issued_tokens == ["fresh-token", "fresh-token"]
    assert len(socket.connect_calls) == 2


def test_live_event_arriving_while_pending_messages_are_read_is_retained(gateway):
    """Fails if clearing the read queue discards a concurrently received event."""
    adapter, socket, _ = gateway
    adapter.read_new()

    class RaceQueue(deque):
        def __init__(self):
            super().__init__()
            self.triggered = False

        def __iter__(self):
            yield from tuple(super().__iter__())
            if not self.triggered:
                self.triggered = True
                socket.trigger(
                    "message:new",
                    {"chatroomId": "room-1", "message": message("m-race", "u-1", "/余额")},
                )

    adapter._pending = RaceQueue()

    assert adapter.read_new() == []
    assert [item.platform_message_id for item in adapter.read_new()] == ["m-race"]
