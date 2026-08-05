from collections.abc import Callable
from datetime import UTC, datetime
from time import sleep as default_sleep
from typing import Protocol

from dzmm_bot.runtime.contracts import LoginState

from .core_client import CorePort, WorkerCommand
from .session import BrowserSession, ChatGateway


class ManualDesktop(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class BrowserWorker:
    def __init__(
        self,
        *,
        worker_id: str,
        core: CorePort,
        session: BrowserSession,
        desktop: ManualDesktop,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = default_sleep,
        lease_seconds: int = 30,
    ) -> None:
        self._worker_id = worker_id
        self._core = core
        self._session = session
        self._desktop = desktop
        self._clock = clock
        self._sleep = sleep
        self._lease_seconds = lease_seconds
        self._gateway: ChatGateway | None = None
        self._listening = True
        self._login_state = LoginState.READY
        self._seen_message_ids: set[str] = set()
        self._auth_loss_reported = False
        self._auth_backoff = 1

    @property
    def login_state(self) -> LoginState:
        return self._login_state

    @property
    def browser_stopped(self) -> bool:
        return self._gateway is None

    def run_once(self) -> None:
        now = self._clock()
        command = self._core.claim_command(
            self._worker_id, now, self._lease_seconds
        )
        if command is not None:
            self._execute_command(command)

        if self._login_state is not LoginState.AUTH_IN_PROGRESS:
            gateway = self._ensure_gateway()
            if gateway.is_authenticated():
                self._login_state = LoginState.READY
                self._auth_loss_reported = False
                self._auth_backoff = 1
            else:
                self._transition_to_auth_required()

        self._core.heartbeat(self._worker_id, self._login_state, self._clock())

        if self._login_state is LoginState.AUTH_REQUIRED:
            delay = self._auth_backoff
            self._auth_backoff = min(self._auth_backoff * 2, 2)
            self._sleep(delay)
            return
        if self._login_state is LoginState.AUTH_IN_PROGRESS:
            return

        gateway = self._ensure_gateway()
        if self._listening:
            for message in gateway.read_new():
                if message.platform_message_id in self._seen_message_ids:
                    continue
                self._core.submit_inbound(message)
                self._seen_message_ids.add(message.platform_message_id)

        outbound = self._core.claim_outbound(
            self._worker_id, self._clock(), self._lease_seconds
        )
        if outbound is None:
            return
        try:
            platform_sent_id = gateway.send(outbound.text)
        except Exception:
            return
        self._core.confirm_sent(
            outbound.id,
            self._worker_id,
            outbound.lease_token,
            platform_sent_id,
            self._clock(),
        )

    def _ensure_gateway(self) -> ChatGateway:
        if self._gateway is None:
            self._gateway = self._session.start_headless()
        return self._gateway

    def _transition_to_auth_required(self) -> None:
        self._login_state = LoginState.AUTH_REQUIRED
        self._listening = False
        if not self._auth_loss_reported:
            self._core.record_audit(
                "authentication_lost", self._worker_id, self._clock()
            )
            self._auth_loss_reported = True

    def _execute_command(self, command: WorkerCommand) -> None:
        status = "completed"
        try:
            if command.command == "pause_listening":
                self._listening = False
            elif command.command == "resume_listening":
                self._listening = True
            elif command.command == "restart_browser":
                self._session.stop()
                self._gateway = self._session.start_headless()
            elif command.command == "start_auth":
                self._session.stop()
                self._gateway = None
                self._desktop.start()
                self._login_state = LoginState.AUTH_IN_PROGRESS
                self._listening = False
            elif command.command == "finish_auth":
                self._desktop.stop()
                self._gateway = self._session.start_headless()
                self._login_state = LoginState.READY
                self._listening = True
                self._auth_loss_reported = False
                self._auth_backoff = 1
            else:
                raise ValueError(f"unsupported worker command: {command.command}")
        except Exception:
            status = "failed"
        self._core.complete_command(
            command.id,
            self._worker_id,
            command.lease_token,
            status,
            self._clock(),
        )
