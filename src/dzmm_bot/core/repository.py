from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from secrets import choice, randbelow
from uuid import UUID, uuid4

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, aliased, sessionmaker

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
    HideAndSeekDailyPlayRecord,
    HideAndSeekGameRecord,
    HideAndSeekSceneRecord,
    HideAndSeekSettingsRecord,
    IncomeReportDeliveryRecord,
    IncomeReportScheduleRecord,
    InboundRecord,
    ItemRecord,
    ManualLoginLeaseRecord,
    MemoryAssessmentDailyPlayRecord,
    MemoryAssessmentGameRecord,
    MemoryAssessmentLevelRuleRecord,
    MemoryAssessmentParticipantRecord,
    MemoryAssessmentRoundRecord,
    MemoryAssessmentSettingsRecord,
    OutboundRecord,
    RandomEventScheduleRecord,
    RandomEventDetailRecord,
    RandomEventRecord,
    RandomEventParticipantRecord,
    RandomEventSeatRecord,
    RandomEventSceneRecord,
    RandomEventSceneOpeningRecord,
    RandomEventSceneSeatRecord,
    RandomEventSettingsRecord,
    UserItemRecord,
    UserRecord,
    WeeklyAttendanceSettlementRecord,
    WorkerCommandRecord,
    WorkerInstanceRecord,
)


_DEFAULT_CURRENCY_NAME = "摸鱼币"
_DEFAULT_ONBOARDING_BONUS = 0
_DEFAULT_CHECKIN_REWARD = 5
_DEFAULT_WEEKLY_ATTENDANCE_REWARD = 5
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
_DEFAULT_RANDOM_EVENT_START_TIME = "10:00"
_DEFAULT_RANDOM_EVENT_END_TIME = "24:00"
_DEFAULT_RANDOM_EVENT_COUNT = 1
_DEFAULT_RANDOM_EVENT_MINIMUM_INTERVAL_MINUTES = 60
_DEFAULT_RANDOM_EVENT_SIGNUP_TIMEOUT_MINUTES = 15
_DEFAULT_RANDOM_EVENT_REMINDER_INTERVAL_MINUTES = 5
_DEFAULT_RANDOM_EVENT_TIMES = ("00:00", "02:00", "10:00", "14:00", "16:00", "20:00")
_DEFAULT_RANDOM_EVENT_SIGNUP_NOTICE_TEMPLATE = (
    "可选身份：{可选身份}\n"
    "请使用 /加入 身份 报名，报名将在 {报名截止分钟} 分钟后截止。"
)
_DEFAULT_HIDE_AND_SEEK_ENTRY_FEE = 1
_DEFAULT_HIDE_AND_SEEK_WIN_REWARD = 3
_DEFAULT_HIDE_AND_SEEK_DAILY_LIMIT = 2
_DEFAULT_HIDE_AND_SEEK_SELECTION_TIMEOUT_MINUTES = 2
_DEFAULT_HIDE_AND_SEEK_SCENES = (
    "公司前台",
    "茶水间",
    "开放办公区",
    "会议室",
    "总监办公室",
    "资料室",
    "健身房",
    "公司天台",
    "楼下公园",
    "员工休息室",
)
_DEFAULT_MEMORY_ASSESSMENT_LEVELS = (
    (1, 5, 1),
    (2, 7, 2),
    (3, 9, 3),
    (4, 11, 4),
    (5, 13, 5),
)
_DEFAULT_MEMORY_ASSESSMENT_CHARACTER_SET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%&*_ -"
).replace(" ", "")
_ROLE_VARIABLE = re.compile(r"\{([^{}]*\S[^{}]*)\}")


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
class RandomEventSettings:
    schedule_times: list[str]
    signup_notice_template: str
    signup_timeout_minutes: int
    reminder_interval_minutes: int


@dataclass(frozen=True)
class HideAndSeekSettings:
    enabled: bool
    entry_fee: int
    win_reward: int
    daily_limit: int
    selection_timeout_minutes: int


@dataclass(frozen=True)
class HideAndSeekScene:
    id: UUID
    name: str
    enabled: bool


@dataclass(frozen=True)
class HideAndSeekGameResult:
    status: str
    display_name: str | None = None
    candidates: tuple[str, ...] = ()
    patrol_numbers: tuple[int, ...] = ()
    patrol_scenes: tuple[str, ...] = ()
    balance: int | None = None
    entry_fee: int = 0
    win_reward: int = 0
    selection_timeout_minutes: int = 0


@dataclass(frozen=True)
class MemoryAssessmentSettings:
    enabled: bool
    single_daily_limit: int
    single_recall_seconds: int
    duel_recall_seconds: int
    duel_difficulty_level: int
    duel_base_pool: int
    duel_wrong_freeze: int
    duel_wrong_limit: int
    duel_answer_timeout_minutes: int
    character_set: str


@dataclass(frozen=True)
class MemoryAssessmentLevelRule:
    level: int
    answer_length: int
    reward: int


@dataclass(frozen=True)
class MemoryAssessmentGame:
    id: UUID
    mode: str
    state: str
    level: int | None
    reward: int
    base_pool: int


@dataclass(frozen=True)
class MemoryAssessmentParticipant:
    user_id: UUID
    state: str
    wrong_count: int
    frozen_amount: int


@dataclass(frozen=True)
class MemoryAssessmentRound:
    id: UUID
    game_id: UUID
    sequence: int
    answer: str
    display_seconds: int
    state: str


@dataclass(frozen=True)
class MemoryAssessmentGameResult:
    status: str
    display_name: str | None = None
    game_id: UUID | None = None
    round_id: UUID | None = None
    answer: str | None = None
    level: int | None = None
    reward: int = 0
    balance: int | None = None
    display_seconds: int = 0


@dataclass(frozen=True)
class RandomEventSchedule:
    id: UUID
    event_date: date
    scheduled_at: datetime
    status: str
    scene_name: str | None = None
    event_name: str | None = None
    is_cross_day: bool = False


@dataclass(frozen=True)
class RandomEventTemplate:
    name: str
    opening_text: str


@dataclass(frozen=True)
class RandomEventSeatRule:
    role: str
    capacity: int


@dataclass(frozen=True)
class RandomEventScene:
    id: UUID
    name: str
    signup_text: str
    openings: list[str]
    events: list[RandomEventTemplate]
    reward: int
    target_rounds: int
    enabled: bool
    seats: list[RandomEventSeatRule]


@dataclass(frozen=True)
class PersonalActivity:
    level: int
    reward: int


@dataclass(frozen=True)
class ManualLoginLease:
    operator_id: str
    operator_name: str
    expires_at: datetime


class ManualLoginBusyError(RuntimeError):
    pass


class ManualLoginOwnerError(RuntimeError):
    pass


_COMMAND_DEFINITIONS = (
    ("/入职", "登记群成员为摸鱼公司员工"),
    ("/我的物品", "查看自己持有的物品"),
    ("/打卡", "每日领取 5 摸鱼币"),
    ("/余额", "查看当前摸鱼币余额"),
    ("/我", "查看余额、今日活跃度和今日收益"),
    ("/商店", "查看当前上架物品"),
    ("/帮助", "查看当前可用指令"),
    ("/加入", "加入当前随机事件的指定角色"),
    ("/退出", "退出当前随机事件并结算奖励"),
    ("/摸鱼躲猫猫", "发起单人躲猫猫小游戏；选择时发送 /躲 序号"),
    ("/记忆考核", "发起单人记忆考核，或使用 /记忆考核 对战 发起双人对战"),
    ("/继续", "继续当前单人记忆考核"),
    ("/收手", "结算当前单人记忆考核的奖励"),
    ("/投降", "退出当前记忆考核对战"),
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
                    weekly_attendance_reward=_DEFAULT_WEEKLY_ATTENDANCE_REWARD,
                )
                session.add(record)
                session.flush()
            return record

    def get_random_event_settings(self) -> RandomEventSettings:
        with self._session() as session:
            record = session.get(RandomEventSettingsRecord, 1)
            if record is None:
                record = RandomEventSettingsRecord(
                    id=1,
                    start_time=_DEFAULT_RANDOM_EVENT_START_TIME,
                    end_time=_DEFAULT_RANDOM_EVENT_END_TIME,
                    events_per_day=_DEFAULT_RANDOM_EVENT_COUNT,
                    minimum_interval_minutes=_DEFAULT_RANDOM_EVENT_MINIMUM_INTERVAL_MINUTES,
                    schedule_times=list(_DEFAULT_RANDOM_EVENT_TIMES),
                    signup_notice_template=_DEFAULT_RANDOM_EVENT_SIGNUP_NOTICE_TEMPLATE,
                    signup_timeout_minutes=_DEFAULT_RANDOM_EVENT_SIGNUP_TIMEOUT_MINUTES,
                    reminder_interval_minutes=_DEFAULT_RANDOM_EVENT_REMINDER_INTERVAL_MINUTES,
                )
                session.add(record)
                session.flush()
            return _random_event_settings(record)

    def set_random_event_settings(
        self,
        schedule_times: list[str],
        signup_notice_template: str,
        signup_timeout_minutes: int,
        reminder_interval_minutes: int,
    ) -> RandomEventSettings:
        if not isinstance(schedule_times, list) or not schedule_times:
            raise ValueError("每日固定场次至少需要一个时间")
        if any(_event_time_minutes(value) is None for value in schedule_times):
            raise ValueError("固定场次必须使用 HH:mm 格式")
        normalized_times = sorted(set(schedule_times))
        if len(normalized_times) != len(schedule_times):
            raise ValueError("固定场次不能重复")
        signup_notice_template = _validate_signup_notice_template(signup_notice_template)
        if not isinstance(signup_timeout_minutes, int) or signup_timeout_minutes < 1:
            raise ValueError("报名超时至少为 1 分钟")
        if not isinstance(reminder_interval_minutes, int) or reminder_interval_minutes < 1:
            raise ValueError("提醒间隔至少为 1 分钟")
        with self._session() as session:
            record = session.get(RandomEventSettingsRecord, 1)
            if record is None:
                record = RandomEventSettingsRecord(
                    id=1,
                    start_time=_DEFAULT_RANDOM_EVENT_START_TIME,
                    end_time=_DEFAULT_RANDOM_EVENT_END_TIME,
                    events_per_day=_DEFAULT_RANDOM_EVENT_COUNT,
                    minimum_interval_minutes=_DEFAULT_RANDOM_EVENT_MINIMUM_INTERVAL_MINUTES,
                    schedule_times=list(_DEFAULT_RANDOM_EVENT_TIMES),
                    signup_notice_template=_DEFAULT_RANDOM_EVENT_SIGNUP_NOTICE_TEMPLATE,
                    signup_timeout_minutes=_DEFAULT_RANDOM_EVENT_SIGNUP_TIMEOUT_MINUTES,
                    reminder_interval_minutes=_DEFAULT_RANDOM_EVENT_REMINDER_INTERVAL_MINUTES,
                )
                session.add(record)
            record.schedule_times = normalized_times
            record.signup_notice_template = signup_notice_template
            record.signup_timeout_minutes = signup_timeout_minutes
            record.reminder_interval_minutes = reminder_interval_minutes
            session.flush()
            return _random_event_settings(record)

    def get_memory_assessment_settings(self) -> MemoryAssessmentSettings:
        with self._session() as session:
            record = session.get(MemoryAssessmentSettingsRecord, 1)
            if record is None:
                record = MemoryAssessmentSettingsRecord(
                    id=1,
                    enabled=True,
                    single_daily_limit=1,
                    single_recall_seconds=3,
                    duel_recall_seconds=3,
                    duel_difficulty_level=5,
                    duel_base_pool=5,
                    duel_wrong_freeze=1,
                    duel_wrong_limit=10,
                    duel_answer_timeout_minutes=10,
                    character_set=_DEFAULT_MEMORY_ASSESSMENT_CHARACTER_SET,
                )
                session.add(record)
            if not session.scalar(select(MemoryAssessmentLevelRuleRecord.level).limit(1)):
                session.add_all(
                    [
                        MemoryAssessmentLevelRuleRecord(
                            level=level,
                            answer_length=answer_length,
                            reward=reward,
                        )
                        for level, answer_length, reward in _DEFAULT_MEMORY_ASSESSMENT_LEVELS
                    ]
                )
            session.flush()
            return _memory_assessment_settings(record)

    def list_memory_assessment_levels(self) -> list[MemoryAssessmentLevelRule]:
        self.get_memory_assessment_settings()
        with self._session() as session:
            records = list(
                session.scalars(
                    select(MemoryAssessmentLevelRuleRecord).order_by(
                        MemoryAssessmentLevelRuleRecord.level
                    )
                )
            )
            return [_memory_assessment_level_rule(record) for record in records]

    def set_memory_assessment_settings(
        self,
        *,
        enabled: bool = True,
        single_daily_limit: int,
        single_recall_seconds: int,
        duel_recall_seconds: int,
        duel_difficulty_level: int,
        duel_base_pool: int,
        duel_wrong_freeze: int,
        duel_wrong_limit: int,
        duel_answer_timeout_minutes: int,
        character_set: str,
        levels: list[MemoryAssessmentLevelRule],
    ) -> MemoryAssessmentSettings:
        _validate_memory_assessment_settings(
            single_daily_limit=single_daily_limit,
            single_recall_seconds=single_recall_seconds,
            duel_recall_seconds=duel_recall_seconds,
            duel_difficulty_level=duel_difficulty_level,
            duel_base_pool=duel_base_pool,
            duel_wrong_freeze=duel_wrong_freeze,
            duel_wrong_limit=duel_wrong_limit,
            duel_answer_timeout_minutes=duel_answer_timeout_minutes,
            character_set=character_set,
            levels=levels,
        )
        if not isinstance(enabled, bool):
            raise ValueError("玩法开关无效")
        self.get_memory_assessment_settings()
        with self._session() as session:
            record = session.get(MemoryAssessmentSettingsRecord, 1)
            if record is None:
                raise RuntimeError("记忆考核设置消失")
            record.enabled = enabled
            record.single_daily_limit = single_daily_limit
            record.single_recall_seconds = single_recall_seconds
            record.duel_recall_seconds = duel_recall_seconds
            record.duel_difficulty_level = duel_difficulty_level
            record.duel_base_pool = duel_base_pool
            record.duel_wrong_freeze = duel_wrong_freeze
            record.duel_wrong_limit = duel_wrong_limit
            record.duel_answer_timeout_minutes = duel_answer_timeout_minutes
            record.character_set = character_set
            session.execute(delete(MemoryAssessmentLevelRuleRecord))
            session.add_all(
                [
                    MemoryAssessmentLevelRuleRecord(
                        level=rule.level,
                        answer_length=rule.answer_length,
                        reward=rule.reward,
                    )
                    for rule in levels
                ]
            )
            session.flush()
            return _memory_assessment_settings(record)

    def start_memory_assessment_single(
        self, platform_id: str, now: datetime
    ) -> MemoryAssessmentGameResult:
        now = now.astimezone(BEIJING)
        with self.transaction():
            settings = self.get_memory_assessment_settings()
            with self._session() as session:
                user = session.scalar(
                    select(UserRecord)
                    .where(UserRecord.platform_id == platform_id)
                    .with_for_update()
                )
                if user is None:
                    return MemoryAssessmentGameResult("not_joined")
                if not settings.enabled:
                    return MemoryAssessmentGameResult(
                        "disabled", display_name=user.display_name
                    )
                active = session.scalar(
                    select(MemoryAssessmentGameRecord)
                    .where(MemoryAssessmentGameRecord.active_key == "global")
                    .with_for_update()
                )
                if active is not None:
                    return MemoryAssessmentGameResult(
                        "already_active", display_name=user.display_name
                    )
                daily = session.scalar(
                    select(MemoryAssessmentDailyPlayRecord)
                    .where(
                        MemoryAssessmentDailyPlayRecord.user_id == user.id,
                        MemoryAssessmentDailyPlayRecord.play_date == now.date(),
                    )
                    .with_for_update()
                )
                if daily is not None and daily.count >= settings.single_daily_limit:
                    return MemoryAssessmentGameResult(
                        "daily_limit", display_name=user.display_name
                    )
                if daily is None:
                    daily = MemoryAssessmentDailyPlayRecord(
                        user_id=user.id, play_date=now.date(), count=0
                    )
                    session.add(daily)
                rule = session.get(MemoryAssessmentLevelRuleRecord, 1)
                if rule is None:
                    raise RuntimeError("记忆考核等级规则消失")
                game = MemoryAssessmentGameRecord(
                    mode="single",
                    state="showing_answer",
                    active_key="global",
                    play_date=now.date(),
                    level=rule.level,
                    reward=rule.reward,
                    base_pool=0,
                    created_at=now,
                )
                session.add(game)
                session.flush()
                answer = _memory_assessment_answer(
                    settings.character_set, rule.answer_length
                )
                round_record = MemoryAssessmentRoundRecord(
                    game_id=game.id,
                    sequence=rule.level,
                    answer=answer,
                    display_seconds=settings.single_recall_seconds,
                    state="showing",
                )
                session.add(round_record)
                session.add(
                    MemoryAssessmentParticipantRecord(
                        game_id=game.id,
                        user_id=user.id,
                        state="active",
                        wrong_count=0,
                        frozen_amount=0,
                    )
                )
                daily.count += 1
                session.flush()
                return MemoryAssessmentGameResult(
                    "started",
                    display_name=user.display_name,
                    game_id=game.id,
                    round_id=round_record.id,
                    answer=answer,
                    level=rule.level,
                    reward=rule.reward,
                    balance=user.balance,
                    display_seconds=settings.single_recall_seconds,
                )

    def mark_memory_assessment_round_recalled(
        self, round_id: UUID, now: datetime
    ) -> MemoryAssessmentRound:
        now = now.astimezone(BEIJING)
        with self.transaction():
            with self._session() as session:
                round_record = session.get(
                    MemoryAssessmentRoundRecord, round_id, with_for_update=True
                )
                if round_record is None:
                    raise ValueError("记忆考核轮次不存在")
                game = session.get(
                    MemoryAssessmentGameRecord, round_record.game_id, with_for_update=True
                )
                if game is None or game.state != "showing_answer":
                    raise ValueError("记忆考核轮次不在展示中")
                if round_record.state != "showing":
                    raise ValueError("记忆考核轮次无法撤回")
                round_record.state = "awaiting_answer"
                game.state = "awaiting_answer"
                session.flush()
                return _memory_assessment_round(round_record)

    def start_memory_assessment_duel(
        self, platform_id: str, now: datetime
    ) -> MemoryAssessmentGameResult:
        now = now.astimezone(BEIJING)
        with self.transaction():
            settings = self.get_memory_assessment_settings()
            with self._session() as session:
                user = session.scalar(
                    select(UserRecord)
                    .where(UserRecord.platform_id == platform_id)
                    .with_for_update()
                )
                if user is None:
                    return MemoryAssessmentGameResult("not_joined")
                if not settings.enabled:
                    return MemoryAssessmentGameResult(
                        "disabled", display_name=user.display_name
                    )
                if session.scalar(
                    select(MemoryAssessmentGameRecord)
                    .where(MemoryAssessmentGameRecord.active_key == "global")
                    .with_for_update()
                ) is not None:
                    return MemoryAssessmentGameResult(
                        "already_active", display_name=user.display_name
                    )
                rule = session.get(
                    MemoryAssessmentLevelRuleRecord, settings.duel_difficulty_level
                )
                if rule is None:
                    raise RuntimeError("记忆考核多人难度规则消失")
                game = MemoryAssessmentGameRecord(
                    mode="duel",
                    state="waiting_opponent",
                    active_key="global",
                    play_date=now.date(),
                    level=rule.level,
                    reward=0,
                    base_pool=0,
                    created_at=now,
                )
                session.add(game)
                session.flush()
                session.add(
                    MemoryAssessmentParticipantRecord(
                        game_id=game.id,
                        user_id=user.id,
                        state="waiting",
                        wrong_count=0,
                        frozen_amount=0,
                    )
                )
                return MemoryAssessmentGameResult(
                    "waiting_opponent",
                    display_name=user.display_name,
                    game_id=game.id,
                    level=rule.level,
                )

    def join_memory_assessment_duel(
        self, platform_id: str, now: datetime
    ) -> MemoryAssessmentGameResult:
        now = now.astimezone(BEIJING)
        with self.transaction():
            settings = self.get_memory_assessment_settings()
            with self._session() as session:
                user = session.scalar(
                    select(UserRecord)
                    .where(UserRecord.platform_id == platform_id)
                    .with_for_update()
                )
                if user is None:
                    return MemoryAssessmentGameResult("not_joined")
                game = session.scalar(
                    select(MemoryAssessmentGameRecord)
                    .where(MemoryAssessmentGameRecord.active_key == "global")
                    .with_for_update()
                )
                if game is None or game.mode != "duel" or game.state != "waiting_opponent":
                    return MemoryAssessmentGameResult(
                        "no_duel", display_name=user.display_name
                    )
                participants = list(
                    session.scalars(
                        select(MemoryAssessmentParticipantRecord)
                        .where(MemoryAssessmentParticipantRecord.game_id == game.id)
                        .with_for_update()
                    )
                )
                if any(participant.user_id == user.id for participant in participants):
                    return MemoryAssessmentGameResult(
                        "already_joined", display_name=user.display_name
                    )
                if len(participants) != 1:
                    raise RuntimeError("记忆考核对局参与者数量异常")
                opponent = session.get(UserRecord, participants[0].user_id, with_for_update=True)
                if opponent is None:
                    raise RuntimeError("记忆考核对手消失")
                self._apply_balance_change(
                    opponent,
                    -settings.duel_base_pool,
                    "memory_assessment_duel_pool",
                    now,
                )
                self._apply_balance_change(
                    user,
                    -settings.duel_base_pool,
                    "memory_assessment_duel_pool",
                    now,
                )
                participants[0].state = "active"
                participants[0].frozen_amount = settings.duel_base_pool
                game.state = "showing_answer"
                game.base_pool = settings.duel_base_pool * 2
                game.answer_deadline = now + timedelta(
                    minutes=settings.duel_answer_timeout_minutes
                )
                answer = _memory_assessment_answer(
                    settings.character_set,
                    int(
                        session.get(
                            MemoryAssessmentLevelRuleRecord, game.level
                        ).answer_length
                    ),
                )
                round_record = MemoryAssessmentRoundRecord(
                    game_id=game.id,
                    sequence=1,
                    answer=answer,
                    display_seconds=settings.duel_recall_seconds,
                    state="showing",
                )
                session.add(round_record)
                session.add(
                    MemoryAssessmentParticipantRecord(
                        game_id=game.id,
                        user_id=user.id,
                        state="active",
                        wrong_count=0,
                        frozen_amount=settings.duel_base_pool,
                    )
                )
                session.flush()
                return MemoryAssessmentGameResult(
                    "duel_started",
                    display_name=user.display_name,
                    game_id=game.id,
                    round_id=round_record.id,
                    answer=answer,
                    level=game.level,
                    reward=game.base_pool,
                    balance=user.balance,
                    display_seconds=settings.duel_recall_seconds,
                )

    def surrender_memory_assessment_duel(
        self, platform_id: str, now: datetime
    ) -> MemoryAssessmentGameResult:
        now = now.astimezone(BEIJING)
        with self.transaction():
            with self._session() as session:
                user = session.scalar(
                    select(UserRecord)
                    .where(UserRecord.platform_id == platform_id)
                    .with_for_update()
                )
                if user is None:
                    return MemoryAssessmentGameResult("not_joined")
                game = self._active_memory_assessment(session, user.id)
                if game is None or game.mode != "duel" or game.state == "waiting_opponent":
                    return MemoryAssessmentGameResult(
                        "cannot_surrender", display_name=user.display_name
                    )
                participant = self._memory_assessment_participant(session, game.id, user.id)
                if participant.state != "active":
                    return MemoryAssessmentGameResult(
                        "cannot_surrender", display_name=user.display_name
                    )
                participant.state = "surrendered"
                winner = self._remaining_memory_assessment_duel_participant(session, game.id)
                if winner is None:
                    return self._collect_memory_assessment_duel_pool(session, game, now)
                return self._finish_memory_assessment_duel_with_winner(
                    session, game, winner, now
                )

    def expire_memory_assessment_duels(self, now: datetime) -> list[MemoryAssessmentGameResult]:
        now = now.astimezone(BEIJING)
        expired = []
        with self.transaction():
            with self._session() as session:
                games = list(
                    session.scalars(
                        select(MemoryAssessmentGameRecord)
                        .where(
                            MemoryAssessmentGameRecord.mode == "duel",
                            MemoryAssessmentGameRecord.active_key == "global",
                            MemoryAssessmentGameRecord.answer_deadline <= now,
                        )
                        .with_for_update()
                    )
                )
                for game in games:
                    expired.append(
                        self._collect_memory_assessment_duel_pool(session, game, now)
                    )
        return expired

    def answer_memory_assessment(
        self, platform_id: str, answer: str, now: datetime
    ) -> MemoryAssessmentGameResult:
        now = now.astimezone(BEIJING)
        with self.transaction():
            with self._session() as session:
                user = session.scalar(
                    select(UserRecord)
                    .where(UserRecord.platform_id == platform_id)
                    .with_for_update()
                )
                if user is None:
                    return MemoryAssessmentGameResult("not_joined")
                game = self._active_memory_assessment(session, user.id)
                if game is None:
                    return MemoryAssessmentGameResult(
                        "no_active_game", display_name=user.display_name
                    )
                if game.mode == "duel":
                    return self._answer_memory_assessment_duel(session, user, game, answer, now)
                round_record = session.scalar(
                    select(MemoryAssessmentRoundRecord)
                    .where(MemoryAssessmentRoundRecord.game_id == game.id)
                    .order_by(MemoryAssessmentRoundRecord.sequence.desc())
                    .with_for_update()
                )
                if round_record is None:
                    raise RuntimeError("记忆考核答案轮次消失")
                if game.state != "awaiting_answer" or round_record.state != "awaiting_answer":
                    return MemoryAssessmentGameResult(
                        "answer_not_ready",
                        display_name=user.display_name,
                        game_id=game.id,
                        round_id=round_record.id,
                        level=game.level,
                        reward=game.reward,
                    )
                if answer != round_record.answer:
                    round_record.state = "failed"
                    game.state = "failed"
                    game.active_key = None
                    game.finished_at = now
                    self._memory_assessment_participant(session, game.id, user.id).state = "failed"
                    return MemoryAssessmentGameResult(
                        "failed",
                        display_name=user.display_name,
                        game_id=game.id,
                        round_id=round_record.id,
                        level=game.level,
                        reward=game.reward,
                        balance=user.balance,
                    )
                round_record.state = "answered"
                is_final_level = session.scalar(
                    select(MemoryAssessmentLevelRuleRecord.level)
                    .where(MemoryAssessmentLevelRuleRecord.level > game.level)
                    .limit(1)
                ) is None
                if not is_final_level:
                    game.state = "awaiting_decision"
                    return MemoryAssessmentGameResult(
                        "correct",
                        display_name=user.display_name,
                        game_id=game.id,
                        round_id=round_record.id,
                        level=game.level,
                        reward=game.reward,
                        balance=user.balance,
                    )
                self._apply_balance_change(
                    user, game.reward, "memory_assessment_single_reward", now
                )
                game.state = "settled"
                game.active_key = None
                game.finished_at = now
                self._memory_assessment_participant(session, game.id, user.id).state = "settled"
                return MemoryAssessmentGameResult(
                    "completed",
                    display_name=user.display_name,
                    game_id=game.id,
                    round_id=round_record.id,
                    level=game.level,
                    reward=game.reward,
                    balance=user.balance,
                )

    def continue_memory_assessment(
        self, platform_id: str, now: datetime
    ) -> MemoryAssessmentGameResult:
        now = now.astimezone(BEIJING)
        with self.transaction():
            settings = self.get_memory_assessment_settings()
            with self._session() as session:
                user = session.scalar(
                    select(UserRecord)
                    .where(UserRecord.platform_id == platform_id)
                    .with_for_update()
                )
                if user is None:
                    return MemoryAssessmentGameResult("not_joined")
                game = self._active_memory_assessment_single(session, user.id)
                if game is None or game.state != "awaiting_decision":
                    return MemoryAssessmentGameResult(
                        "cannot_continue", display_name=user.display_name
                    )
                next_rule = session.get(
                    MemoryAssessmentLevelRuleRecord, int(game.level or 0) + 1
                )
                if next_rule is None:
                    raise RuntimeError("记忆考核已无下一等级")
                answer = _memory_assessment_answer(
                    settings.character_set, next_rule.answer_length
                )
                game.state = "showing_answer"
                game.level = next_rule.level
                game.reward = next_rule.reward
                round_record = MemoryAssessmentRoundRecord(
                    game_id=game.id,
                    sequence=next_rule.level,
                    answer=answer,
                    display_seconds=settings.single_recall_seconds,
                    state="showing",
                )
                session.add(round_record)
                session.flush()
                return MemoryAssessmentGameResult(
                    "continued",
                    display_name=user.display_name,
                    game_id=game.id,
                    round_id=round_record.id,
                    answer=answer,
                    level=next_rule.level,
                    reward=next_rule.reward,
                    balance=user.balance,
                    display_seconds=settings.single_recall_seconds,
                )

    def cash_out_memory_assessment(
        self, platform_id: str, now: datetime
    ) -> MemoryAssessmentGameResult:
        now = now.astimezone(BEIJING)
        with self.transaction():
            with self._session() as session:
                user = session.scalar(
                    select(UserRecord)
                    .where(UserRecord.platform_id == platform_id)
                    .with_for_update()
                )
                if user is None:
                    return MemoryAssessmentGameResult("not_joined")
                game = self._active_memory_assessment_single(session, user.id)
                if game is None or game.state != "awaiting_decision":
                    return MemoryAssessmentGameResult(
                        "cannot_cash_out", display_name=user.display_name
                    )
                self._apply_balance_change(
                    user, game.reward, "memory_assessment_single_reward", now
                )
                game.state = "settled"
                game.active_key = None
                game.finished_at = now
                self._memory_assessment_participant(session, game.id, user.id).state = "settled"
                return MemoryAssessmentGameResult(
                    "cashed_out",
                    display_name=user.display_name,
                    game_id=game.id,
                    level=game.level,
                    reward=game.reward,
                    balance=user.balance,
                )

    def _active_memory_assessment_single(
        self, session: Session, user_id: UUID
    ) -> MemoryAssessmentGameRecord | None:
        return session.scalar(
            select(MemoryAssessmentGameRecord)
            .join(
                MemoryAssessmentParticipantRecord,
                MemoryAssessmentParticipantRecord.game_id
                == MemoryAssessmentGameRecord.id,
            )
            .where(
                MemoryAssessmentGameRecord.mode == "single",
                MemoryAssessmentGameRecord.active_key == "global",
                MemoryAssessmentParticipantRecord.user_id == user_id,
            )
            .with_for_update()
        )

    def _active_memory_assessment(
        self, session: Session, user_id: UUID
    ) -> MemoryAssessmentGameRecord | None:
        return session.scalar(
            select(MemoryAssessmentGameRecord)
            .join(
                MemoryAssessmentParticipantRecord,
                MemoryAssessmentParticipantRecord.game_id
                == MemoryAssessmentGameRecord.id,
            )
            .where(
                MemoryAssessmentGameRecord.active_key == "global",
                MemoryAssessmentParticipantRecord.user_id == user_id,
            )
            .with_for_update()
        )

    def _answer_memory_assessment_duel(
        self,
        session: Session,
        user: UserRecord,
        game: MemoryAssessmentGameRecord,
        answer: str,
        now: datetime,
    ) -> MemoryAssessmentGameResult:
        participant = self._memory_assessment_participant(session, game.id, user.id)
        round_record = session.scalar(
            select(MemoryAssessmentRoundRecord)
            .where(MemoryAssessmentRoundRecord.game_id == game.id)
            .with_for_update()
        )
        if round_record is None:
            raise RuntimeError("记忆考核对局答案轮次消失")
        if game.state != "awaiting_answer" or round_record.state != "awaiting_answer":
            return MemoryAssessmentGameResult(
                "answer_not_ready",
                display_name=user.display_name,
                game_id=game.id,
                round_id=round_record.id,
            )
        if participant.state != "active":
            return MemoryAssessmentGameResult(
                "duel_disqualified", display_name=user.display_name, game_id=game.id
            )
        if answer == round_record.answer:
            round_record.state = "answered"
            return self._finish_memory_assessment_duel_with_winner(
                session, game, participant, now
            )
        settings = self.get_memory_assessment_settings()
        participant.wrong_count += 1
        participant.frozen_amount += settings.duel_wrong_freeze
        game.base_pool += settings.duel_wrong_freeze
        self._apply_balance_change(
            user,
            -settings.duel_wrong_freeze,
            "memory_assessment_duel_wrong",
            now,
        )
        if participant.wrong_count < settings.duel_wrong_limit:
            return MemoryAssessmentGameResult(
                "duel_incorrect",
                display_name=user.display_name,
                game_id=game.id,
                reward=game.base_pool,
                balance=user.balance,
            )
        participant.state = "disqualified"
        winner = self._remaining_memory_assessment_duel_participant(session, game.id)
        if winner is None:
            return self._collect_memory_assessment_duel_pool(session, game, now)
        return self._finish_memory_assessment_duel_with_winner(session, game, winner, now)

    def _remaining_memory_assessment_duel_participant(
        self, session: Session, game_id: UUID
    ) -> MemoryAssessmentParticipantRecord | None:
        participants = list(
            session.scalars(
                select(MemoryAssessmentParticipantRecord)
                .where(
                    MemoryAssessmentParticipantRecord.game_id == game_id,
                    MemoryAssessmentParticipantRecord.state == "active",
                )
                .with_for_update()
            )
        )
        return participants[0] if len(participants) == 1 else None

    def _finish_memory_assessment_duel_with_winner(
        self,
        session: Session,
        game: MemoryAssessmentGameRecord,
        winner: MemoryAssessmentParticipantRecord,
        now: datetime,
    ) -> MemoryAssessmentGameResult:
        user = session.get(UserRecord, winner.user_id, with_for_update=True)
        if user is None:
            raise RuntimeError("记忆考核胜者消失")
        winner.state = "winner"
        for participant in session.scalars(
            select(MemoryAssessmentParticipantRecord).where(
                MemoryAssessmentParticipantRecord.game_id == game.id,
                MemoryAssessmentParticipantRecord.id != winner.id,
                MemoryAssessmentParticipantRecord.state == "active",
            )
        ):
            participant.state = "lost"
        self._apply_balance_change(
            user, game.base_pool, "memory_assessment_duel_reward", now
        )
        game.state = "settled"
        game.active_key = None
        game.winner_user_id = user.id
        game.finished_at = now
        return MemoryAssessmentGameResult(
            "duel_won",
            display_name=user.display_name,
            game_id=game.id,
            level=game.level,
            reward=game.base_pool,
            balance=user.balance,
        )

    def _collect_memory_assessment_duel_pool(
        self, session: Session, game: MemoryAssessmentGameRecord, now: datetime
    ) -> MemoryAssessmentGameResult:
        game.state = "collected"
        game.active_key = None
        game.finished_at = now
        return MemoryAssessmentGameResult(
            "duel_collected", game_id=game.id, reward=game.base_pool
        )

    def _memory_assessment_participant(
        self, session: Session, game_id: UUID, user_id: UUID
    ) -> MemoryAssessmentParticipantRecord:
        participant = session.scalar(
            select(MemoryAssessmentParticipantRecord)
            .where(
                MemoryAssessmentParticipantRecord.game_id == game_id,
                MemoryAssessmentParticipantRecord.user_id == user_id,
            )
            .with_for_update()
        )
        if participant is None:
            raise RuntimeError("记忆考核参与者消失")
        return participant

    def get_hide_and_seek_settings(self) -> HideAndSeekSettings:
        with self._session() as session:
            record = session.get(HideAndSeekSettingsRecord, 1)
            if record is None:
                record = HideAndSeekSettingsRecord(
                    id=1,
                    enabled=True,
                    entry_fee=_DEFAULT_HIDE_AND_SEEK_ENTRY_FEE,
                    win_reward=_DEFAULT_HIDE_AND_SEEK_WIN_REWARD,
                    daily_limit=_DEFAULT_HIDE_AND_SEEK_DAILY_LIMIT,
                    selection_timeout_minutes=_DEFAULT_HIDE_AND_SEEK_SELECTION_TIMEOUT_MINUTES,
                )
                session.add(record)
                session.add_all(
                    [HideAndSeekSceneRecord(name=name) for name in _DEFAULT_HIDE_AND_SEEK_SCENES]
                )
                session.flush()
            return _hide_and_seek_settings(record)

    def set_hide_and_seek_settings(
        self,
        enabled: bool,
        entry_fee: int,
        win_reward: int,
        daily_limit: int,
        selection_timeout_minutes: int,
    ) -> HideAndSeekSettings:
        if not isinstance(enabled, bool):
            raise ValueError("玩法开关无效")
        if not isinstance(entry_fee, int) or not 0 <= entry_fee <= 999:
            raise ValueError("入场费需在 0 至 999 之间")
        if not isinstance(win_reward, int) or not 0 <= win_reward <= 999:
            raise ValueError("胜利奖励需在 0 至 999 之间")
        if not isinstance(daily_limit, int) or not 1 <= daily_limit <= 99:
            raise ValueError("每日次数需在 1 至 99 之间")
        if (
            not isinstance(selection_timeout_minutes, int)
            or not 1 <= selection_timeout_minutes <= 60
        ):
            raise ValueError("选择超时需在 1 至 60 分钟之间")
        self.get_hide_and_seek_settings()
        with self._session() as session:
            record = session.get(HideAndSeekSettingsRecord, 1)
            if record is None:
                raise RuntimeError("躲猫猫设置消失")
            record.enabled = enabled
            record.entry_fee = entry_fee
            record.win_reward = win_reward
            record.daily_limit = daily_limit
            record.selection_timeout_minutes = selection_timeout_minutes
            session.flush()
            return _hide_and_seek_settings(record)

    def list_hide_and_seek_scenes_page(
        self, page: int, page_size: int
    ) -> tuple[list[HideAndSeekScene], int]:
        self.get_hide_and_seek_settings()
        with self._session() as session:
            total = int(
                session.scalar(select(func.count()).select_from(HideAndSeekSceneRecord))
                or 0
            )
            records = list(
                session.scalars(
                    select(HideAndSeekSceneRecord)
                    .order_by(HideAndSeekSceneRecord.name)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            return [_hide_and_seek_scene(record) for record in records], total

    def create_hide_and_seek_scene(self, name: str) -> HideAndSeekScene:
        name = _validate_hide_and_seek_scene_name(name)
        self.get_hide_and_seek_settings()
        with self._session() as session:
            if session.scalar(
                select(HideAndSeekSceneRecord.id).where(HideAndSeekSceneRecord.name == name)
            ) is not None:
                raise ValueError("地点名称已存在")
            record = HideAndSeekSceneRecord(name=name)
            session.add(record)
            session.flush()
            return _hide_and_seek_scene(record)

    def update_hide_and_seek_scene(
        self, scene_id: UUID, name: str, enabled: bool
    ) -> HideAndSeekScene:
        name = _validate_hide_and_seek_scene_name(name)
        if not isinstance(enabled, bool):
            raise ValueError("地点状态无效")
        self.get_hide_and_seek_settings()
        with self._session() as session:
            record = session.get(HideAndSeekSceneRecord, scene_id)
            if record is None:
                raise ValueError("躲猫猫地点不存在")
            if session.scalar(
                select(HideAndSeekSceneRecord.id).where(
                    HideAndSeekSceneRecord.name == name,
                    HideAndSeekSceneRecord.id != scene_id,
                )
            ) is not None:
                raise ValueError("地点名称已存在")
            record.name = name
            record.enabled = enabled
            session.flush()
            return _hide_and_seek_scene(record)

    def delete_hide_and_seek_scene(self, scene_id: UUID) -> bool:
        self.get_hide_and_seek_settings()
        with self._session() as session:
            record = session.get(HideAndSeekSceneRecord, scene_id)
            if record is None:
                return False
            session.delete(record)
            return True

    def start_hide_and_seek(
        self, platform_id: str, now: datetime
    ) -> HideAndSeekGameResult:
        now = now.astimezone(BEIJING)
        with self.transaction():
            settings = self.get_hide_and_seek_settings()
            with self._session() as session:
                user = session.scalar(
                    select(UserRecord)
                    .where(UserRecord.platform_id == platform_id)
                    .with_for_update()
                )
                if user is None:
                    return HideAndSeekGameResult("not_joined")
                if not settings.enabled:
                    return HideAndSeekGameResult("disabled", display_name=user.display_name)
                if self._active_random_event(session) is not None:
                    return HideAndSeekGameResult(
                        "random_event_active", display_name=user.display_name
                    )
                active = session.scalar(
                    select(HideAndSeekGameRecord)
                    .where(
                        HideAndSeekGameRecord.user_id == user.id,
                        HideAndSeekGameRecord.state == "selecting",
                    )
                    .with_for_update()
                )
                if active is not None:
                    return HideAndSeekGameResult("already_active", display_name=user.display_name)
                scenes = list(
                    session.scalars(
                        select(HideAndSeekSceneRecord)
                        .where(HideAndSeekSceneRecord.enabled.is_(True))
                        .order_by(HideAndSeekSceneRecord.name)
                    )
                )
                if len(scenes) < 7:
                    return HideAndSeekGameResult(
                        "not_enough_scenes", display_name=user.display_name
                    )
                play_date = now.date()
                daily = session.scalar(
                    select(HideAndSeekDailyPlayRecord)
                    .where(
                        HideAndSeekDailyPlayRecord.user_id == user.id,
                        HideAndSeekDailyPlayRecord.play_date == play_date,
                    )
                    .with_for_update()
                )
                if daily is not None and daily.count >= settings.daily_limit:
                    return HideAndSeekGameResult("daily_limit", display_name=user.display_name)
                if daily is None:
                    daily = HideAndSeekDailyPlayRecord(
                        user_id=user.id, play_date=play_date, count=0
                    )
                    session.add(daily)
                candidates = _sample_distinct([scene.name for scene in scenes], 7)
                daily.count += 1
                session.add(
                    HideAndSeekGameRecord(
                        user_id=user.id,
                        play_date=play_date,
                        state="selecting",
                        candidates=candidates,
                        entry_fee=settings.entry_fee,
                        win_reward=settings.win_reward,
                        choice_deadline=now + timedelta(minutes=settings.selection_timeout_minutes),
                    )
                )
                return HideAndSeekGameResult(
                    "started",
                    display_name=user.display_name,
                    candidates=tuple(candidates),
                    balance=user.balance,
                    entry_fee=settings.entry_fee,
                    win_reward=settings.win_reward,
                )

    def choose_hide_and_seek(
        self, platform_id: str, scene_number: int, now: datetime
    ) -> HideAndSeekGameResult:
        now = now.astimezone(BEIJING)
        with self.transaction():
            with self._session() as session:
                user = session.scalar(
                    select(UserRecord)
                    .where(UserRecord.platform_id == platform_id)
                    .with_for_update()
                )
                if user is None:
                    return HideAndSeekGameResult("not_joined")
                game = session.scalar(
                    select(HideAndSeekGameRecord)
                    .where(
                        HideAndSeekGameRecord.user_id == user.id,
                        HideAndSeekGameRecord.state == "selecting",
                    )
                    .with_for_update()
                )
                if game is None:
                    return HideAndSeekGameResult("no_active_game", display_name=user.display_name)
                if game.choice_deadline <= now:
                    self._cancel_hide_and_seek_game(session, user, game, now)
                    return HideAndSeekGameResult("expired", display_name=user.display_name)
                if not isinstance(scene_number, int) or not 1 <= scene_number <= len(game.candidates):
                    return HideAndSeekGameResult("invalid_scene", display_name=user.display_name)
                first_patrol_numbers = _sample_distinct(
                    list(range(1, len(game.candidates) + 1)), 3
                )
                game.selected_number = scene_number
                patrol_numbers = first_patrol_numbers
                game.finished_at = now
                if scene_number in first_patrol_numbers:
                    game.state = "found"
                else:
                    remaining_numbers = [
                        number
                        for number in range(1, len(game.candidates) + 1)
                        if number not in first_patrol_numbers
                    ]
                    second_patrol_numbers = _sample_distinct(remaining_numbers, 2)
                    patrol_numbers = first_patrol_numbers + second_patrol_numbers
                    game.state = "found" if scene_number in second_patrol_numbers else "won"
                game.patrol_numbers = patrol_numbers
                if game.state == "found":
                    self._apply_balance_change(
                        user, -game.entry_fee, "hide_and_seek_penalty", now
                    )
                else:
                    self._apply_balance_change(user, game.win_reward, "hide_and_seek_win", now)
                patrol_scenes = tuple(game.candidates[number - 1] for number in patrol_numbers)
                return HideAndSeekGameResult(
                    game.state,
                    display_name=user.display_name,
                    patrol_numbers=tuple(patrol_numbers),
                    patrol_scenes=patrol_scenes,
                    balance=user.balance,
                    entry_fee=game.entry_fee,
                    win_reward=game.win_reward,
                )

    def expire_hide_and_seek_games(self, now: datetime) -> list[HideAndSeekGameResult]:
        now = now.astimezone(BEIJING)
        cancelled = []
        with self.transaction():
            with self._session() as session:
                games = list(
                    session.scalars(
                        select(HideAndSeekGameRecord)
                        .where(
                            HideAndSeekGameRecord.state == "selecting",
                            HideAndSeekGameRecord.choice_deadline <= now,
                        )
                        .with_for_update()
                    )
                )
                for game in games:
                    user = session.get(UserRecord, game.user_id, with_for_update=True)
                    if user is None:
                        continue
                    self._cancel_hide_and_seek_game(session, user, game, now)
                    cancelled.append(
                        HideAndSeekGameResult(
                            "cancelled",
                            display_name=user.display_name,
                            entry_fee=game.entry_fee,
                            selection_timeout_minutes=int(
                                (game.choice_deadline - game.created_at).total_seconds() // 60
                            ),
                        )
                    )
        return cancelled

    def _cancel_hide_and_seek_game(
        self,
        session: Session,
        user: UserRecord,
        game: HideAndSeekGameRecord,
        now: datetime,
    ) -> None:
        if game.state != "selecting":
            return
        game.state = "cancelled"
        game.finished_at = now
        daily = session.scalar(
            select(HideAndSeekDailyPlayRecord)
            .where(
                HideAndSeekDailyPlayRecord.user_id == user.id,
                HideAndSeekDailyPlayRecord.play_date == game.play_date,
            )
            .with_for_update()
        )
        if daily is not None and daily.count > 0:
            daily.count -= 1

    def schedule_random_events(self, now: datetime) -> list[RandomEventSchedule]:
        now = now.astimezone(BEIJING)
        settings = self.get_random_event_settings()
        with self._session() as session:
            existing = list(
                session.scalars(
                    select(RandomEventScheduleRecord)
                    .where(RandomEventScheduleRecord.event_date == now.date())
                    .order_by(RandomEventScheduleRecord.scheduled_at)
                )
            )
            if existing:
                for record in existing:
                    if record.status == "pending" and record.scene_name is None:
                        self._fill_random_event_schedule_snapshot(session, record)
                return [_random_event_schedule(record) for record in existing]
            records = []
            for scheduled_time in settings.schedule_times:
                minute = _event_time_minutes(scheduled_time)
                if minute is None:
                    raise RuntimeError("random event schedule disappeared")
                scheduled_at = now.replace(
                    hour=minute // 60,
                    minute=minute % 60,
                    second=0,
                    microsecond=0,
                )
                record = RandomEventScheduleRecord(
                    event_date=now.date(),
                    scheduled_at=scheduled_at,
                    status="skipped" if scheduled_at < now.replace(second=0, microsecond=0) else "pending",
                )
                session.add(record)
                self._fill_random_event_schedule_snapshot(session, record)
                records.append(record)
            session.flush()
            return [_random_event_schedule(record) for record in records]

    def list_today_random_event_schedules(
        self, now: datetime
    ) -> list[RandomEventSchedule]:
        now = now.astimezone(BEIJING)
        with self._session() as session:
            records = list(
                session.scalars(
                    select(RandomEventScheduleRecord)
                    .where(RandomEventScheduleRecord.event_date == now.date())
                    .order_by(RandomEventScheduleRecord.scheduled_at)
                )
            )
            carryover = session.scalar(
                select(RandomEventScheduleRecord)
                .join(RandomEventRecord, RandomEventRecord.schedule_id == RandomEventScheduleRecord.id)
                .where(
                    RandomEventRecord.state.in_(("signup", "in_progress")),
                    RandomEventScheduleRecord.event_date < now.date(),
                )
                .order_by(RandomEventScheduleRecord.scheduled_at)
            )
            if carryover is not None:
                records.insert(0, carryover)
            names = {
                schedule_id: (scene_name, event_name)
                for schedule_id, scene_name, event_name in session.execute(
                    select(
                        RandomEventRecord.schedule_id,
                        RandomEventRecord.scene_name,
                        RandomEventRecord.event_name,
                    ).where(
                        RandomEventRecord.schedule_id.in_([record.id for record in records])
                    )
                )
            }
            return [
                _random_event_schedule(
                    record,
                    *(names.get(record.id, (None, None))),
                    is_cross_day=record.id == getattr(carryover, "id", None),
                )
                for record in records
            ]

    def reschedule_random_event(
        self, schedule_id: UUID, scheduled_at: datetime, now: datetime
    ) -> RandomEventSchedule:
        now = now.astimezone(BEIJING)
        scheduled_at = scheduled_at.astimezone(BEIJING).replace(second=0, microsecond=0)
        if scheduled_at.date() != now.date() or scheduled_at <= now:
            raise ValueError("调整时间必须是今日未来时刻")
        with self._session() as session:
            record = session.get(RandomEventScheduleRecord, schedule_id)
            if record is None:
                raise ValueError("随机事件不存在")
            if record.event_date != now.date() or record.status != "pending":
                raise ValueError("仅待开始事件可以调整")
            conflict = session.scalar(
                select(RandomEventScheduleRecord.id).where(
                    RandomEventScheduleRecord.event_date == now.date(),
                    RandomEventScheduleRecord.id != record.id,
                    RandomEventScheduleRecord.scheduled_at == scheduled_at,
                )
            )
            if conflict is not None:
                raise ValueError("今日已有该时刻的随机事件")
            record.scheduled_at = scheduled_at
            session.flush()
            return _random_event_schedule(record)

    def create_today_random_event(
        self, scene_id: UUID, event_name: str, scheduled_at: datetime, now: datetime
    ) -> RandomEventSchedule:
        now = now.astimezone(BEIJING)
        scheduled_at = scheduled_at.astimezone(BEIJING).replace(second=0, microsecond=0)
        if scheduled_at.date() != now.date() or scheduled_at <= now:
            raise ValueError("补充时间必须是今日未来时刻")
        with self._session() as session:
            if session.scalar(
                select(RandomEventScheduleRecord.id).where(
                    RandomEventScheduleRecord.event_date == now.date(),
                    RandomEventScheduleRecord.scheduled_at == scheduled_at,
                )
            ) is not None:
                raise ValueError("今日已有该时刻的随机事件")
            scene = session.get(RandomEventSceneRecord, scene_id)
            if scene is None or not scene.enabled:
                raise ValueError("场景不存在或已停用")
            template = session.scalar(
                select(RandomEventSceneOpeningRecord).where(
                    RandomEventSceneOpeningRecord.scene_id == scene.id,
                    RandomEventSceneOpeningRecord.name == event_name,
                )
            )
            if template is None:
                raise ValueError("事件模板不存在")
            seats = list(
                session.scalars(
                    select(RandomEventSceneSeatRecord)
                    .where(RandomEventSceneSeatRecord.scene_id == scene.id)
                    .order_by(RandomEventSceneSeatRecord.role)
                )
            )
            record = RandomEventScheduleRecord(
                event_date=now.date(), scheduled_at=scheduled_at, status="pending"
            )
            session.add(record)
            self._set_random_event_schedule_snapshot(session, record, scene, template, seats)
            session.flush()
            return _random_event_schedule(record)

    def delete_today_random_event(self, schedule_id: UUID, now: datetime) -> bool:
        now = now.astimezone(BEIJING)
        with self._session() as session:
            record = session.get(RandomEventScheduleRecord, schedule_id)
            if (
                record is None
                or record.event_date != now.date()
                or record.status != "pending"
            ):
                return False
            session.delete(record)
            return True

    def trigger_random_event(
        self, schedule_id: UUID, now: datetime
    ) -> RandomEventSchedule:
        now = now.astimezone(BEIJING)
        with self.transaction():
            with self._session() as session:
                schedule = session.get(RandomEventScheduleRecord, schedule_id, with_for_update=True)
                if schedule is None or schedule.event_date != now.date() or schedule.status != "pending":
                    raise ValueError("仅待开始事件可以立即触发")
                if self._active_random_event(session) is not None:
                    raise ValueError("当前已有进行中的随机事件")
                if not self._fill_random_event_schedule_snapshot(session, schedule):
                    schedule.status = "skipped"
                    raise ValueError("没有可用的随机事件场景")
                self._start_random_event_from_schedule(session, schedule, now)
                return _random_event_schedule(schedule)

    def create_random_event_scene(
        self,
        name: str,
        signup_text: str,
        openings: list[str | dict[str, str]],
        reward: int,
        target_rounds: int,
        seats: list[tuple[str, int]],
    ) -> RandomEventScene:
        name = name.strip()
        signup_text = signup_text.strip()
        rules, templates = _validate_random_event_scene(
            name, signup_text, openings, reward, target_rounds, seats
        )
        with self._session() as session:
            if session.scalar(
                select(RandomEventSceneRecord.id).where(
                    RandomEventSceneRecord.name == name
                )
            ) is not None:
                raise ValueError("场景名称已存在")
            record = RandomEventSceneRecord(
                name=name,
                signup_text=signup_text,
                reward=reward,
                target_rounds=target_rounds,
            )
            session.add(record)
            session.flush()
            session.add_all(
                [
                    RandomEventSceneSeatRecord(
                        scene_id=record.id, role=rule.role, capacity=rule.capacity
                    )
                    for rule in rules
                ]
            )
            session.add_all(
                [
                    RandomEventSceneOpeningRecord(
                        scene_id=record.id,
                        position=position,
                        name=template.name,
                        content=template.opening_text,
                    )
                    for position, template in enumerate(templates)
                ]
            )
            session.flush()
            return _random_event_scene(record, rules, templates)

    def list_random_event_scenes(self) -> list[RandomEventScene]:
        scenes, _ = self.list_random_event_scenes_page(1, 100)
        return scenes

    def list_random_event_scenes_page(
        self, page: int, page_size: int
    ) -> tuple[list[RandomEventScene], int]:
        with self._session() as session:
            records = list(
                session.scalars(
                    select(RandomEventSceneRecord).order_by(
                        RandomEventSceneRecord.created_at.desc(),
                        RandomEventSceneRecord.id.desc(),
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            total = int(
                session.scalar(
                    select(func.count()).select_from(RandomEventSceneRecord)
                )
                or 0
            )
            seats_by_scene: dict[UUID, list[RandomEventSeatRule]] = {
                record.id: [] for record in records
            }
            templates_by_scene: dict[UUID, list[RandomEventTemplate]] = {
                record.id: [] for record in records
            }
            for seat in session.scalars(
                select(RandomEventSceneSeatRecord)
                .where(RandomEventSceneSeatRecord.scene_id.in_(seats_by_scene))
                .order_by(
                    RandomEventSceneSeatRecord.scene_id,
                    RandomEventSceneSeatRecord.role,
                )
            ):
                seats_by_scene[seat.scene_id].append(
                    RandomEventSeatRule(seat.role, seat.capacity)
                )
            for opening in session.scalars(
                select(RandomEventSceneOpeningRecord)
                .where(RandomEventSceneOpeningRecord.scene_id.in_(templates_by_scene))
                .order_by(
                    RandomEventSceneOpeningRecord.scene_id,
                    RandomEventSceneOpeningRecord.position,
                )
            ):
                templates_by_scene[opening.scene_id].append(
                    RandomEventTemplate(opening.name, opening.content)
                )
            return (
                [
                    _random_event_scene(
                        record, seats_by_scene[record.id], templates_by_scene[record.id]
                    )
                    for record in records
                ],
                total,
            )

    def update_random_event_scene(
        self,
        scene_id: UUID,
        name: str,
        signup_text: str,
        openings: list[str | dict[str, str]],
        reward: int,
        target_rounds: int,
        seats: list[tuple[str, int]],
        enabled: bool,
    ) -> RandomEventScene:
        name = name.strip()
        signup_text = signup_text.strip()
        rules, templates = _validate_random_event_scene(
            name, signup_text, openings, reward, target_rounds, seats
        )
        with self._session() as session:
            record = session.get(RandomEventSceneRecord, scene_id, with_for_update=True)
            if record is None:
                raise ValueError("场景不存在")
            if session.scalar(
                select(RandomEventSceneRecord.id).where(
                    RandomEventSceneRecord.name == name,
                    RandomEventSceneRecord.id != scene_id,
                )
            ) is not None:
                raise ValueError("场景名称已存在")
            record.name = name
            record.signup_text = signup_text
            record.reward = reward
            record.target_rounds = target_rounds
            record.enabled = enabled
            session.execute(
                delete(RandomEventSceneSeatRecord).where(
                    RandomEventSceneSeatRecord.scene_id == scene_id
                )
            )
            session.execute(
                delete(RandomEventSceneOpeningRecord).where(
                    RandomEventSceneOpeningRecord.scene_id == scene_id
                )
            )
            session.add_all(
                [
                    RandomEventSceneSeatRecord(
                        scene_id=scene_id, role=rule.role, capacity=rule.capacity
                    )
                    for rule in rules
                ]
            )
            session.add_all(
                [
                    RandomEventSceneOpeningRecord(
                        scene_id=scene_id,
                        position=position,
                        name=template.name,
                        content=template.opening_text,
                    )
                    for position, template in enumerate(templates)
                ]
            )
            session.flush()
            return _random_event_scene(record, rules, templates)

    def delete_random_event_scene(self, scene_id: UUID) -> bool:
        with self._session() as session:
            record = session.get(RandomEventSceneRecord, scene_id, with_for_update=True)
            if record is None:
                return False
            session.execute(
                delete(RandomEventSceneSeatRecord).where(
                    RandomEventSceneSeatRecord.scene_id == scene_id
                )
            )
            session.execute(
                delete(RandomEventSceneOpeningRecord).where(
                    RandomEventSceneOpeningRecord.scene_id == scene_id
                )
            )
            session.delete(record)
            return True

    def run_random_event_jobs(self, now: datetime) -> None:
        now = now.astimezone(BEIJING)
        with self.transaction():
            self.schedule_random_events(now)
            with self._session() as session:
                active = session.scalar(
                    select(RandomEventRecord)
                    .where(RandomEventRecord.state.in_(("signup", "in_progress")))
                    .order_by(RandomEventRecord.started_at)
                    .with_for_update()
                )
                if active is not None and active.state == "signup":
                    if active.signup_deadline <= now:
                        self._finish_random_event(session, active, "dissolved", now)
                        self.enqueue_system_outbound(
                            f"【随机事件：{active.scene_name}】报名超时，事件已解散。"
                        )
                        active = None
                    elif (
                        active.next_reminder_at is not None
                        and active.next_reminder_at <= now
                    ):
                        open_seats = self._random_event_open_seats(session, active.id)
                        self.enqueue_system_outbound(
                            f"【随机事件：{active.scene_name}】仍在报名。\n"
                            f"剩余可选身份：{open_seats}"
                        )
                        settings = self.get_random_event_settings()
                        active.next_reminder_at = now + timedelta(
                            minutes=settings.reminder_interval_minutes
                        )
                due_schedules = list(
                    session.scalars(
                        select(RandomEventScheduleRecord)
                        .where(
                            RandomEventScheduleRecord.status == "pending",
                            RandomEventScheduleRecord.event_date == now.date(),
                            RandomEventScheduleRecord.scheduled_at <= now,
                        )
                        .order_by(RandomEventScheduleRecord.scheduled_at)
                        .with_for_update()
                    )
                )
                for schedule in due_schedules:
                    if active is not None:
                        schedule.status = "skipped"
                        continue
                    if not self._fill_random_event_schedule_snapshot(session, schedule):
                        schedule.status = "skipped"
                        continue
                    active = self._start_random_event_from_schedule(session, schedule, now)

    def join_random_event(self, platform_id: str, role: str, now: datetime) -> str:
        role = role.strip()
        now = now.astimezone(BEIJING)
        with self.transaction():
            with self._session() as session:
                user = session.scalar(
                    select(UserRecord).where(UserRecord.platform_id == platform_id)
                )
                if user is None:
                    return "not_joined"
                event = self._active_random_event(session)
                if event is None:
                    return "no_event"
                if event.state != "signup":
                    return "event_started"
                participant = session.scalar(
                    select(RandomEventParticipantRecord).where(
                        RandomEventParticipantRecord.event_id == event.id,
                        RandomEventParticipantRecord.user_id == user.id,
                    )
                )
                if participant is not None:
                    return "already_joined"
                seat = session.scalar(
                    select(RandomEventSeatRecord).where(
                        RandomEventSeatRecord.event_id == event.id,
                        RandomEventSeatRecord.role == role,
                    )
                )
                if seat is None:
                    return "unknown_role"
                occupied = int(
                    session.scalar(
                        select(func.count())
                        .select_from(RandomEventParticipantRecord)
                        .where(
                            RandomEventParticipantRecord.event_id == event.id,
                            RandomEventParticipantRecord.role == role,
                            RandomEventParticipantRecord.left_at.is_(None),
                        )
                    )
                    or 0
                )
                if occupied >= seat.capacity:
                    return "role_full"
                session.add(
                    RandomEventParticipantRecord(
                        event_id=event.id, user_id=user.id, role=role, joined_at=now
                    )
                )
                session.flush()
                if self._random_event_is_full(session, event.id):
                    event.state = "in_progress"
                    event.formal_opening_text = _render_random_event_formal_opening(
                        session, event
                    )
                    schedule = session.get(RandomEventScheduleRecord, event.schedule_id)
                    if schedule is not None:
                        schedule.status = "in_progress"
                    self.enqueue_system_outbound(
                        f"【随机事件：{event.scene_name}－{event.event_name or '未命名事件'}】人员已齐，事件开始。\n"
                        f"{event.formal_opening_text}"
                    )
                    return "started"
                return "joined"

    def record_random_event_round(
        self, platform_id: str, now: datetime, content: str
    ) -> str:
        classification = self.classify_random_event_message(platform_id, content)
        if classification != "participant":
            return classification
        with self._session() as session:
            event = self._active_random_event(session)
            if event is None or event.state != "in_progress":
                return "none"
            user = session.scalar(
                select(UserRecord).where(UserRecord.platform_id == platform_id)
            )
            if user is None:
                return "observer_invalid"
            participant = session.scalar(
                select(RandomEventParticipantRecord).where(
                    RandomEventParticipantRecord.event_id == event.id,
                    RandomEventParticipantRecord.user_id == user.id,
                    RandomEventParticipantRecord.left_at.is_(None),
                )
            )
            if participant is not None:
                participant.rounds += 1
                position = int(
                    session.scalar(
                        select(func.count())
                        .select_from(RandomEventDetailRecord)
                        .where(RandomEventDetailRecord.event_id == event.id)
                    )
                    or 0
                )
                session.add(
                    RandomEventDetailRecord(
                        event_id=event.id,
                        user_id=user.id,
                        display_name=user.display_name,
                        content=content,
                        occurred_at=now.astimezone(BEIJING),
                        position=position,
                    )
                )
                return "participant"
        return "observer_invalid"

    def classify_random_event_message(self, platform_id: str, content: str) -> str:
        if content.lstrip().startswith("/") or not content.strip():
            return "none"
        with self._session() as session:
            event = self._active_random_event(session)
            if event is None or event.state != "in_progress":
                return "none"
            user = session.scalar(
                select(UserRecord).where(UserRecord.platform_id == platform_id)
            )
            if user is not None:
                participant = session.scalar(
                    select(RandomEventParticipantRecord).where(
                        RandomEventParticipantRecord.event_id == event.id,
                        RandomEventParticipantRecord.user_id == user.id,
                        RandomEventParticipantRecord.left_at.is_(None),
                    )
                )
                if participant is not None:
                    return "participant"
        if _is_parenthesized_observer_message(content):
            return "observer_valid"
        return "observer_invalid"

    def leave_random_event(self, platform_id: str, now: datetime) -> str:
        now = now.astimezone(BEIJING)
        with self.transaction():
            with self._session() as session:
                event = self._active_random_event(session)
                if event is None:
                    return "no_event"
                user = session.scalar(
                    select(UserRecord).where(UserRecord.platform_id == platform_id)
                )
                if user is None:
                    return "not_joined"
                participant = session.scalar(
                    select(RandomEventParticipantRecord).where(
                        RandomEventParticipantRecord.event_id == event.id,
                        RandomEventParticipantRecord.user_id == user.id,
                        RandomEventParticipantRecord.left_at.is_(None),
                    )
                )
                if participant is None:
                    return "not_participating"
                participant.left_at = now
                result = "left_signup"
                if event.state == "in_progress":
                    if participant.rounds >= event.target_rounds:
                        self._apply_balance_change(user, event.reward, "random_event", now)
                        participant.rewarded_at = now
                        result = "rewarded"
                    else:
                        result = "left_without_reward"
                    remaining = int(
                        session.scalar(
                            select(func.count())
                            .select_from(RandomEventParticipantRecord)
                            .where(
                                RandomEventParticipantRecord.event_id == event.id,
                                RandomEventParticipantRecord.left_at.is_(None),
                            )
                        )
                        or 0
                    )
                    if remaining == 0:
                        self._finish_random_event(session, event, "ended", now)
                return result

    def last_random_event_reward(self, platform_id: str) -> int:
        with self._session() as session:
            return int(
                session.scalar(
                    select(RandomEventRecord.reward)
                    .join(
                        RandomEventParticipantRecord,
                        RandomEventParticipantRecord.event_id == RandomEventRecord.id,
                    )
                    .join(UserRecord, UserRecord.id == RandomEventParticipantRecord.user_id)
                    .where(
                        UserRecord.platform_id == platform_id,
                        RandomEventParticipantRecord.rewarded_at.is_not(None),
                    )
                    .order_by(RandomEventParticipantRecord.rewarded_at.desc())
                    .limit(1)
                )
                or 0
            )

    def list_random_event_details(self, schedule_id: UUID) -> list[tuple[str, str, datetime]]:
        with self._session() as session:
            event = session.scalar(
                select(RandomEventRecord).where(RandomEventRecord.schedule_id == schedule_id)
            )
            if event is None:
                raise ValueError("随机事件不存在")
            return list(
                session.execute(
                    select(
                        RandomEventDetailRecord.display_name,
                        RandomEventDetailRecord.content,
                        RandomEventDetailRecord.occurred_at,
                    )
                    .where(RandomEventDetailRecord.event_id == event.id)
                    .order_by(RandomEventDetailRecord.position)
                )
            )

    def _fill_random_event_schedule_snapshot(
        self, session: Session, schedule: RandomEventScheduleRecord
    ) -> bool:
        if schedule.scene_name is not None:
            return True
        scenes = list(
            session.scalars(
                select(RandomEventSceneRecord).where(RandomEventSceneRecord.enabled.is_(True))
            )
        )
        if not scenes:
            return False
        scene = scenes[randbelow(len(scenes))]
        templates = list(
            session.scalars(
                select(RandomEventSceneOpeningRecord)
                .where(RandomEventSceneOpeningRecord.scene_id == scene.id)
                .order_by(RandomEventSceneOpeningRecord.position)
            )
        )
        if not templates:
            return False
        template = templates[randbelow(len(templates))]
        seats = list(
            session.scalars(
                select(RandomEventSceneSeatRecord)
                .where(RandomEventSceneSeatRecord.scene_id == scene.id)
                .order_by(RandomEventSceneSeatRecord.role)
            )
        )
        self._set_random_event_schedule_snapshot(session, schedule, scene, template, seats)
        return True

    def _set_random_event_schedule_snapshot(
        self,
        session: Session,
        schedule: RandomEventScheduleRecord,
        scene: RandomEventSceneRecord,
        template: RandomEventSceneOpeningRecord,
        seats: list[RandomEventSceneSeatRecord],
    ) -> None:
        schedule.scene_name = scene.name
        schedule.event_name = template.name
        schedule.signup_text = scene.signup_text
        schedule.signup_notice_template = self.get_random_event_settings().signup_notice_template
        schedule.formal_opening_text = template.content
        schedule.reward = scene.reward
        schedule.target_rounds = scene.target_rounds
        schedule.seats = [{"role": seat.role, "capacity": seat.capacity} for seat in seats]

    def _start_random_event_from_schedule(
        self, session: Session, schedule: RandomEventScheduleRecord, now: datetime
    ) -> RandomEventRecord:
        if any(
            value is None
            for value in (
                schedule.scene_name,
                schedule.event_name,
                schedule.signup_text,
                schedule.formal_opening_text,
                schedule.reward,
                schedule.target_rounds,
                schedule.seats,
            )
        ):
            raise ValueError("随机事件计划缺少快照")
        settings = self.get_random_event_settings()
        active = RandomEventRecord(
            schedule_id=schedule.id,
            state="signup",
            scene_name=schedule.scene_name,
            event_name=schedule.event_name,
            signup_text=schedule.signup_text,
            formal_opening_text=schedule.formal_opening_text,
            reward=schedule.reward,
            target_rounds=schedule.target_rounds,
            signup_deadline=now + timedelta(minutes=settings.signup_timeout_minutes),
            next_reminder_at=now + timedelta(minutes=settings.reminder_interval_minutes),
            started_at=now,
        )
        schedule.status = "signup"
        session.add(active)
        session.flush()
        session.add_all(
            [
                RandomEventSeatRecord(
                    event_id=active.id, role=seat["role"], capacity=seat["capacity"]
                )
                for seat in schedule.seats
            ]
        )
        self.enqueue_system_outbound(
            f"【随机事件：{schedule.scene_name}－{schedule.event_name}】\n{schedule.signup_text}\n"
            + _render_random_event_signup_notice(
                schedule.signup_notice_template or settings.signup_notice_template,
                _random_event_seat_summary(
                    [(seat["role"], seat["capacity"]) for seat in schedule.seats]
                ),
                settings.signup_timeout_minutes,
            )
        )
        return active

    def _active_random_event(self, session: Session) -> RandomEventRecord | None:
        return session.scalar(
            select(RandomEventRecord)
            .where(RandomEventRecord.state.in_(("signup", "in_progress")))
            .order_by(RandomEventRecord.started_at)
            .with_for_update()
        )

    def _random_event_is_full(self, session: Session, event_id: UUID) -> bool:
        for seat in session.scalars(
            select(RandomEventSeatRecord).where(RandomEventSeatRecord.event_id == event_id)
        ):
            occupied = int(
                session.scalar(
                    select(func.count())
                    .select_from(RandomEventParticipantRecord)
                    .where(
                        RandomEventParticipantRecord.event_id == event_id,
                        RandomEventParticipantRecord.role == seat.role,
                        RandomEventParticipantRecord.left_at.is_(None),
                    )
                )
                or 0
            )
            if occupied < seat.capacity:
                return False
        return True

    def _random_event_open_seats(self, session: Session, event_id: UUID) -> str:
        remaining = []
        for seat in session.scalars(
            select(RandomEventSeatRecord)
            .where(RandomEventSeatRecord.event_id == event_id)
            .order_by(RandomEventSeatRecord.role)
        ):
            occupied = int(
                session.scalar(
                    select(func.count())
                    .select_from(RandomEventParticipantRecord)
                    .where(
                        RandomEventParticipantRecord.event_id == event_id,
                        RandomEventParticipantRecord.role == seat.role,
                        RandomEventParticipantRecord.left_at.is_(None),
                    )
                )
                or 0
            )
            if occupied < seat.capacity:
                remaining.append((seat.role, seat.capacity - occupied))
        return _random_event_seat_summary(remaining)

    def random_event_open_seats(self) -> str:
        with self._session() as session:
            event = session.scalar(
                select(RandomEventRecord)
                .where(RandomEventRecord.state == "signup")
                .order_by(RandomEventRecord.started_at)
            )
            if event is None:
                return "已满员"
            return self._random_event_open_seats(session, event.id)

    def _finish_random_event(
        self, session: Session, event: RandomEventRecord, state: str, now: datetime
    ) -> None:
        event.state = state
        event.ended_at = now
        schedule = session.get(RandomEventScheduleRecord, event.schedule_id)
        if schedule is not None:
            schedule.status = state

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
            for game in self.expire_hide_and_seek_games(now):
                self.enqueue_system_outbound(
                    f"【摸鱼躲猫猫】{game.display_name} 未在 {game.selection_timeout_minutes} 分钟内选择地点，本局已取消，次数已返还。"
                )
            for game in self.expire_memory_assessment_duels(now):
                self.enqueue_system_outbound(
                    f"【记忆考核对战】作答超时，{game.reward} 摸鱼币奖池已由系统回收。"
                )
            self._settle_weekly_attendance_rewards(now)
            self._settle_activity_rewards(now)
            self._enqueue_due_income_reports(now)
            self.run_random_event_jobs(now)
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

    def _settle_weekly_attendance_rewards(self, now: datetime) -> None:
        if now.weekday() != 0:
            return
        week_start = now.date() - timedelta(days=7)
        week_end = week_start + timedelta(days=7)
        settings = self.get_game_settings()
        with self._session() as session:
            complete_user_ids = session.scalars(
                select(DailyCheckinRecord.user_id)
                .where(
                    DailyCheckinRecord.checkin_date >= week_start,
                    DailyCheckinRecord.checkin_date < week_end,
                )
                .group_by(DailyCheckinRecord.user_id)
                .having(func.count(DailyCheckinRecord.id) == 7)
            )
            dialect_name = session.get_bind().dialect.name
            for user_id in complete_user_ids:
                values = {
                    "id": uuid4(),
                    "user_id": user_id,
                    "week_start": week_start,
                    "reward": settings.weekly_attendance_reward,
                    "settled_at": now,
                }
                if dialect_name == "postgresql":
                    statement = postgresql_insert(WeeklyAttendanceSettlementRecord).values(
                        **values
                    )
                elif dialect_name == "sqlite":
                    statement = sqlite_insert(WeeklyAttendanceSettlementRecord).values(
                        **values
                    )
                else:
                    raise ValueError(f"unsupported database dialect: {dialect_name}")
                settlement_id = session.scalar(
                    statement.on_conflict_do_nothing(
                        index_elements=[
                            WeeklyAttendanceSettlementRecord.user_id,
                            WeeklyAttendanceSettlementRecord.week_start,
                        ]
                    ).returning(WeeklyAttendanceSettlementRecord.id)
                )
                if settlement_id is None:
                    continue
                user = session.get(UserRecord, user_id)
                if user is None:
                    raise RuntimeError("employee disappeared")
                self._apply_balance_change(
                    user, settings.weekly_attendance_reward, "weekly_attendance", now
                )

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
        self,
        currency_name: str,
        onboarding_bonus: int,
        checkin_reward: int,
        weekly_attendance_reward: int,
    ) -> GameSettingsRecord:
        currency_name = currency_name.strip()
        if not 1 <= len(currency_name) <= 12:
            raise ValueError("货币名称需为 1 至 12 个字符")
        if not 0 <= onboarding_bonus <= 999:
            raise ValueError("入职初始余额需在 0 至 999 之间")
        if not 0 <= checkin_reward <= 999:
            raise ValueError("打卡奖励需在 0 至 999 之间")
        if not 0 <= weekly_attendance_reward <= 999:
            raise ValueError("每周全勤奖需在 0 至 999 之间")
        with self._session() as session:
            record = session.get(GameSettingsRecord, 1)
            if record is None:
                record = GameSettingsRecord(id=1)
                session.add(record)
            record.currency_name = currency_name
            record.onboarding_bonus = onboarding_bonus
            record.checkin_reward = checkin_reward
            record.weekly_attendance_reward = weekly_attendance_reward
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

    def consecutive_checkin_days(self, user_id: UUID, now: datetime) -> int:
        today = now.astimezone(BEIJING).date()
        with self._session() as session:
            checkin_dates = set(
                session.scalars(
                    select(DailyCheckinRecord.checkin_date).where(
                        DailyCheckinRecord.user_id == user_id,
                        DailyCheckinRecord.checkin_date <= today,
                    )
                )
            )
        current = today if today in checkin_dates else today - timedelta(days=1)
        days = 0
        while current in checkin_dates:
            days += 1
            current -= timedelta(days=1)
        return days

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
        self,
        inbound_message_id: UUID | str,
        reply: str,
        reply_index: int = 0,
        *,
        recall_after_seconds: int | None = None,
        memory_round_id: UUID | None = None,
    ) -> OutboundRecord:
        if recall_after_seconds is not None and recall_after_seconds < 1:
            raise ValueError("撤回秒数必须为正整数")
        with self._session() as session:
            record = OutboundRecord(
                inbound_message_id=UUID(str(inbound_message_id)),
                text=reply,
                reply_index=reply_index,
                recall_after_seconds=recall_after_seconds,
            )
            session.add(record)
            session.flush()
            if memory_round_id is not None:
                round_record = session.get(
                    MemoryAssessmentRoundRecord, memory_round_id, with_for_update=True
                )
                if round_record is None or round_record.state != "showing":
                    raise ValueError("记忆考核轮次无法关联撤回消息")
                round_record.outbound_message_id = record.id
            return record

    def enqueue_system_outbound(
        self,
        text: str,
        *,
        recall_after_seconds: int | None = None,
        memory_round_id: UUID | None = None,
    ) -> OutboundRecord:
        if recall_after_seconds is not None and recall_after_seconds < 1:
            raise ValueError("撤回秒数必须为正整数")
        with self._session() as session:
            record = OutboundRecord(
                inbound_message_id=None,
                text=text,
                recall_after_seconds=recall_after_seconds,
            )
            session.add(record)
            session.flush()
            if memory_round_id is not None:
                round_record = session.get(
                    MemoryAssessmentRoundRecord, memory_round_id, with_for_update=True
                )
                if round_record is None or round_record.state != "showing":
                    raise ValueError("记忆考核轮次无法关联撤回消息")
                round_record.outbound_message_id = record.id
            return record

    def claim_outbound(
        self, worker_id: str, now: datetime, lease_seconds: int
    ) -> OutboundRecord | None:
        with self._session() as session:
            earlier_reply = aliased(OutboundRecord)
            has_unsent_earlier_reply = exists(
                select(1).where(
                    earlier_reply.inbound_message_id
                    == OutboundRecord.inbound_message_id,
                    earlier_reply.reply_index < OutboundRecord.reply_index,
                    earlier_reply.status != "sent",
                )
            )
            record = session.scalar(
                select(OutboundRecord)
                .where(
                    OutboundRecord.status.in_(("pending", "leased")),
                    or_(
                        OutboundRecord.lease_expires_at.is_(None),
                        OutboundRecord.lease_expires_at <= now,
                    ),
                    or_(
                        OutboundRecord.inbound_message_id.is_(None),
                        ~has_unsent_earlier_reply,
                    ),
                )
                .order_by(
                    OutboundRecord.created_at,
                    OutboundRecord.reply_index,
                    OutboundRecord.id,
                )
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
            record = session.scalar(
                select(OutboundRecord)
                .where(
                    OutboundRecord.id == UUID(str(message_id)),
                    OutboundRecord.status == "leased",
                    OutboundRecord.lease_worker_id == worker_id,
                    OutboundRecord.lease_token == UUID(str(lease_token)),
                    OutboundRecord.lease_expires_at > now,
                )
                .with_for_update()
            )
            if record is None:
                return False
            record.status = "sent"
            record.platform_sent_id = platform_sent_id
            record.lease_worker_id = None
            record.lease_token = None
            record.lease_expires_at = None
            if record.recall_after_seconds is not None:
                record.recall_status = "pending"
                record.recall_due_at = now + timedelta(
                    seconds=record.recall_after_seconds
                )
            return True

    def claim_outbound_recall(
        self, worker_id: str, now: datetime, lease_seconds: int
    ) -> OutboundRecord | None:
        with self._session() as session:
            record = session.scalar(
                select(OutboundRecord)
                .where(
                    OutboundRecord.status == "sent",
                    OutboundRecord.platform_sent_id.is_not(None),
                    OutboundRecord.recall_due_at <= now,
                    OutboundRecord.recall_status.in_(("pending", "leased")),
                    or_(
                        OutboundRecord.recall_lease_expires_at.is_(None),
                        OutboundRecord.recall_lease_expires_at <= now,
                    ),
                )
                .order_by(OutboundRecord.recall_due_at, OutboundRecord.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if record is None:
                return None
            record.recall_status = "leased"
            record.recall_lease_worker_id = worker_id
            record.recall_lease_token = uuid4()
            record.recall_lease_expires_at = now + timedelta(seconds=lease_seconds)
            record.recall_attempt_count += 1
            session.flush()
            return record

    def confirm_outbound_recalled(
        self,
        message_id: UUID | str,
        worker_id: str,
        lease_token: UUID | str,
        now: datetime,
    ) -> bool:
        with self.transaction():
            with self._session() as session:
                record = session.scalar(
                    select(OutboundRecord)
                    .where(
                        OutboundRecord.id == UUID(str(message_id)),
                        OutboundRecord.recall_status == "leased",
                        OutboundRecord.recall_lease_worker_id == worker_id,
                        OutboundRecord.recall_lease_token == UUID(str(lease_token)),
                        OutboundRecord.recall_lease_expires_at > now,
                    )
                    .with_for_update()
                )
                if record is None:
                    return False
                record.recall_status = "recalled"
                record.recalled_at = now
                record.recall_lease_worker_id = None
                record.recall_lease_token = None
                record.recall_lease_expires_at = None
                round_record = session.scalar(
                    select(MemoryAssessmentRoundRecord)
                    .where(MemoryAssessmentRoundRecord.outbound_message_id == record.id)
                    .with_for_update()
                )
                if round_record is not None:
                    game = session.get(
                        MemoryAssessmentGameRecord,
                        round_record.game_id,
                        with_for_update=True,
                    )
                    if game is not None and game.state == "showing_answer":
                        round_record.state = "awaiting_answer"
                        game.state = "awaiting_answer"
                return True

    def start_manual_login(
        self, operator_id: str, operator_name: str, now: datetime
    ) -> ManualLoginLease:
        with self.transaction():
            self._expire_manual_login_lease(now)
            with self._session() as session:
                current = session.scalar(
                    select(ManualLoginLeaseRecord)
                    .where(ManualLoginLeaseRecord.id == 1)
                    .with_for_update()
                )
                if current is not None:
                    raise ManualLoginBusyError("manual login is already active")
                record = ManualLoginLeaseRecord(
                    id=1,
                    operator_id=operator_id,
                    operator_name=operator_name,
                    expires_at=now + timedelta(minutes=3),
                )
                session.add(record)
                self.enqueue_worker_command("start_auth")
                session.flush()
                return ManualLoginLease(
                    record.operator_id, record.operator_name, record.expires_at
                )

    def finish_manual_login(self, operator_id: str, now: datetime) -> None:
        with self.transaction():
            self._expire_manual_login_lease(now)
            with self._session() as session:
                current = session.get(ManualLoginLeaseRecord, 1)
                if current is None or current.operator_id != operator_id:
                    raise ManualLoginOwnerError("manual login is not owned by actor")
                session.delete(current)
                self.enqueue_worker_command("finish_auth")

    def cancel_manual_login(self, now: datetime) -> bool:
        with self.transaction():
            self._expire_manual_login_lease(now)
            with self._session() as session:
                current = session.get(ManualLoginLeaseRecord, 1)
                if current is None:
                    return False
                session.delete(current)
                self.enqueue_worker_command("cancel_auth")
                return True

    def manual_login_lease(self, now: datetime) -> ManualLoginLease | None:
        with self.transaction():
            self._expire_manual_login_lease(now)
            with self._session() as session:
                record = session.get(ManualLoginLeaseRecord, 1)
                if record is None:
                    return None
                return ManualLoginLease(
                    record.operator_id, record.operator_name, record.expires_at
                )

    def _expire_manual_login_lease(self, now: datetime) -> None:
        with self._session() as session:
            current = session.scalar(
                select(ManualLoginLeaseRecord)
                .where(ManualLoginLeaseRecord.id == 1)
                .with_for_update()
            )
            if current is not None and current.expires_at <= now:
                session.delete(current)
                self.enqueue_worker_command("cancel_auth")

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
        with self.transaction():
            self._expire_manual_login_lease(heartbeat.recorded_at)
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


def _event_time_minutes(value: str, *, allow_midnight: bool = False) -> int | None:
    if not isinstance(value, str) or re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) is None:
        if allow_midnight and value == "24:00":
            return 24 * 60
        return None
    return int(value[:2]) * 60 + int(value[3:])


def _validate_signup_notice_template(template: str) -> str:
    if not isinstance(template, str) or not template.strip() or len(template) > 2000:
        raise ValueError("报名补充文案不能为空且不能超过 2000 个字符")
    allowed = {"{可选身份}", "{报名截止分钟}"}
    variables = set(re.findall(r"\{[^{}]+\}", template))
    if not variables.issubset(allowed):
        raise ValueError("报名补充文案包含不支持的变量")
    return template.strip()


def _validate_random_event_capacity(
    start_minutes: int,
    end_minutes: int,
    events_per_day: int,
    minimum_interval_minutes: int,
) -> None:
    if end_minutes - start_minutes - 1 < (events_per_day - 1) * minimum_interval_minutes:
        raise ValueError("时间窗不足以容纳每日次数和最小间隔")


def _random_event_settings(record: RandomEventSettingsRecord) -> RandomEventSettings:
    return RandomEventSettings(
        schedule_times=list(record.schedule_times),
        signup_notice_template=record.signup_notice_template,
        signup_timeout_minutes=record.signup_timeout_minutes,
        reminder_interval_minutes=record.reminder_interval_minutes,
    )


def _hide_and_seek_settings(record: HideAndSeekSettingsRecord) -> HideAndSeekSettings:
    return HideAndSeekSettings(
        enabled=record.enabled,
        entry_fee=record.entry_fee,
        win_reward=record.win_reward,
        daily_limit=record.daily_limit,
        selection_timeout_minutes=record.selection_timeout_minutes,
    )


def _memory_assessment_settings(
    record: MemoryAssessmentSettingsRecord,
) -> MemoryAssessmentSettings:
    return MemoryAssessmentSettings(
        enabled=record.enabled,
        single_daily_limit=record.single_daily_limit,
        single_recall_seconds=record.single_recall_seconds,
        duel_recall_seconds=record.duel_recall_seconds,
        duel_difficulty_level=record.duel_difficulty_level,
        duel_base_pool=record.duel_base_pool,
        duel_wrong_freeze=record.duel_wrong_freeze,
        duel_wrong_limit=record.duel_wrong_limit,
        duel_answer_timeout_minutes=record.duel_answer_timeout_minutes,
        character_set=record.character_set,
    )


def _memory_assessment_level_rule(
    record: MemoryAssessmentLevelRuleRecord,
) -> MemoryAssessmentLevelRule:
    return MemoryAssessmentLevelRule(
        level=record.level,
        answer_length=record.answer_length,
        reward=record.reward,
    )


def _memory_assessment_round(record: MemoryAssessmentRoundRecord) -> MemoryAssessmentRound:
    return MemoryAssessmentRound(
        id=record.id,
        game_id=record.game_id,
        sequence=record.sequence,
        answer=record.answer,
        display_seconds=record.display_seconds,
        state=record.state,
    )


def _memory_assessment_answer(character_set: str, length: int) -> str:
    return "".join(choice(character_set) for _ in range(length))


def _validate_memory_assessment_settings(
    *,
    single_daily_limit: int,
    single_recall_seconds: int,
    duel_recall_seconds: int,
    duel_difficulty_level: int,
    duel_base_pool: int,
    duel_wrong_freeze: int,
    duel_wrong_limit: int,
    duel_answer_timeout_minutes: int,
    character_set: str,
    levels: list[MemoryAssessmentLevelRule],
) -> None:
    positive_values = {
        "每日挑战次数": single_daily_limit,
        "单人撤回秒数": single_recall_seconds,
        "多人撤回秒数": duel_recall_seconds,
        "基础奖池": duel_base_pool,
        "答错冻结金额": duel_wrong_freeze,
        "答错上限": duel_wrong_limit,
        "作答超时": duel_answer_timeout_minutes,
    }
    if any(not isinstance(value, int) or value < 1 for value in positive_values.values()):
        raise ValueError("记忆考核数值必须为正整数")
    if not isinstance(character_set, str) or not character_set:
        raise ValueError("字符集不能为空")
    if any(character.isspace() for character in character_set):
        raise ValueError("字符集不能包含空白字符")
    if len(set(character_set)) < 2:
        raise ValueError("字符集至少需要两个不同字符")
    if not isinstance(levels, list) or not levels:
        raise ValueError("至少需要一个等级")
    expected_levels = list(range(1, len(levels) + 1))
    actual_levels = [rule.level for rule in levels]
    if actual_levels != expected_levels:
        raise ValueError("等级必须从 1 开始连续排列")
    if any(
        not isinstance(rule.answer_length, int)
        or rule.answer_length < 1
        or not isinstance(rule.reward, int)
        or rule.reward < 1
        for rule in levels
    ):
        raise ValueError("等级长度和奖励必须为正整数")
    if duel_difficulty_level not in actual_levels:
        raise ValueError("多人难度必须是现有等级")


def _hide_and_seek_scene(record: HideAndSeekSceneRecord) -> HideAndSeekScene:
    return HideAndSeekScene(record.id, record.name, record.enabled)


def _validate_hide_and_seek_scene_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("地点名称不能为空")
    name = name.strip()
    if not 1 <= len(name) <= 64:
        raise ValueError("地点名称不能为空且不能超过 64 个字符")
    return name


def _sample_distinct(values: list, count: int) -> list:
    pool = list(values)
    sampled = []
    for _ in range(count):
        sampled.append(pool.pop(randbelow(len(pool))))
    return sampled


def _random_event_seat_summary(seats) -> str:
    return "、".join(f"{role} × {capacity}" for role, capacity in seats) or "已满员"


def _render_random_event_signup_notice(
    template: str, open_seats: str, signup_timeout_minutes: int
) -> str:
    return (
        template.replace("{可选身份}", open_seats)
        .replace("{报名截止分钟}", str(signup_timeout_minutes))
    )


def _random_event_schedule(
    record: RandomEventScheduleRecord,
    scene_name: str | None = None,
    event_name: str | None = None,
    is_cross_day: bool = False,
) -> RandomEventSchedule:
    return RandomEventSchedule(
        id=record.id,
        event_date=record.event_date,
        scheduled_at=record.scheduled_at,
        status=record.status,
        scene_name=record.scene_name or scene_name,
        event_name=record.event_name or event_name,
        is_cross_day=is_cross_day,
    )


def _validate_random_event_scene(
    name: str,
    signup_text: str,
    openings: list[str | dict[str, str]],
    reward: int,
    target_rounds: int,
    seats: list[tuple[str, int]],
) -> tuple[list[RandomEventSeatRule], list[RandomEventTemplate]]:
    if not 1 <= len(name) <= 64 or not signup_text:
        raise ValueError("场景名称和报名公告不能为空")
    if not isinstance(openings, list) or not openings:
        raise ValueError("至少需要一条正式剧情开场白")
    templates: list[RandomEventTemplate] = []
    for opening in openings:
        if isinstance(opening, str):
            templates.append(RandomEventTemplate("未命名事件", opening.strip()))
        elif isinstance(opening, dict):
            templates.append(
                RandomEventTemplate(
                    str(opening.get("name", "")).strip(),
                    str(opening.get("opening_text", "")).strip(),
                )
            )
    if len(templates) != len(openings) or any(
        not template.name or not template.opening_text for template in templates
    ):
        raise ValueError("事件名称和正式剧情开场白不能为空")
    if not isinstance(reward, int) or not 0 <= reward <= 999:
        raise ValueError("事件奖励需在 0 至 999 之间")
    if not isinstance(target_rounds, int) or target_rounds < 1:
        raise ValueError("目标轮次至少为 1")
    rules = [RandomEventSeatRule(role.strip(), capacity) for role, capacity in seats]
    if not rules or any(
        not 1 <= len(rule.role) <= 32 or not isinstance(rule.capacity, int) or rule.capacity < 1
        for rule in rules
    ):
        raise ValueError("席位角色和人数无效")
    if len({rule.role for rule in rules}) != len(rules):
        raise ValueError("席位角色不能重复")
    _validate_formal_opening_variables(
        [template.opening_text for template in templates], {rule.role for rule in rules}
    )
    return rules, templates


def _validate_formal_opening_variables(openings: list[str], roles: set[str]) -> None:
    unknown = {
        match.group(1)
        for opening in openings
        for match in _ROLE_VARIABLE.finditer(opening)
    } - roles
    if unknown:
        raise ValueError(
            f"正式剧情开场白包含不存在的角色变量：{'、'.join(sorted(unknown))}"
        )


def _render_random_event_formal_opening(
    session: Session, event: RandomEventRecord
) -> str:
    names_by_role: dict[str, list[str]] = {}
    for role, display_name in session.execute(
        select(RandomEventParticipantRecord.role, UserRecord.display_name)
        .join(UserRecord, UserRecord.id == RandomEventParticipantRecord.user_id)
        .where(
            RandomEventParticipantRecord.event_id == event.id,
            RandomEventParticipantRecord.left_at.is_(None),
        )
        .order_by(
            RandomEventParticipantRecord.joined_at,
            RandomEventParticipantRecord.id,
        )
    ):
        names_by_role.setdefault(role, []).append(display_name)
    return _ROLE_VARIABLE.sub(
        lambda match: "、".join(names_by_role.get(match.group(1), [])),
        event.formal_opening_text,
    )


def _is_parenthesized_observer_message(content: str) -> bool:
    compact = "".join(content.split())
    return (
        len(compact) >= 3
        and (compact[0], compact[-1]) in {("（", "）"), ("(", ")")}
    )


def _random_event_scene(
    record: RandomEventSceneRecord,
    seats: list[RandomEventSeatRule],
    openings: list[RandomEventTemplate],
) -> RandomEventScene:
    return RandomEventScene(
        id=record.id,
        name=record.name,
        signup_text=record.signup_text,
        openings=[template.opening_text for template in openings],
        events=openings,
        reward=record.reward,
        target_rounds=record.target_rounds,
        enabled=record.enabled,
        seats=seats,
    )
