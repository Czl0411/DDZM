from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
from time import sleep as default_sleep
from typing import Protocol

from dzmm_bot.runtime.contracts import LoginState

from .core_client import CorePort, WorkerCommand
from .session import BrowserSession, ChatGateway


_LOGGER = logging.getLogger(__name__)


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
        clock: Callable[[], datetime] = lambda: datetime.now(ZoneInfo("Asia/Shanghai")),
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
        self._manual_auth_confirmed = False

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
            try:
                gateway = self._ensure_gateway()
                authenticated = gateway.is_authenticated()
            except Exception:
                _LOGGER.exception("browser authentication check failed")
                self._recover_browser_session()
            else:
                if authenticated or self._manual_auth_confirmed:
                    self._login_state = LoginState.READY
                    self._auth_loss_reported = False
                    self._auth_backoff = 1
                else:
                    self._recover_browser_session()

        self._core.heartbeat(self._worker_id, self._login_state, self._clock())

        if self._login_state is LoginState.AUTH_REQUIRED:
            self._core.run_daily_jobs(now)
            delay = self._auth_backoff
            self._auth_backoff = min(self._auth_backoff * 2, 2)
            self._sleep(delay)
            return
        if self._login_state is LoginState.AUTH_IN_PROGRESS:
            self._core.run_daily_jobs(now)
            return

        gateway = self._ensure_gateway()
        if self._listening:
            try:
                messages = gateway.read_new()
            except NotImplementedError:
                self._listening = False
                messages = []
            except Exception:
                _LOGGER.exception("browser message read failed")
                self._recover_browser_session()
                self._core.heartbeat(
                    self._worker_id, self._login_state, self._clock()
                )
                return
            for message in messages:
                if message.platform_message_id in self._seen_message_ids:
                    continue
                self._core.submit_inbound(message)
                self._seen_message_ids.add(message.platform_message_id)

        self._core.run_daily_jobs(now)

        recall = self._core.claim_outbound_recall(
            self._worker_id, self._clock(), self._lease_seconds
        )
        if recall is not None:
            try:
                gateway.retract(recall.platform_sent_id)
            except Exception:
                _LOGGER.exception("outbound retraction failed: %s", recall.id)
            else:
                self._core.confirm_outbound_recalled(
                    recall.id,
                    self._worker_id,
                    recall.lease_token,
                    self._clock(),
                )

        outbound = self._core.claim_outbound(
            self._worker_id, self._clock(), self._lease_seconds
        )
        if outbound is None:
            return
        try:
            platform_sent_id = gateway.send(outbound.text)
        except Exception as error:
            if "请勿发送重复内容" in str(error):
                _LOGGER.warning("outbound content rejected as duplicate: %s", outbound.id)
                self._core.mark_outbound_failed(
                    outbound.id,
                    self._worker_id,
                    outbound.lease_token,
                    self._clock(),
                )
                return
            _LOGGER.exception("outbound send failed: %s", outbound.id)
            self._recover_browser_session()
            self._core.heartbeat(
                self._worker_id, self._login_state, self._clock()
            )
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

    def _recover_browser_session(self) -> None:
        self._session.stop()
        self._gateway = None
        self._transition_to_auth_required()

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
                self._manual_auth_confirmed = False
            elif command.command == "finish_auth":
                self._gateway = self._session.attach_existing()
                self._login_state = LoginState.READY
                self._listening = True
                self._auth_loss_reported = False
                self._auth_backoff = 1
                self._manual_auth_confirmed = True
            elif command.command == "cancel_auth":
                self._desktop.stop()
                self._gateway = None
                self._login_state = LoginState.AUTH_REQUIRED
                self._listening = True
                self._manual_auth_confirmed = False
            elif command.command == "retract_test":
                gateway = self._ensure_gateway()
                platform_message_id = gateway.send("【撤回验证】这条消息会立即撤回。")
                gateway.retract(platform_message_id)
                _LOGGER.info("worker retraction test succeeded: %s", platform_message_id)
            else:
                raise ValueError(f"unsupported worker command: {command.command}")
        except Exception:
            _LOGGER.exception("worker command failed: %s", command.command)
            status = "failed"
        self._core.complete_command(
            command.id,
            self._worker_id,
            command.lease_token,
            status,
            self._clock(),
        )
