import sys
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from dzmm_bot.runtime.contracts import (
    InboundMessage,
    LoginState,
    MessageReference,
    OutboundMessage,
    WorkerHeartbeat,
)


def test_inbound_message_is_immutable():
    message = InboundMessage("platform-1", "sender-1", "hello", datetime.now(UTC))

    with pytest.raises(FrozenInstanceError):
        message.content = "changed"


def test_inbound_message_preserves_group_defaults_and_direct_provenance():
    now = datetime.now(UTC)

    group = InboundMessage("group-1", "sender-1", "/帮助", now)
    direct = InboundMessage(
        "direct-1",
        "sender-1",
        "/报数 29",
        now,
        source_type="direct",
        chatroom_id="direct-room-1",
    )

    assert (group.source_type, group.chatroom_id) == ("group", None)
    assert (direct.source_type, direct.chatroom_id) == ("direct", "direct-room-1")


def test_inbound_message_preserves_referenced_image_metadata():
    """Fails if a replied image is flattened away before command handling."""
    reference = MessageReference(
        message_id="image-message-1",
        sender_platform_id="image-sender-1",
        content_type="image",
        image_url="https://cdn.example.test/profile.png",
        alt="profile.png",
        width=1254,
        height=1254,
        blurhash="UsK-k9",
    )

    message = InboundMessage(
        "reply-message-1",
        "sender-1",
        "/编辑档案形象",
        datetime.now(UTC),
        reference=reference,
    )

    assert message.reference == reference


def test_outbound_message_has_stable_uuid_and_delivery_defaults():
    outbound = OutboundMessage(inbound_message_id="inbound-1", text="reply")

    assert isinstance(outbound.id, UUID)
    assert outbound.status == "pending"
    assert outbound.lease_worker_id is None
    assert outbound.lease_token is None
    assert outbound.lease_expires_at is None
    assert outbound.attempt_count == 0
    assert outbound.platform_sent_id is None


def test_worker_heartbeat_is_immutable():
    heartbeat = WorkerHeartbeat("worker-1", LoginState.READY, datetime.now(UTC))

    assert heartbeat.listening is True

    with pytest.raises(FrozenInstanceError):
        heartbeat.login_state = LoginState.AUTH_REQUIRED
