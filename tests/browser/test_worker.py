from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import pytest

from dzmm_bot.browser.core_client import OutboundClaim, OutboundRecallClaim, WorkerCommand
from dzmm_bot.browser.worker import BrowserWorker
from dzmm_bot.runtime.contracts import InboundMessage, LoginState


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
LEASE = UUID("00000000-0000-0000-0000-000000000001")
OUTBOUND_ID = UUID("00000000-0000-0000-0000-000000000002")
COMMAND_ID = UUID("00000000-0000-0000-0000-000000000003")


@dataclass
class FakeGateway:
    messages: list[InboundMessage] = field(default_factory=list)
    authenticated: bool = True
    sent: list[str] = field(default_factory=list)
    retracted: list[str] = field(default_factory=list)
    send_error: Exception | None = None
    read_error: Exception | None = None

    def read_new(self):
        if self.read_error:
            raise self.read_error
        return list(self.messages)

    def send(self, text):
        if self.send_error:
            raise self.send_error
        self.sent.append(text)
        return f"sent-{len(self.sent)}"

    def is_authenticated(self):
        return self.authenticated

    def retract(self, message_id):
        self.retracted.append(message_id)

    def close(self):
        pass


@dataclass
class FakeSession:
    gateway: FakeGateway
    starts: int = 0
    stops: int = 0

    def start_headless(self):
        self.starts += 1
        return self.gateway

    def attach_existing(self):
        self.starts += 1
        return self.gateway

    def stop(self):
        self.stops += 1

    def login_state(self):
        return LoginState.READY if self.gateway.authenticated else LoginState.AUTH_REQUIRED


@dataclass
class FakeDesktop:
    starts: int = 0
    stops: int = 0

    def start(self):
        self.starts += 1

    def stop(self):
        self.stops += 1


@dataclass
class FakeCore:
    pending: list[OutboundClaim] = field(default_factory=list)
    pending_recalls: list[OutboundRecallClaim] = field(default_factory=list)
    commands: list[WorkerCommand] = field(default_factory=list)
    submitted_ids: list[str] = field(default_factory=list)
    confirmed: list[tuple] = field(default_factory=list)
    failed: list[tuple] = field(default_factory=list)
    recalls_confirmed: list[tuple] = field(default_factory=list)
    heartbeats: list[tuple] = field(default_factory=list)
    completions: list[tuple] = field(default_factory=list)
    audits: list[tuple] = field(default_factory=list)
    daily_job_times: list[datetime] = field(default_factory=list)

    def submit_inbound(self, message):
        self.submitted_ids.append(message.platform_message_id)

    def claim_outbound(self, worker_id, now, lease_seconds):
        return self.pending.pop(0) if self.pending else None

    def confirm_sent(self, message_id, worker_id, lease_token, platform_sent_id, now):
        self.confirmed.append(
            (message_id, worker_id, lease_token, platform_sent_id, now)
        )

    def mark_outbound_failed(self, message_id, worker_id, lease_token, now):
        self.failed.append((message_id, worker_id, lease_token, now))

    def claim_outbound_recall(self, worker_id, now, lease_seconds):
        return self.pending_recalls.pop(0) if self.pending_recalls else None

    def confirm_outbound_recalled(self, message_id, worker_id, lease_token, now):
        self.recalls_confirmed.append((message_id, worker_id, lease_token, now))

    def heartbeat(self, worker_id, login_state, recorded_at):
        self.heartbeats.append((worker_id, login_state, recorded_at))

    def claim_command(self, worker_id, now, lease_seconds):
        return self.commands.pop(0) if self.commands else None

    def complete_command(self, command_id, worker_id, lease_token, status, now):
        self.completions.append(
            (command_id, worker_id, lease_token, status, now)
        )

    def record_audit(self, event_type, worker_id, recorded_at):
        self.audits.append((event_type, worker_id, recorded_at))

    def run_daily_jobs(self, now):
        self.daily_job_times.append(now)


@pytest.fixture
def context():
    gateway = FakeGateway()
    session = FakeSession(gateway)
    desktop = FakeDesktop()
    core = FakeCore()
    sleeps = []
    worker = BrowserWorker(
        worker_id="worker-a",
        core=core,
        session=session,
        desktop=desktop,
        clock=lambda: NOW,
        sleep=sleeps.append,
    )
    return worker, gateway, session, desktop, core, sleeps


def test_worker_submits_each_platform_message_once(context):
    worker, gateway, _, _, core, _ = context
    gateway.messages = [InboundMessage("p-1", "u-1", "/test", NOW)]

    worker.run_once()
    worker.run_once()

    assert core.submitted_ids == ["p-1"]


def test_worker_runs_daily_jobs_after_submitting_messages(context):
    worker, gateway, _, _, core, _ = context
    gateway.messages = [InboundMessage("p-1", "u-1", "普通消息", NOW)]

    worker.run_once()

    assert core.submitted_ids == ["p-1"]
    assert core.daily_job_times == [NOW]

def test_worker_confirms_only_after_gateway_send_succeeds(context):
    worker, gateway, session, _, core, _ = context
    core.pending = [OutboundClaim(OUTBOUND_ID, "in-1", "reply", LEASE)]
    gateway.send_error = RuntimeError("page unavailable")

    worker.run_once()

    assert core.confirmed == []
    assert worker.login_state is LoginState.AUTH_REQUIRED
    assert session.stops == 1
    assert core.audits == [("authentication_lost", "worker-a", NOW)]


def test_read_failure_resets_the_browser_session_and_marks_auth_required(context):
    worker, gateway, session, _, core, _ = context
    gateway.read_error = RuntimeError("socket disconnected")

    worker.run_once()

    assert worker.login_state is LoginState.AUTH_REQUIRED
    assert session.stops == 1
    assert core.audits == [("authentication_lost", "worker-a", NOW)]
    assert core.heartbeats[-1] == ("worker-a", LoginState.AUTH_REQUIRED, NOW)


def test_duplicate_content_rejection_is_marked_failed_without_resetting_browser(context):
    worker, gateway, session, _, core, _ = context
    core.pending = [OutboundClaim(OUTBOUND_ID, "in-1", "reply", LEASE)]
    gateway.send_error = RuntimeError("请勿发送重复内容")

    worker.run_once()

    assert core.confirmed == []
    assert core.failed == [(OUTBOUND_ID, "worker-a", LEASE, NOW)]
    assert worker.login_state is LoginState.READY
    assert session.stops == 0


def test_sent_confirmation_includes_current_fencing_values(context):
    worker, _, _, _, core, _ = context
    core.pending = [OutboundClaim(OUTBOUND_ID, "in-1", "reply", LEASE)]

    worker.run_once()

    assert core.confirmed == [
        (OUTBOUND_ID, "worker-a", LEASE, "sent-1", NOW)
    ]


def test_worker_retracts_a_due_outbound_with_current_fencing_values(context):
    worker, gateway, _, _, core, _ = context
    core.pending_recalls = [
        OutboundRecallClaim(OUTBOUND_ID, "platform-message", LEASE)
    ]

    worker.run_once()

    assert gateway.retracted == ["platform-message"]
    assert core.recalls_confirmed == [(OUTBOUND_ID, "worker-a", LEASE, NOW)]


def test_paused_worker_still_heartbeats_and_polls_commands(context):
    worker, gateway, _, _, core, _ = context
    core.commands = [WorkerCommand(COMMAND_ID, "pause_listening", LEASE)]
    gateway.messages = [InboundMessage("p-1", "u-1", "/test", NOW)]

    worker.run_once()
    worker.run_once()

    assert len(core.heartbeats) == 2
    assert core.completions == [
        (COMMAND_ID, "worker-a", LEASE, "completed", NOW)
    ]
    assert core.submitted_ids == []


@pytest.mark.parametrize(
    ("command", "expected_starts", "expected_stops", "desktop_starts", "desktop_stops"),
    [
        ("restart_browser", 1, 1, 0, 0),
        ("start_auth", 0, 1, 1, 0),
        ("finish_auth", 1, 0, 0, 0),
    ],
)
def test_lifecycle_commands_touch_only_the_expected_processes(
    context, command, expected_starts, expected_stops, desktop_starts, desktop_stops
):
    worker, _, session, desktop, core, _ = context
    core.commands = [WorkerCommand(COMMAND_ID, command, LEASE)]

    worker.run_once()

    assert (session.starts, session.stops) == (expected_starts, expected_stops)
    assert (desktop.starts, desktop.stops) == (desktop_starts, desktop_stops)


def test_cancel_auth_closes_desktop_and_restores_the_persisted_browser(context):
    worker, _, session, desktop, core, _ = context
    core.commands = [
        WorkerCommand(COMMAND_ID, "start_auth", LEASE),
        WorkerCommand(UUID(int=4), "cancel_auth", UUID(int=5)),
    ]

    worker.run_once()
    worker.run_once()

    assert (desktop.starts, desktop.stops) == (1, 1)
    assert (session.starts, session.stops) == (1, 1)
    assert worker.login_state is LoginState.READY


def test_authentication_loss_transitions_once_and_backs_off_bounded(context):
    worker, gateway, _, _, core, sleeps = context
    gateway.authenticated = False

    for _ in range(8):
        worker.run_once()

    assert core.audits == [("authentication_lost", "worker-a", NOW)]
    assert core.submitted_ids == []
    assert all(state is LoginState.AUTH_REQUIRED for _, state, _ in core.heartbeats)
    assert sleeps == [1, 2, 2, 2, 2, 2, 2, 2]


def test_resume_listening_allows_polling_again(context):
    worker, gateway, _, _, core, _ = context
    gateway.messages = [InboundMessage("p-1", "u-1", "/test", NOW)]
    core.commands = [
        WorkerCommand(COMMAND_ID, "pause_listening", LEASE),
        WorkerCommand(UUID(int=4), "resume_listening", UUID(int=5)),
    ]

    worker.run_once()
    worker.run_once()

    assert core.submitted_ids == ["p-1"]


def test_retract_test_command_withdraws_its_own_test_message(context):
    worker, gateway, _, _, core, _ = context
    core.commands = [WorkerCommand(COMMAND_ID, "retract_test", LEASE)]

    worker.run_once()

    assert gateway.sent == ["【撤回验证】这条消息会立即撤回。"]
    assert gateway.retracted == ["sent-1"]
    assert core.completions == [
        (COMMAND_ID, "worker-a", LEASE, "completed", NOW)
    ]
