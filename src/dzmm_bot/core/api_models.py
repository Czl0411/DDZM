from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from dzmm_bot.runtime.contracts import LoginState


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InboundRequest(ApiModel):
    platform_message_id: str = Field(min_length=1, max_length=255)
    sender_platform_id: str = Field(min_length=1, max_length=255)
    content: str
    received_at: AwareDatetime


class InboundResponse(ApiModel):
    message_id: UUID
    accepted: bool


class DirectChatRoomRequest(ApiModel):
    platform_user_id: str = Field(min_length=1, max_length=255)
    chatroom_id: str = Field(min_length=1, max_length=255)


class DirectChatSyncRequest(ApiModel):
    rooms: list[DirectChatRoomRequest]
    now: AwareDatetime


class ClaimRequest(ApiModel):
    worker_id: str = Field(min_length=1, max_length=255)
    now: AwareDatetime
    lease_seconds: int = Field(gt=0)


class OutboundClaimResponse(ApiModel):
    id: UUID
    inbound_message_id: UUID | None
    text: str
    lease_token: UUID
    lease_expires_at: datetime
    attempt_count: int
    destination_chatroom_id: str | None
    delivery_kind: str


class SentRequest(ApiModel):
    worker_id: str = Field(min_length=1, max_length=255)
    lease_token: UUID
    platform_sent_id: str = Field(min_length=1, max_length=255)
    now: AwareDatetime


class FailedRequest(ApiModel):
    worker_id: str = Field(min_length=1, max_length=255)
    lease_token: UUID
    now: AwareDatetime


class OutboundRecallClaimResponse(ApiModel):
    id: UUID
    platform_sent_id: str
    lease_token: UUID
    lease_expires_at: datetime
    attempt_count: int


class RecalledRequest(ApiModel):
    worker_id: str = Field(min_length=1, max_length=255)
    lease_token: UUID
    now: AwareDatetime


class AcceptedResponse(ApiModel):
    accepted: bool


class HeartbeatRequest(ApiModel):
    worker_id: str = Field(min_length=1, max_length=255)
    login_state: LoginState
    recorded_at: AwareDatetime


class HeartbeatResponse(ApiModel):
    worker_id: str
    login_state: LoginState
    recorded_at: datetime


class HealthResponse(ApiModel):
    database_available: bool
    latest_worker_heartbeat_age_seconds: float | None


class QueueCountsResponse(ApiModel):
    inbound_accepted: int
    outbound_pending: int
    worker_commands_pending: int


class AdminStatusResponse(ApiModel):
    state: str
    last_heartbeat: datetime | None
    queue_counts: QueueCountsResponse


class CommandTemplateResponse(ApiModel):
    scenario: str
    label: str
    template: str
    variables: list[str]


class CommandDefinitionResponse(ApiModel):
    command: str
    description: str
    enabled: bool
    templates: list[CommandTemplateResponse]


class SetCommandEnabledRequest(ApiModel):
    command: str = Field(min_length=1, max_length=32)
    enabled: bool


class SetCommandTemplateRequest(ApiModel):
    command: str = Field(min_length=1, max_length=32)
    scenario: str = Field(min_length=1, max_length=64)
    template: str = Field(min_length=1, max_length=2000)


class UserResponse(ApiModel):
    platform_id: str
    display_name: str
    balance: int
    joined_at: datetime
    rank_name: str
    rank_level_label: str
    department_name: str


class RankResponse(ApiModel):
    id: UUID
    sort_order: int
    name: str
    level_label: str
    promotion_price: int
    vote_weight: int
    multiplayer_game_limit: int
    has_group_management: bool
    is_board: bool
    enabled: bool


class UpdateRankRequest(ApiModel):
    name: str = Field(min_length=1, max_length=64)
    promotion_price: int = Field(ge=0, le=99999)
    vote_weight: int = Field(ge=0, le=99)
    multiplayer_game_limit: int = Field(ge=-1, le=999)
    has_group_management: bool
    enabled: bool


class DepartmentResponse(ApiModel):
    id: UUID
    name: str
    description: str
    is_default: bool
    enabled: bool


class CreateDepartmentRequest(ApiModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=2000)


class UpdateDepartmentRequest(CreateDepartmentRequest):
    enabled: bool


class PaginatedDepartmentsResponse(ApiModel):
    items: list[DepartmentResponse]
    page: int
    page_size: int
    total: int
    pages: int


class PromotionRequestResponse(ApiModel):
    number: int
    applicant_platform_id: str
    applicant_name: str
    source_rank_name: str
    target_rank_name: str
    price: int
    state: str
    requested_at: datetime
    expires_at: datetime
    decided_at: datetime | None


class PaginatedPromotionRequestsResponse(ApiModel):
    items: list[PromotionRequestResponse]
    page: int
    page_size: int
    total: int
    pages: int


class DepartmentRequestResponse(ApiModel):
    number: int
    applicant_platform_id: str
    applicant_name: str
    source_department_name: str
    target_department_name: str
    state: str
    requested_at: datetime
    expires_at: datetime
    decided_at: datetime | None
    approver_name: str | None
    decision: str | None


class PaginatedDepartmentRequestsResponse(ApiModel):
    items: list[DepartmentRequestResponse]
    page: int
    page_size: int
    total: int
    pages: int


class SetBoardMembershipRequest(ApiModel):
    member: bool


class UserProfileResponse(ApiModel):
    platform_id: str
    display_name: str
    balance: int
    rank: RankResponse
    department: DepartmentResponse


class ItemResponse(ApiModel):
    name: str
    description: str
    price: int
    stock: int
    enabled: bool


class PaginatedUsersResponse(ApiModel):
    items: list[UserResponse]
    page: int
    page_size: int
    total: int
    pages: int


class PaginatedItemsResponse(ApiModel):
    items: list[ItemResponse]
    page: int
    page_size: int
    total: int
    pages: int


class CreateItemRequest(ApiModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1)
    price: int = Field(ge=0, le=999)
    stock: int = Field(ge=0, le=999)


class GameSettingsResponse(ApiModel):
    currency_name: str
    onboarding_bonus: int
    checkin_reward: int
    weekly_attendance_reward: int
    reset_time_label: str = "北京时间 00:00"


class SetGameSettingsRequest(ApiModel):
    currency_name: str = Field(min_length=1, max_length=12)
    onboarding_bonus: int = Field(ge=0, le=999)
    checkin_reward: int = Field(ge=0, le=999)
    weekly_attendance_reward: int = Field(ge=0, le=999)


class AIRankQuotaResponse(ApiModel):
    rank_id: UUID
    rank_name: str
    rank_level_label: str
    daily_limit: int = Field(ge=0, le=100)


class SetAIRankQuotaRequest(ApiModel):
    rank_id: UUID
    daily_limit: int = Field(ge=0, le=100)


class AIAssistantSettingsResponse(ApiModel):
    enabled: bool
    persona: str
    system_prompt: str
    over_limit_reply: str
    failure_reply: str
    max_response_chars: int = Field(ge=1, le=800)
    timeout_seconds: int = Field(ge=1, le=60)
    quotas: list[AIRankQuotaResponse]


class SetAIAssistantSettingsRequest(ApiModel):
    enabled: bool
    persona: str = Field(min_length=1, max_length=4000)
    system_prompt: str = Field(min_length=1, max_length=4000)
    over_limit_reply: str = Field(min_length=1, max_length=1000)
    failure_reply: str = Field(min_length=1, max_length=1000)
    max_response_chars: int = Field(ge=1, le=800)
    timeout_seconds: int = Field(ge=1, le=60)
    quotas: list[SetAIRankQuotaRequest] = Field(min_length=1, max_length=100)


class AIClaimResponse(ApiModel):
    id: UUID
    lease_token: UUID
    system_prompt: str
    user_content: str
    max_response_chars: int = Field(ge=1, le=800)
    timeout_seconds: int = Field(ge=1, le=60)


class AICompleteRequest(ApiModel):
    worker_id: str = Field(min_length=1, max_length=255)
    lease_token: UUID
    text: str = Field(min_length=1, max_length=800)
    now: AwareDatetime


class AIFailedRequest(ApiModel):
    worker_id: str = Field(min_length=1, max_length=255)
    lease_token: UUID
    failure_summary: Literal["timeout", "network", "http_error", "invalid_response"]
    now: AwareDatetime


class ActivityLevelRuleModel(ApiModel):
    level: int = Field(ge=1, le=10)
    character_threshold: int = Field(ge=0)
    reward: int = Field(ge=0, le=999)


class ActivitySettingsResponse(ApiModel):
    rules: list[ActivityLevelRuleModel]
    report_times: list[str]


class SetActivitySettingsRequest(ApiModel):
    rules: list[ActivityLevelRuleModel] = Field(min_length=10, max_length=10)
    report_times: list[str] = Field(min_length=1)


class RandomEventSettingsResponse(ApiModel):
    schedule_times: list[str] = Field(min_length=1, max_length=24)
    signup_notice_template: str = Field(min_length=1, max_length=2000)
    signup_timeout_minutes: int
    reminder_interval_minutes: int
    signup_allowed_commands: list[str] = Field(max_length=32)
    in_progress_allowed_commands: list[str] = Field(max_length=32)
    blocked_message: str = Field(min_length=1, max_length=2000)


class SetRandomEventSettingsRequest(RandomEventSettingsResponse):
    pass


class HideAndSeekSettingsResponse(ApiModel):
    enabled: bool
    entry_fee: int = Field(ge=0, le=999)
    win_reward: int = Field(ge=0, le=999)
    daily_limit: int = Field(ge=1, le=99)
    selection_timeout_minutes: int = Field(ge=1, le=60)


class SetHideAndSeekSettingsRequest(HideAndSeekSettingsResponse):
    pass


class MemoryAssessmentLevelRuleModel(ApiModel):
    level: int = Field(ge=1, le=20)
    answer_length: int = Field(ge=1, le=200)
    reward: int = Field(ge=1, le=999)


class MemoryAssessmentSettingsResponse(ApiModel):
    enabled: bool
    single_daily_limit: int = Field(ge=1, le=99)
    single_recall_seconds: int = Field(ge=1, le=60)
    duel_recall_seconds: int = Field(ge=1, le=60)
    duel_difficulty_level: int = Field(ge=1, le=20)
    duel_base_pool: int = Field(ge=1, le=999)
    duel_wrong_freeze: int = Field(ge=1, le=999)
    duel_wrong_limit: int = Field(ge=1, le=99)
    duel_answer_timeout_minutes: int = Field(ge=1, le=60)
    character_set: str = Field(min_length=2, max_length=200)
    levels: list[MemoryAssessmentLevelRuleModel] = Field(min_length=1, max_length=20)


class SetMemoryAssessmentSettingsRequest(MemoryAssessmentSettingsResponse):
    pass


class UndercoverRoleRuleModel(ApiModel):
    player_count: int = Field(ge=4, le=8)
    civilian_count: int = Field(ge=0, le=8)
    undercover_count: int = Field(ge=0, le=8)
    whiteboard_count: int = Field(ge=0, le=8)


class UndercoverSettingsResponse(ApiModel):
    enabled: bool
    vote_seconds: int = Field(ge=1, le=3600)
    whiteboard_win_remaining: int = Field(ge=2, le=8)
    roles: list[UndercoverRoleRuleModel] = Field(min_length=5, max_length=5)


class SetUndercoverSettingsRequest(UndercoverSettingsResponse):
    pass


class UndercoverSessionResponse(ApiModel):
    state: str | None
    target_player_count: int
    player_count: int
    queued_count: int
    current_vote_round: int
    vote_deadline: datetime | None


class HideAndSeekSceneResponse(ApiModel):
    id: UUID
    name: str
    enabled: bool


class PaginatedHideAndSeekScenesResponse(ApiModel):
    items: list[HideAndSeekSceneResponse]
    page: int
    page_size: int
    total: int
    pages: int


class CreateHideAndSeekSceneRequest(ApiModel):
    name: str = Field(min_length=1, max_length=64)


class UpdateHideAndSeekSceneRequest(CreateHideAndSeekSceneRequest):
    enabled: bool


class RandomEventSeatModel(ApiModel):
    role: str = Field(min_length=1, max_length=32)
    capacity: int = Field(ge=1, le=99)


class RandomEventTemplateModel(ApiModel):
    name: str = Field(min_length=1, max_length=64)
    opening_text: str = Field(min_length=1, max_length=2000)


class RandomEventSceneResponse(ApiModel):
    id: UUID
    name: str
    signup_text: str
    openings: list[str]
    events: list[RandomEventTemplateModel]
    reward: int
    target_rounds: int
    enabled: bool
    seats: list[RandomEventSeatModel]


class PaginatedRandomEventScenesResponse(ApiModel):
    items: list[RandomEventSceneResponse]
    page: int
    page_size: int
    total: int
    pages: int


class CreateRandomEventSceneRequest(ApiModel):
    name: str = Field(min_length=1, max_length=64)
    signup_text: str = Field(min_length=1, max_length=2000)
    openings: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(default_factory=list, max_length=20)
    events: list[RandomEventTemplateModel] = Field(default_factory=list, max_length=20)
    reward: int = Field(ge=0, le=999)
    target_rounds: int = Field(ge=1, le=999)
    seats: list[RandomEventSeatModel] = Field(min_length=1, max_length=20)


class UpdateRandomEventSceneRequest(CreateRandomEventSceneRequest):
    enabled: bool


class RandomEventScheduleResponse(ApiModel):
    id: UUID
    event_date: date
    scheduled_at: datetime
    status: str
    scene_name: str | None
    event_name: str | None
    is_cross_day: bool


class CreateTodayRandomEventRequest(ApiModel):
    scene_id: UUID
    event_name: str = Field(min_length=1, max_length=64)
    scheduled_at: datetime


class RandomEventDetailResponse(ApiModel):
    display_name: str
    content: str
    occurred_at: datetime


class RandomEventDetailsResponse(ApiModel):
    items: list[RandomEventDetailResponse]


class RescheduleRandomEventRequest(ApiModel):
    scheduled_at: AwareDatetime


class DailyJobsRequest(ApiModel):
    now: AwareDatetime


class ManualLoginActorRequest(ApiModel):
    operator_id: str = Field(min_length=1, max_length=64)
    operator_name: str = Field(min_length=1, max_length=32)


class ManualLoginLeaseResponse(ApiModel):
    operator_id: str
    operator_name: str
    expires_at: datetime


WorkerCommandKind = Literal[
    "pause_listening",
    "resume_listening",
    "restart_browser",
    "start_auth",
    "finish_auth",
    "cancel_auth",
    "retract_test",
]


class WorkerCommandRequest(ApiModel):
    command: WorkerCommandKind


class WorkerCommandResponse(ApiModel):
    id: UUID
    command: WorkerCommandKind
    status: str
    lease_token: UUID | None = None
    lease_expires_at: datetime | None = None


class CompleteWorkerCommandRequest(ApiModel):
    worker_id: str = Field(min_length=1, max_length=255)
    lease_token: UUID
    status: Literal["completed", "failed"]
    now: AwareDatetime
