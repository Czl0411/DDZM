from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from dzmm_bot.runtime.contracts import InboundMessage, WorkerHeartbeat

from .reply_templates import TEMPLATE_DEFINITIONS, validate_template
from .schema import (
    ActivityLevelRuleRecord,
    ActivityRewardSettlementRecord,
    BalanceTransactionRecord,
    BEIJING,
    CommandDefinitionRecord,
    CommandReplyTemplateRecord,
    DailyActivityRecord,
    DailyCheckinRecord,
    GameSettingsRecord,
    IncomeReportDeliveryRecord,
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


@dataclass(frozen=True)
class PersonalActivity:
    level: int
    reward: int


_COMMAND_DEFINITIONS = (
    ("/入职", "登记群成员为摸鱼公司员工"),
    ("/我的物品", "查看自己持有的物品"),
    ("/打卡", "每日领取 5 摸鱼币"),
    ("/余额", "查看当前摸鱼币余额"),
    ("/我", "查看余额、今日活跃度和今日收益"),
    ("/商店", "查看当前上架物品"),
    ("/帮助", "查看当前可用指令"),
)


class CoreRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._active_session: ContextVar[Session | None] = ContextVar(
            f"core_repository_session_{id(self)}", default=None
        )
        self._current_day_history_backfilled: date | None = None

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
            if session.scalar(select(ActivityLevelRuleRecord.level).limit(1)) is None:
                for level, character_threshold, reward in _DEFAULT_ACTIVITY_RULES:
                    values = {
                        "level": level,
                        "character_threshold": character_threshold,
                        "reward": reward,
                    }
                    if dialect_name == "postgresql":
                        statement = postgresql_insert(ActivityLevelRuleRecord).values(
                            **values
                        )
                    elif dialect_name == "sqlite":
                        statement = sqlite_insert(ActivityLevelRuleRecord).values(**values)
                    else:
                        raise ValueError(
                            f"unsupported database dialect: {dialect_name}"
                        )
                    session.execute(
                        statement.on_conflict_do_nothing(
                            index_elements=[ActivityLevelRuleRecord.level]
                        )
                    )
            if session.scalar(select(IncomeReportScheduleRecord.report_time).limit(1)) is None:
                for report_time in _DEFAULT_INCOME_REPORT_TIMES:
                    values = {"report_time": report_time}
                    if dialect_name == "postgresql":
                        statement = postgresql_insert(IncomeReportScheduleRecord).values(
                            **values
                        )
                    elif dialect_name == "sqlite":
                        statement = sqlite_insert(IncomeReportScheduleRecord).values(
                            **values
                        )
                    else:
                        raise ValueError(
                            f"unsupported database dialect: {dialect_name}"
                        )
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

    def set_activity_settings(
        self, rules: list[ActivityLevelRule], report_times: list[str]
    ) -> ActivitySettings:
        if len(rules) != 10 or [rule.level for rule in rules] != list(range(1, 11)):
            raise ValueError("活跃度规则必须包含 LV1 至 LV10")
        thresholds = [rule.character_threshold for rule in rules]
        if any(
            not isinstance(threshold, int) or threshold < 0
            for threshold in thresholds
        ) or thresholds != sorted(thresholds) or len(set(thresholds)) != len(thresholds):
            raise ValueError("字数门槛必须为严格递增的非负整数")
        if any(
            not isinstance(rule.reward, int) or not 0 <= rule.reward <= 999
            for rule in rules
        ):
            raise ValueError("活跃度奖励需在 0 至 999 之间")
        if not report_times or len(set(report_times)) != len(report_times):
            raise ValueError("收益榜推送时段不能为空且不能重复")
        if any(
            re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", report_time) is None
            for report_time in report_times
        ):
            raise ValueError("收益榜推送时段必须为 HH:MM")
        with self._session() as session:
            session.execute(delete(ActivityLevelRuleRecord))
            session.add_all(
                [
                    ActivityLevelRuleRecord(
                        level=rule.level,
                        character_threshold=rule.character_threshold,
                        reward=rule.reward,
                    )
                    for rule in rules
                ]
            )
            session.execute(delete(IncomeReportScheduleRecord))
            session.add_all(
                [IncomeReportScheduleRecord(report_time=report_time) for report_time in report_times]
            )
        return self.get_activity_settings()

    def record_activity(
        self, platform_id: str, received_at: datetime, content: str
    ) -> None:
        if content.lstrip().startswith("/"):
            return
        character_count = len("".join(content.split()))
        if not character_count:
            return
        activity_date = received_at.astimezone(BEIJING).date()
        with self._session() as session:
            user = session.scalar(
                select(UserRecord).where(UserRecord.platform_id == platform_id)
            )
            if user is None:
                return
            values = {
                "id": uuid4(),
                "user_id": user.id,
                "activity_date": activity_date,
                "character_count": character_count,
            }
            dialect_name = session.get_bind().dialect.name
            if dialect_name == "postgresql":
                statement = postgresql_insert(DailyActivityRecord).values(**values)
            elif dialect_name == "sqlite":
                statement = sqlite_insert(DailyActivityRecord).values(**values)
            else:
                raise ValueError(f"unsupported database dialect: {dialect_name}")
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[
                        DailyActivityRecord.user_id,
                        DailyActivityRecord.activity_date,
                    ],
                    set_={
                        "character_count": DailyActivityRecord.character_count
                        + character_count
                    },
                )
            )

    def personal_activity(
        self, platform_id: str, now: datetime
    ) -> PersonalActivity | None:
        with self._session() as session:
            user = session.scalar(
                select(UserRecord).where(UserRecord.platform_id == platform_id)
            )
            if user is None:
                return None
            record = session.scalar(
                select(DailyActivityRecord).where(
                    DailyActivityRecord.user_id == user.id,
                    DailyActivityRecord.activity_date == now.astimezone(BEIJING).date(),
                )
            )
            character_count = 0 if record is None else record.character_count
        settings = self.get_activity_settings()
        matching_rules = [
            rule
            for rule in settings.rules
            if rule.character_threshold <= character_count
        ]
        if not matching_rules:
            return PersonalActivity(level=0, reward=0)
        rule = matching_rules[-1]
        return PersonalActivity(level=rule.level, reward=rule.reward)

    def _apply_balance_change(
        self, user: UserRecord, amount: int, source: str, occurred_at: datetime
    ) -> None:
        if amount == 0:
            return
        user.balance += amount
        session = self._active_session.get()
        if session is None:
            raise RuntimeError("balance change requires an active transaction")
        session.add(
            BalanceTransactionRecord(
                user_id=user.id,
                amount=amount,
                source=source,
                occurred_at=occurred_at,
            )
        )

    def record_balance_change(
        self, user_id: UUID, amount: int, source: str, occurred_at: datetime
    ) -> None:
        with self.transaction():
            with self._session() as session:
                user = session.get(UserRecord, user_id)
                if user is None:
                    raise ValueError("员工不存在")
                self._apply_balance_change(user, amount, source, occurred_at)

    def today_income(self, user_id: UUID, now: datetime) -> int:
        start = now.astimezone(BEIJING).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(days=1)
        with self._session() as session:
            income = session.scalar(
                select(func.coalesce(func.sum(BalanceTransactionRecord.amount), 0)).where(
                    BalanceTransactionRecord.user_id == user_id,
                    BalanceTransactionRecord.amount > 0,
                    BalanceTransactionRecord.occurred_at >= start,
                    BalanceTransactionRecord.occurred_at < end,
                )
            )
            return int(income)

    def run_daily_jobs(self, now: datetime) -> None:
        now = now.astimezone(BEIJING)
        should_backfill = self._current_day_history_backfilled != now.date()
        with self.transaction():
            if should_backfill:
                self._backfill_current_day_history(now)
            self._settle_activity_rewards(now)
            self._enqueue_due_income_reports(now)
        if should_backfill:
            self._current_day_history_backfilled = now.date()

    def _backfill_current_day_history(self, now: datetime) -> None:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        settings = self.get_game_settings()
        with self._session() as session:
            users = {
                user.platform_id: user
                for user in session.scalars(
                    select(UserRecord).where(UserRecord.joined_at < end)
                )
            }
            activity_totals: dict[UUID, int] = {}
            for platform_id, content, received_at in session.execute(
                select(
                    InboundRecord.sender_platform_id,
                    InboundRecord.content,
                    InboundRecord.received_at,
                ).where(
                    InboundRecord.received_at >= start,
                    InboundRecord.received_at < end,
                )
            ):
                user = users.get(platform_id)
                if (
                    user is None
                    or received_at < user.joined_at
                    or content.lstrip().startswith("/")
                ):
                    continue
                character_count = len("".join(content.split()))
                if character_count:
                    activity_totals[user.id] = (
                        activity_totals.get(user.id, 0) + character_count
                    )
            for user_id, character_count in activity_totals.items():
                activity = session.scalar(
                    select(DailyActivityRecord).where(
                        DailyActivityRecord.user_id == user_id,
                        DailyActivityRecord.activity_date == now.date(),
                    )
                )
                if activity is None:
                    session.add(
                        DailyActivityRecord(
                            id=uuid4(),
                            user_id=user_id,
                            activity_date=now.date(),
                            character_count=character_count,
                        )
                    )
                else:
                    activity.character_count = character_count
            for checkin in session.scalars(
                select(DailyCheckinRecord).where(
                    DailyCheckinRecord.checkin_date == now.date()
                )
            ):
                income_recorded = session.scalar(
                    select(BalanceTransactionRecord.id).where(
                        BalanceTransactionRecord.user_id == checkin.user_id,
                        BalanceTransactionRecord.source.in_(
                            ("checkin", "checkin_backfill")
                        ),
                        BalanceTransactionRecord.occurred_at >= start,
                        BalanceTransactionRecord.occurred_at < end,
                    )
                )
                if income_recorded is None:
                    session.add(
                        BalanceTransactionRecord(
                            id=uuid4(),
                            user_id=checkin.user_id,
                            amount=settings.checkin_reward,
                            source="checkin_backfill",
                            occurred_at=checkin.checked_in_at,
                        )
                    )

    def _settle_activity_rewards(self, now: datetime) -> None:
        settings = self.get_activity_settings()
        with self._session() as session:
            activities = list(
                session.scalars(
                    select(DailyActivityRecord).where(
                        DailyActivityRecord.activity_date < now.date()
                    )
                )
            )
            dialect_name = session.get_bind().dialect.name
            for activity in activities:
                matching_rules = [
                    rule
                    for rule in settings.rules
                    if rule.character_threshold <= activity.character_count
                ]
                level = 0 if not matching_rules else matching_rules[-1].level
                reward = 0 if not matching_rules else matching_rules[-1].reward
                values = {
                    "id": uuid4(),
                    "user_id": activity.user_id,
                    "activity_date": activity.activity_date,
                    "level": level,
                    "reward": reward,
                    "settled_at": now,
                }
                if dialect_name == "postgresql":
                    statement = postgresql_insert(ActivityRewardSettlementRecord).values(
                        **values
                    )
                elif dialect_name == "sqlite":
                    statement = sqlite_insert(ActivityRewardSettlementRecord).values(
                        **values
                    )
                else:
                    raise ValueError(f"unsupported database dialect: {dialect_name}")
                settlement_id = session.scalar(
                    statement.on_conflict_do_nothing(
                        index_elements=[
                            ActivityRewardSettlementRecord.user_id,
                            ActivityRewardSettlementRecord.activity_date,
                        ]
                    ).returning(ActivityRewardSettlementRecord.id)
                )
                if settlement_id is None:
                    continue
                user = session.get(UserRecord, activity.user_id)
                if user is None:
                    raise RuntimeError("employee disappeared")
                self._apply_balance_change(user, reward, "activity_reward", now)

    def _enqueue_due_income_reports(self, now: datetime) -> None:
        settings = self.get_activity_settings()
        current_time = now.strftime("%H:%M")
        with self._session() as session:
            for report_time in settings.report_times:
                if report_time > current_time:
                    continue
                existing = session.scalar(
                    select(IncomeReportDeliveryRecord).where(
                        IncomeReportDeliveryRecord.report_date == now.date(),
                        IncomeReportDeliveryRecord.report_time == report_time,
                    )
                )
                if existing is not None:
                    continue
                rankings = self._income_rankings(session, now)
                if not rankings:
                    session.add(
                        IncomeReportDeliveryRecord(
                            report_date=now.date(),
                            report_time=report_time,
                            status="skipped",
                        )
                    )
                    continue
                outbound = OutboundRecord(
                    inbound_message_id=None,
                    text=self._income_report_text(rankings, report_time),
                )
                session.add(outbound)
                session.flush()
                session.add(
                    IncomeReportDeliveryRecord(
                        report_date=now.date(),
                        report_time=report_time,
                        status="queued",
                        outbound_message_id=outbound.id,
                    )
                )

    def _income_rankings(self, session: Session, now: datetime) -> list[tuple[str, int]]:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        income = func.sum(BalanceTransactionRecord.amount).label("income")
        return [
            (display_name, int(total))
            for display_name, total in session.execute(
                select(UserRecord.display_name, income)
                .join(
                    BalanceTransactionRecord,
                    BalanceTransactionRecord.user_id == UserRecord.id,
                )
                .where(
                    BalanceTransactionRecord.amount > 0,
                    BalanceTransactionRecord.occurred_at >= start,
                    BalanceTransactionRecord.occurred_at < end,
                )
                .group_by(UserRecord.id, UserRecord.display_name)
                .order_by(income.desc(), UserRecord.id)
                .limit(10)
            )
        ]

    def _income_report_text(
        self, rankings: list[tuple[str, int]], report_time: str
    ) -> str:
        currency_name = self.get_game_settings().currency_name
        lines = [f"今日收益榜（{report_time}）"]
        lines.extend(
            f"{index}. {display_name}：{income} {currency_name}"
            for index, (display_name, income) in enumerate(rankings, start=1)
        )
        return "\n".join(lines)

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
        with self.transaction():
            with self._session() as session:
                existing = session.scalar(
                    select(UserRecord).where(UserRecord.platform_id == platform_id)
                )
                if existing is not None:
                    return existing, False
                record = UserRecord(
                    platform_id=platform_id,
                    display_name=display_name,
                    balance=0,
                    joined_at=joined_at,
                )
                session.add(record)
                session.flush()
                self._apply_balance_change(
                    record, initial_balance, "onboarding", joined_at
                )
                return record, True

    def check_in(self, user: UserRecord, checked_in_at: datetime, reward: int) -> bool:
        with self.transaction():
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
                self._apply_balance_change(employee, reward, "checkin", checked_in_at)
                session.flush()
                return True

    def list_users(self) -> list[UserRecord]:
        with self._session() as session:
            return list(
                session.scalars(select(UserRecord).order_by(UserRecord.joined_at))
            )

    def list_users_page(
        self, page: int, page_size: int
    ) -> tuple[list[UserRecord], int]:
        with self._session() as session:
            total = int(session.scalar(select(func.count()).select_from(UserRecord)) or 0)
            users = list(
                session.scalars(
                    select(UserRecord)
                    .order_by(UserRecord.joined_at.desc(), UserRecord.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            return users, total

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

    def list_active_items_page(
        self, page: int, page_size: int
    ) -> tuple[list[ItemRecord], int]:
        with self._session() as session:
            query = select(ItemRecord).where(ItemRecord.enabled.is_(True))
            total = int(
                session.scalar(select(func.count()).select_from(query.subquery())) or 0
            )
            items = list(
                session.scalars(
                    query.order_by(ItemRecord.created_at.desc(), ItemRecord.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            return items, total

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
