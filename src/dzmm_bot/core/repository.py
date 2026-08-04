from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from dzmm_bot.runtime.contracts import InboundMessage, WorkerHeartbeat

from .schema import (
    InboundRecord,
    OutboundRecord,
    WorkerCommandRecord,
    WorkerInstanceRecord,
)


class CoreRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._active_session: ContextVar[Session | None] = ContextVar(
            f"core_repository_session_{id(self)}", default=None
        )

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._active_session.get() is not None:
            yield
            return
        with self._session_factory.begin() as session:
            token = self._active_session.set(session)
            try:
                yield
            finally:
                self._active_session.reset(token)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        active = self._active_session.get()
        if active is not None:
            yield active
            return
        with self._session_factory.begin() as session:
            yield session

    def accept_inbound(self, message: InboundMessage) -> tuple[InboundRecord, bool]:
        with self._session() as session:
            record_id = uuid4()
            values = dict(
                id=record_id,
                platform_message_id=message.platform_message_id,
                sender_platform_id=message.sender_platform_id,
                content=message.content,
                received_at=message.received_at,
            )
            dialect_name = session.get_bind().dialect.name
            if dialect_name == "postgresql":
                statement = postgresql_insert(InboundRecord).values(**values)
            elif dialect_name == "sqlite":
                statement = sqlite_insert(InboundRecord).values(**values)
            else:
                raise ValueError(f"unsupported database dialect: {dialect_name}")
            inserted_id = session.scalar(
                statement.on_conflict_do_nothing(
                    index_elements=[InboundRecord.platform_message_id]
                ).returning(InboundRecord.id)
            )
            if inserted_id is None:
                record = session.scalar(
                    select(InboundRecord).where(
                        InboundRecord.platform_message_id == message.platform_message_id
                    )
                )
                if record is None:
                    raise RuntimeError("conflicting inbound message disappeared")
                return record, False
            record = session.get(InboundRecord, inserted_id)
            if record is None:
                raise RuntimeError("inserted inbound message disappeared")
            return record, True

    def enqueue_outbound(
        self, inbound_message_id: UUID | str, reply: str
    ) -> OutboundRecord:
        with self._session() as session:
            record = OutboundRecord(
                inbound_message_id=UUID(str(inbound_message_id)), text=reply
            )
            session.add(record)
            session.flush()
            return record

    def claim_outbound(
        self, worker_id: str, now: datetime, lease_seconds: int
    ) -> OutboundRecord | None:
        with self._session() as session:
            record = session.scalar(
                select(OutboundRecord)
                .where(
                    OutboundRecord.status.in_(("pending", "leased")),
                    or_(
                        OutboundRecord.lease_expires_at.is_(None),
                        OutboundRecord.lease_expires_at <= now,
                    ),
                )
                .order_by(OutboundRecord.created_at, OutboundRecord.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if record is None:
                return None
            record.status = "leased"
            record.lease_worker_id = worker_id
            record.lease_token = uuid4()
            record.lease_expires_at = now + timedelta(seconds=lease_seconds)
            record.attempt_count += 1
            session.flush()
            return record

    def confirm_sent(
        self,
        message_id: UUID | str,
        worker_id: str,
        lease_token: UUID | str,
        platform_sent_id: str,
        now: datetime,
    ) -> bool:
        with self._session() as session:
            confirmed_id = session.scalar(
                update(OutboundRecord)
                .where(
                    OutboundRecord.id == UUID(str(message_id)),
                    OutboundRecord.status == "leased",
                    OutboundRecord.lease_worker_id == worker_id,
                    OutboundRecord.lease_token == UUID(str(lease_token)),
                    OutboundRecord.lease_expires_at > now,
                )
                .values(
                    status="sent",
                    platform_sent_id=platform_sent_id,
                    lease_worker_id=None,
                    lease_token=None,
                    lease_expires_at=None,
                )
                .returning(OutboundRecord.id)
            )
            return confirmed_id is not None

    def enqueue_worker_command(self, command: str) -> WorkerCommandRecord:
        with self._session() as session:
            record = WorkerCommandRecord(command=command)
            session.add(record)
            session.flush()
            return record

    def claim_worker_command(
        self, worker_id: str, now: datetime, lease_seconds: int
    ) -> WorkerCommandRecord | None:
        with self._session() as session:
            record = session.scalar(
                select(WorkerCommandRecord)
                .where(
                    WorkerCommandRecord.status.in_(("pending", "leased")),
                    or_(
                        WorkerCommandRecord.lease_expires_at.is_(None),
                        WorkerCommandRecord.lease_expires_at <= now,
                    ),
                )
                .order_by(WorkerCommandRecord.created_at, WorkerCommandRecord.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if record is None:
                return None
            record.status = "leased"
            record.lease_worker_id = worker_id
            record.lease_token = uuid4()
            record.lease_expires_at = now + timedelta(seconds=lease_seconds)
            session.flush()
            return record

    def complete_worker_command(
        self,
        command_id: UUID | str,
        worker_id: str,
        lease_token: UUID | str,
        status: str,
        now: datetime,
    ) -> bool:
        with self._session() as session:
            completed_id = session.scalar(
                update(WorkerCommandRecord)
                .where(
                    WorkerCommandRecord.id == UUID(str(command_id)),
                    WorkerCommandRecord.status == "leased",
                    WorkerCommandRecord.lease_worker_id == worker_id,
                    WorkerCommandRecord.lease_token == UUID(str(lease_token)),
                    WorkerCommandRecord.lease_expires_at > now,
                )
                .values(
                    status=status,
                    completed_at=now,
                    lease_worker_id=None,
                    lease_token=None,
                    lease_expires_at=None,
                )
                .returning(WorkerCommandRecord.id)
            )
            return completed_id is not None

    def record_worker_heartbeat(
        self, heartbeat: WorkerHeartbeat
    ) -> WorkerInstanceRecord:
        with self._session() as session:
            values = dict(
                id=uuid4(),
                worker_id=heartbeat.worker_id,
                login_state=heartbeat.login_state.value,
                recorded_at=heartbeat.recorded_at,
            )
            dialect_name = session.get_bind().dialect.name
            if dialect_name == "postgresql":
                statement = postgresql_insert(WorkerInstanceRecord).values(**values)
            elif dialect_name == "sqlite":
                statement = sqlite_insert(WorkerInstanceRecord).values(**values)
            else:
                raise ValueError(f"unsupported database dialect: {dialect_name}")
            upsert = statement.on_conflict_do_update(
                index_elements=[WorkerInstanceRecord.worker_id],
                set_={
                    "login_state": statement.excluded.login_state,
                    "recorded_at": statement.excluded.recorded_at,
                },
            ).returning(WorkerInstanceRecord.id)
            record_id = session.scalar(upsert)
            record = session.get(WorkerInstanceRecord, record_id)
            if record is None:
                raise RuntimeError("persisted worker heartbeat disappeared")
            return record

    def queue_counts(self) -> dict[str, int]:
        with self._session() as session:
            return {
                "inbound_accepted": session.scalar(
                    select(func.count())
                    .select_from(InboundRecord)
                    .where(InboundRecord.status == "accepted")
                )
                or 0,
                "outbound_pending": session.scalar(
                    select(func.count())
                    .select_from(OutboundRecord)
                    .where(OutboundRecord.status == "pending")
                )
                or 0,
                "worker_commands_pending": session.scalar(
                    select(func.count())
                    .select_from(WorkerCommandRecord)
                    .where(WorkerCommandRecord.status == "pending")
                )
                or 0,
            }
