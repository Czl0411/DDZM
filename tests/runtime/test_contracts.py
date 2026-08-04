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
    OutboundMessage,
    WorkerHeartbeat,
)


def test_inbound_message_is_immutable():
    message = InboundMessage("platform-1", "sender-1", "hello", datetime.now(UTC))

    with pytest.raises(FrozenInstanceError):
        message.content = "changed"


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

    with pytest.raises(FrozenInstanceError):
        heartbeat.login_state = LoginState.AUTH_REQUIRED
