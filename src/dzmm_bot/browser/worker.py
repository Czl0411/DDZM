from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logging
from threading import Lock
from time import monotonic as default_monotonic, sleep as default_sleep
from typing import Protocol

from dzmm_bot.runtime.contracts import DirectChatRoom, InboundMessage, LoginState
from dzmm_bot.runtime.outbound import requires_bot_group_sender

from .core_client import CorePort, OutboundClaim, WorkerCommand
from .session import BrowserSession, ChatGateway


_LOGGER = logging.getLogger(__name__)
_OUTBOUND_BATCH_SIZE = 20
_OUTBOUND_BATCH_BUDGET_SECONDS = 2.0


class ManualDesktop(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class BotSender(Protocol):
    def send_to(self, chatroom_id: str, text: str) -> str: ...


class BrowserWorker:
    def __init__(
        self,
        *,
        worker_id: str,
        core: CorePort,
        session: BrowserSession,
        desktop: ManualDesktop,
        clock: Callable[[], datetime] = lambda: datetime.now(ZoneInfo("Asia/Shanghai")),
        monotonic: Callable[[], float] = default_monotonic,
        sleep: Callable[[float], None] = default_sleep,
        lease_seconds: int = 30,
        bot_sender: BotSender | None = None,
        bot_chatroom_id: str | None = None,
    ) -> None:
        self._worker_id = worker_id
        self._core = core
        self._session = session
        self._desktop = desktop
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._lease_seconds = lease_seconds
        self._bot_sender = bot_sender
        self._bot_chatroom_id = bot_chatroom_id
        self._gateway: ChatGateway | None = None
        self._listening = True
        self._login_state = LoginState.READY
        self._seen_message_ids: set[str] = set()
        self._auth_loss_reported = False
        self._auth_backoff = 1
        self._manual_auth_confirmed = False
        self._last_direct_chat_sync_at: datetime | None = None
        self._inbound_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="dzmm-inbound"
        )
        self._outbound_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="dzmm-outbound"
        )
        self._outbound_future: Future[None] | None = None
        self._paused_messages: list[InboundMessage] = []
        self._paused_messages_lock = Lock()
        self._outbound_failed = False
        self._outbound_failed_lock = Lock()

    @property
    def login_state(self) -> LoginState:
        return self._login_state

    @property
    def browser_stopped(self) -> bool:
        return self._gateway is None

    def run_once(self) -> None:
        now = self._clock()
        if self._consume_outbound_failure():
            self._recover_browser_session()
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

        self._sync_listener_state()
        self._flush_paused_messages()

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
        self._sync_direct_chats(gateway, now)
        if self._listening:
            try:
                direct_targets = self._core.direct_inbound_chatroom_ids()
                messages = gateway.read_new(direct_targets)
            except NotImplementedError:
                self._listening = False
                messages = []
            except Exception:
                _LOGGER.exception("browser message read failed")
                self._recover_browser_session()
                self._sync_listener_state()
                return
            for message in messages:
                if message.platform_message_id in self._seen_message_ids:
                    continue
                self._queue_inbound(message)
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

        self._start_outbound_if_idle(gateway)

    def _queue_inbound(self, message: InboundMessage) -> None:
        if not self._listening:
            with self._paused_messages_lock:
                self._paused_messages.append(message)
            return
        self._inbound_executor.submit(self._dispatch_inbound, message)

    def _flush_paused_messages(self) -> None:
        if not self._listening:
            return
        with self._paused_messages_lock:
            messages, self._paused_messages = self._paused_messages, []
        for message in messages:
            self._inbound_executor.submit(self._dispatch_inbound, message)

    def _dispatch_inbound(self, message: InboundMessage) -> None:
        if message.source_type == "direct" and message.chatroom_id is not None:
            self._core.sync_direct_chats(
                [DirectChatRoom(message.sender_platform_id, message.chatroom_id)],
                self._clock(),
            )
        self._core.submit_inbound(message)

    def _start_outbound_if_idle(self, gateway: ChatGateway) -> None:
        if self._outbound_future is not None and not self._outbound_future.done():
            return
        if self._outbound_future is not None:
            self._outbound_future.result()
        self._outbound_future = self._outbound_executor.submit(
            self._drain_outbound, gateway
        )

    def _consume_outbound_failure(self) -> bool:
        with self._outbound_failed_lock:
            failed, self._outbound_failed = self._outbound_failed, False
        return failed

    def _drain_outbound(self, gateway: ChatGateway) -> None:
        started_at = self._monotonic()
        sent_count = 0
        while sent_count < _OUTBOUND_BATCH_SIZE:
            if self._monotonic() - started_at >= _OUTBOUND_BATCH_BUDGET_SECONDS:
                return
            outbound = self._core.claim_outbound(
                self._worker_id, self._clock(), self._lease_seconds
            )
            if outbound is None:
                return
            if not self._send_one_outbound(gateway, outbound):
                return
            sent_count += 1

    def _send_one_outbound(self, gateway: ChatGateway, outbound) -> bool:
        try:
            platform_sent_id = self._send_outbound(gateway, outbound)
        except Exception as error:
            if "请勿发送重复内容" in str(error):
                _LOGGER.warning("outbound content rejected as duplicate: %s", outbound.id)
                self._core.mark_outbound_failed(
                    outbound.id,
                    self._worker_id,
                    outbound.lease_token,
                    self._clock(),
                )
                return False
            _LOGGER.exception("outbound send failed: %s", outbound.id)
            gateway.close()
            with self._outbound_failed_lock:
                self._outbound_failed = True
            return False
        self._core.confirm_sent(
            outbound.id,
            self._worker_id,
            outbound.lease_token,
            platform_sent_id,
            self._clock(),
        )
        return True

    def _send_outbound(self, gateway: ChatGateway, outbound) -> str:
        if (
            self._bot_sender is not None
            and self._bot_chatroom_id is not None
            and outbound.destination_chatroom_id is None
            and outbound.delivery_kind == "group"
            and outbound.recall_after_seconds is None
            and requires_bot_group_sender(outbound.text)
        ):
            return self._bot_sender.send_to(self._bot_chatroom_id, outbound.text)
        if outbound.destination_chatroom_id is not None:
            return gateway.send_to(outbound.destination_chatroom_id, outbound.text)
        return gateway.send(outbound.text)

    def _sync_direct_chats(self, gateway: ChatGateway, now: datetime) -> None:
        if (
            self._last_direct_chat_sync_at is not None
            and now - self._last_direct_chat_sync_at < timedelta(seconds=30)
        ):
            return
        try:
            self._core.sync_direct_chats(gateway.discover_direct_chats(), now)
            gateway.reconcile_history(self._core.direct_inbound_chatroom_ids())
        except NotImplementedError:
            return
        except Exception:
            _LOGGER.exception("direct chat discovery failed")
            return
        self._last_direct_chat_sync_at = now

    def _ensure_gateway(self) -> ChatGateway:
        if self._gateway is None:
            self._gateway = self._configure_gateway(self._session.start_headless())
        return self._gateway

    def _configure_gateway(self, gateway: ChatGateway) -> ChatGateway:
        handler = getattr(gateway, "set_message_handler", None)
        if handler is not None:
            handler(self._queue_inbound)
        return gateway

    def _sync_listener_state(self) -> None:
        desired = self._core.heartbeat(
            self._worker_id,
            self._login_state,
            self._listening,
            self._clock(),
        )
        self._listening = desired and self._login_state is LoginState.READY

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
                self._gateway = self._configure_gateway(self._session.start_headless())
            elif command.command == "start_auth":
                self._session.stop()
                self._gateway = None
                self._desktop.start()
                self._login_state = LoginState.AUTH_IN_PROGRESS
                self._listening = False
                self._manual_auth_confirmed = False
            elif command.command == "finish_auth":
                self._gateway = self._configure_gateway(self._session.attach_existing())
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
