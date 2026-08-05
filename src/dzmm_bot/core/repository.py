from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from dzmm_bot.runtime.contracts import InboundMessage, WorkerHeartbeat

from .reply_templates import TEMPLATE_DEFINITIONS, validate_template
from .schema import (
    ActivityLevelRuleRecord,
    CommandDefinitionRecord,
    CommandReplyTemplateRecord,
    DailyCheckinRecord,
    GameSettingsRecord,
    IncomeReportScheduleRecord,
    InboundRecord,
    ItemRecord,
    OutboundRecord,
    UserItemRecord,
    UserRecord,
    WorkerCommandRecord,
    WorkerInstanceRecord,
)


_DEFAULT_CURRENCY_NAME = "摸鱼币"
_DEFAULT_ONBOARDING_BONUS = 0
_DEFAULT_CHECKIN_REWARD = 5
_DEFAULT_ACTIVITY_RULES = (
    (1, 10, 1),
    (2, 25, 2),
    (3, 60, 3),
    (4, 90, 4),
    (5, 140, 5),
    (6, 190, 6),
    (7, 250, 7),
    (8, 330, 8),
    (9, 410, 9),
    (10, 500, 10),
)
_DEFAULT_INCOME_REPORT_TIMES = ("12:00", "16:00", "20:00", "23:59")


@dataclass(frozen=True)
class ActivityLevelRule:
    level: int
    character_threshold: int
    reward: int


@dataclass(frozen=True)
class ActivitySettings:
    rules: list[ActivityLevelRule]
    report_times: list[str]


_COMMAND_DEFINITIONS = (
    ("/入职", "登记群成员为摸鱼公司员工"),
    ("/我的物品", "查看自己持有的物品"),
    ("/打卡", "每日领取 5 摸鱼币"),
    ("/余额", "查看当前摸鱼币余额"),
    ("/商店", "查看当前上架物品"),
    ("/帮助", "查看当前可用指令"),
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

    def ensure_command_definitions(self) -> None:
        with self._session() as session:
            dialect_name = session.get_bind().dialect.name
            for command, description in _COMMAND_DEFINITIONS:
                values = {"command": command, "description": description}
                if dialect_name == "postgresql":
                    statement = postgresql_insert(CommandDefinitionRecord).values(**values)
                elif dialect_name == "sqlite":
                    statement = sqlite_insert(CommandDefinitionRecord).values(**values)
                else:
                    raise ValueError(f"unsupported database dialect: {dialect_name}")
                session.execute(
                    statement.on_conflict_do_nothing(
                        index_elements=[CommandDefinitionRecord.command]
                    )
                )
        self.ensure_reply_templates()

    def ensure_reply_templates(self) -> None:
        with self._session() as session:
            dialect_name = session.get_bind().dialect.name
            for definition in TEMPLATE_DEFINITIONS:
                values = {
                    "id": uuid4(),
                    "command": definition.command,
                    "scenario": definition.scenario,
                    "template": definition.default,
                }
                if dialect_name == "postgresql":
                    statement = postgresql_insert(CommandReplyTemplateRecord).values(
                        **values
                    )
                elif dialect_name == "sqlite":
                    statement = sqlite_insert(CommandReplyTemplateRecord).values(
                        **values
                    )
                else:
                    raise ValueError(f"unsupported database dialect: {dialect_name}")
                session.execute(
                    statement.on_conflict_do_nothing(
                        index_elements=[
                            CommandReplyTemplateRecord.command,
                            CommandReplyTemplateRecord.scenario,
                        ]
                    )
                )

    def list_reply_templates(self, command: str) -> list[CommandReplyTemplateRecord]:
        self.ensure_reply_templates()
        with self._session() as session:
            return list(
                session.scalars(
                    select(CommandReplyTemplateRecord)
                    .where(CommandReplyTemplateRecord.command == command)
                    .order_by(CommandReplyTemplateRecord.scenario)
                )
            )

    def get_reply_template(
        self, command: str, scenario: str
    ) -> CommandReplyTemplateRecord | None:
        with self._session() as session:
            return session.scalar(
                select(CommandReplyTemplateRecord).where(
                    CommandReplyTemplateRecord.command == command,
                    CommandReplyTemplateRecord.scenario == scenario,
                )
            )

    def set_reply_template(
        self, command: str, scenario: str, template: str
    ) -> CommandReplyTemplateRecord:
        validate_template(command, scenario, template)
        self.ensure_reply_templates()
        with self._session() as session:
            record = session.scalar(
                select(CommandReplyTemplateRecord).where(
                    CommandReplyTemplateRecord.command == command,
                    CommandReplyTemplateRecord.scenario == scenario,
                )
            )
            if record is None:
                raise RuntimeError("reply template disappeared")
            record.template = template
            session.flush()
            return record

    def is_command_enabled(self, command: str) -> bool:
        with self._session() as session:
            return bool(
                session.scalar(
                    select(CommandDefinitionRecord.enabled).where(
                        CommandDefinitionRecord.command == command
                    )
                )
            )

    def list_command_definitions(self) -> list[CommandDefinitionRecord]:
        self.ensure_command_definitions()
        with self._session() as session:
            return list(
                session.scalars(
                    select(CommandDefinitionRecord).order_by(CommandDefinitionRecord.command)
                )
            )

    def list_enabled_command_definitions(self) -> list[CommandDefinitionRecord]:
        self.ensure_command_definitions()
        with self._session() as session:
            return list(
                session.scalars(
                    select(CommandDefinitionRecord)
                    .where(CommandDefinitionRecord.enabled.is_(True))
                    .order_by(CommandDefinitionRecord.command)
                )
            )

    def set_command_enabled(self, command: str, enabled: bool) -> bool:
        self.ensure_command_definitions()
        with self._session() as session:
            record = session.get(CommandDefinitionRecord, command)
            if record is None:
                return False
            record.enabled = enabled
            session.flush()
            return True

    def get_game_settings(self) -> GameSettingsRecord:
        with self._session() as session:
            record = session.get(GameSettingsRecord, 1)
            if record is None:
                record = GameSettingsRecord(
                    id=1,
                    currency_name=_DEFAULT_CURRENCY_NAME,
                    onboarding_bonus=_DEFAULT_ONBOARDING_BONUS,
                    checkin_reward=_DEFAULT_CHECKIN_REWARD,
                )
                session.add(record)
                session.flush()
            return record

    def ensure_activity_settings(self) -> None:
        with self._session() as session:
            dialect_name = session.get_bind().dialect.name
            for level, character_threshold, reward in _DEFAULT_ACTIVITY_RULES:
                values = {
                    "level": level,
                    "character_threshold": character_threshold,
                    "reward": reward,
                }
                if dialect_name == "postgresql":
                    statement = postgresql_insert(ActivityLevelRuleRecord).values(**values)
                elif dialect_name == "sqlite":
                    statement = sqlite_insert(ActivityLevelRuleRecord).values(**values)
                else:
                    raise ValueError(f"unsupported database dialect: {dialect_name}")
                session.execute(
                    statement.on_conflict_do_nothing(
                        index_elements=[ActivityLevelRuleRecord.level]
                    )
                )
            for report_time in _DEFAULT_INCOME_REPORT_TIMES:
                values = {"report_time": report_time}
                if dialect_name == "postgresql":
                    statement = postgresql_insert(IncomeReportScheduleRecord).values(
                        **values
                    )
                elif dialect_name == "sqlite":
                    statement = sqlite_insert(IncomeReportScheduleRecord).values(**values)
                else:
                    raise ValueError(f"unsupported database dialect: {dialect_name}")
                session.execute(
                    statement.on_conflict_do_nothing(
                        index_elements=[IncomeReportScheduleRecord.report_time]
                    )
                )

    def get_activity_settings(self) -> ActivitySettings:
        self.ensure_activity_settings()
        with self._session() as session:
            rules = list(
                session.scalars(
                    select(ActivityLevelRuleRecord).order_by(ActivityLevelRuleRecord.level)
                )
            )
            report_times = list(
                session.scalars(
                    select(IncomeReportScheduleRecord.report_time).order_by(
                        IncomeReportScheduleRecord.report_time
                    )
                )
            )
        return ActivitySettings(
            rules=[
                ActivityLevelRule(
                    rule.level, rule.character_threshold, rule.reward
                )
                for rule in rules
            ],
            report_times=report_times,
        )

    def set_game_settings(
        self, currency_name: str, onboarding_bonus: int, checkin_reward: int
    ) -> GameSettingsRecord:
        currency_name = currency_name.strip()
        if not 1 <= len(currency_name) <= 12:
            raise ValueError("货币名称需为 1 至 12 个字符")
        if not 0 <= onboarding_bonus <= 999:
            raise ValueError("入职初始余额需在 0 至 999 之间")
        if not 0 <= checkin_reward <= 999:
            raise ValueError("打卡奖励需在 0 至 999 之间")
        with self._session() as session:
            record = session.get(GameSettingsRecord, 1)
            if record is None:
                record = GameSettingsRecord(id=1)
                session.add(record)
            record.currency_name = currency_name
            record.onboarding_bonus = onboarding_bonus
            record.checkin_reward = checkin_reward
            session.flush()
            return record

    def find_user(self, platform_id: str) -> UserRecord | None:
        with self._session() as session:
            return session.scalar(
                select(UserRecord).where(UserRecord.platform_id == platform_id)
            )

    def create_user(
        self, platform_id: str, display_name: str, joined_at: datetime, initial_balance: int
    ) -> tuple[UserRecord, bool]:
        with self._session() as session:
            existing = session.scalar(
                select(UserRecord).where(UserRecord.platform_id == platform_id)
            )
            if existing is not None:
                return existing, False
            record = UserRecord(
                platform_id=platform_id,
                display_name=display_name,
                balance=initial_balance,
                joined_at=joined_at,
            )
            session.add(record)
            session.flush()
            return record, True

    def check_in(self, user: UserRecord, checked_in_at: datetime, reward: int) -> bool:
        with self._session() as session:
            employee = session.get(UserRecord, user.id)
            if employee is None:
                raise RuntimeError("employee disappeared")
            values = {
                "id": uuid4(),
                "user_id": employee.id,
                "checkin_date": checked_in_at.date(),
                "checked_in_at": checked_in_at,
            }
            dialect_name = session.get_bind().dialect.name
            if dialect_name == "postgresql":
                statement = postgresql_insert(DailyCheckinRecord).values(**values)
            elif dialect_name == "sqlite":
                statement = sqlite_insert(DailyCheckinRecord).values(**values)
            else:
                raise ValueError(f"unsupported database dialect: {dialect_name}")
            inserted_id = session.scalar(
                statement.on_conflict_do_nothing(
                    index_elements=[
                        DailyCheckinRecord.user_id,
                        DailyCheckinRecord.checkin_date,
                    ]
                ).returning(DailyCheckinRecord.id)
            )
            if inserted_id is None:
                return False
            employee.balance += reward
            session.flush()
            return True

    def list_users(self) -> list[UserRecord]:
        with self._session() as session:
            return list(
                session.scalars(select(UserRecord).order_by(UserRecord.joined_at))
            )

    def add_item(
        self, name: str, description: str, price: int, stock: int
    ) -> ItemRecord:
        with self._session() as session:
            record = ItemRecord(
                name=name,
                description=description,
                price=price,
                stock=stock,
                enabled=True,
            )
            session.add(record)
            session.flush()
            return record

    def list_active_items(self) -> list[ItemRecord]:
        with self._session() as session:
            return list(
                session.scalars(
                    select(ItemRecord)
                    .where(ItemRecord.enabled.is_(True))
                    .order_by(ItemRecord.price, ItemRecord.name)
                )
            )

    def list_user_items(self, user_id: UUID) -> list[tuple[str, int]]:
        with self._session() as session:
            return list(
                session.execute(
                    select(ItemRecord.name, UserItemRecord.quantity)
                    .join(UserItemRecord, UserItemRecord.item_id == ItemRecord.id)
                    .where(UserItemRecord.user_id == user_id)
                    .order_by(ItemRecord.name)
                )
            )

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

    def enqueue_system_outbound(self, text: str) -> OutboundRecord:
        with self._session() as session:
            record = OutboundRecord(inbound_message_id=None, text=text)
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
