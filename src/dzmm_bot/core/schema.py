from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


BEIJING = ZoneInfo("Asia/Shanghai")


def beijing_now() -> datetime:
    return datetime.now(BEIJING)


class BeijingDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        return value.astimezone(BEIJING)

    def process_result_value(
        self, value: datetime | None, dialect: Any
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=BEIJING)
        return value.astimezone(BEIJING)


class Base(DeclarativeBase):
    pass


class InboundRecord(Base):
    __tablename__ = "inbound_messages"
    __table_args__ = (
        Index(
            "ux_inbound_messages_platform_message_id",
            "platform_message_id",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    platform_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_platform_id: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(BeijingDateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="accepted", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        BeijingDateTime, default=beijing_now, nullable=False
    )


class CommandDefinitionRecord(Base):
    __tablename__ = "command_definitions"

    command: Mapped[str] = mapped_column(String(32), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        BeijingDateTime, default=beijing_now, nullable=False
    )


class CommandReplyTemplateRecord(Base):
    __tablename__ = "command_reply_templates"
    __table_args__ = (UniqueConstraint("command", "scenario"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    command: Mapped[str] = mapped_column(String(32), nullable=False)
    scenario: Mapped[str] = mapped_column(String(64), nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        BeijingDateTime, default=beijing_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        BeijingDateTime, default=beijing_now, onupdate=beijing_now, nullable=False
    )


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    platform_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(BeijingDateTime, nullable=False)


class DailyCheckinRecord(Base):
    __tablename__ = "daily_checkins"
    __table_args__ = (UniqueConstraint("user_id", "checkin_date"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    checkin_date: Mapped[date] = mapped_column(Date, nullable=False)
    checked_in_at: Mapped[datetime] = mapped_column(BeijingDateTime, nullable=False)


class ItemRecord(Base):
    __tablename__ = "items"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        BeijingDateTime, default=beijing_now, nullable=False
    )


class UserItemRecord(Base):
    __tablename__ = "user_items"
    __table_args__ = (UniqueConstraint("user_id", "item_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    item_id: Mapped[UUID] = mapped_column(ForeignKey("items.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        BeijingDateTime, default=beijing_now, nullable=False
    )


class OutboundRecord(Base):
    __tablename__ = "outbound_messages"
    __table_args__ = (
        Index(
            "ix_outbound_messages_claim",
            "status",
            "lease_expires_at",
            "created_at",
            postgresql_where=text("status IN ('pending', 'leased')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    inbound_message_id: Mapped[UUID] = mapped_column(
        ForeignKey("inbound_messages.id"), unique=True, nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    lease_worker_id: Mapped[str | None] = mapped_column(String(255))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(BeijingDateTime)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    platform_sent_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        BeijingDateTime, default=beijing_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        BeijingDateTime, default=beijing_now, onupdate=beijing_now, nullable=False
    )


class WorkerInstanceRecord(Base):
    __tablename__ = "worker_instances"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    worker_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    login_state: Mapped[str] = mapped_column(String(32), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(BeijingDateTime, nullable=False)
    version: Mapped[str | None] = mapped_column(String(64))
    browser_state: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(Text)


class WorkerCommandRecord(Base):
    __tablename__ = "worker_commands"
    __table_args__ = (
        Index(
            "ix_worker_commands_claim",
            "status",
            "lease_expires_at",
            "created_at",
            postgresql_where=text("status IN ('pending', 'leased')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    command: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    lease_worker_id: Mapped[str | None] = mapped_column(String(255))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(BeijingDateTime)
    result: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        BeijingDateTime, default=beijing_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(BeijingDateTime)


class LoginSessionRecord(Base):
    __tablename__ = "login_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        BeijingDateTime, default=beijing_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(BeijingDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        BeijingDateTime, default=beijing_now, nullable=False
    )
