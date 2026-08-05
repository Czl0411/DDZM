from datetime import datetime
from typing import Literal
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


class SentRequest(ApiModel):
    worker_id: str = Field(min_length=1, max_length=255)
    lease_token: UUID
    platform_sent_id: str = Field(min_length=1, max_length=255)
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


class ItemResponse(ApiModel):
    name: str
    description: str
    price: int
    stock: int
    enabled: bool


class CreateItemRequest(ApiModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1)
    price: int = Field(ge=0, le=999)
    stock: int = Field(ge=0, le=999)


class GameSettingsResponse(ApiModel):
    currency_name: str
    onboarding_bonus: int
    checkin_reward: int
    reset_time_label: str = "北京时间 00:00"


class SetGameSettingsRequest(ApiModel):
    currency_name: str = Field(min_length=1, max_length=12)
    onboarding_bonus: int = Field(ge=0, le=999)
    checkin_reward: int = Field(ge=0, le=999)


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


class DailyJobsRequest(ApiModel):
    now: AwareDatetime


WorkerCommandKind = Literal[
    "pause_listening",
    "resume_listening",
    "restart_browser",
    "start_auth",
    "finish_auth",
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
