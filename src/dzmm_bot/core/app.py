from datetime import datetime
from secrets import compare_digest
from typing import Annotated, Callable
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from uvicorn import Config, Server

from dzmm_bot.runtime.contracts import InboundMessage, WorkerHeartbeat
from dzmm_bot.runtime.settings import Settings

from .api_models import (
    AcceptedResponse,
    ActivityLevelRuleModel,
    ActivitySettingsResponse,
    AdminStatusResponse,
    ClaimRequest,
    CompleteWorkerCommandRequest,
    CommandDefinitionResponse,
    CommandTemplateResponse,
    CreateItemRequest,
    DailyJobsRequest,
    GameSettingsResponse,
    HealthResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    InboundRequest,
    InboundResponse,
    OutboundClaimResponse,
    QueueCountsResponse,
    SentRequest,
    SetCommandEnabledRequest,
    SetCommandTemplateRequest,
    SetActivitySettingsRequest,
    SetGameSettingsRequest,
    ItemResponse,
    UserResponse,
    WorkerCommandRequest,
    WorkerCommandResponse,
)
from .database import create_session_factory
from .commands import GroupCommandHandler
from .repository import ActivityLevelRule, CoreRepository
from .reply_templates import definitions_for_command, template_definition
from .schema import WorkerCommandRecord, WorkerInstanceRecord, beijing_now
from .service import CoreService


def create_server(repository: CoreRepository, settings: Settings) -> Server:
    config = Config(
        create_app(repository, settings.core_token),
        host="127.0.0.1",
        port=settings.core_api_port,
    )
    return Server(config)


def create_app_from_environment() -> FastAPI:
    settings = Settings.from_environment()
    return create_app(
        CoreRepository(create_session_factory(settings.database_url)),
        settings.core_token,
    )


def create_app(
    repository: CoreRepository,
    core_token: str,
    *,
    clock: Callable[[], datetime] = beijing_now,
) -> FastAPI:
    app = FastAPI()
    service = CoreService(repository, GroupCommandHandler(repository))

    def authorize(x_core_token: Annotated[str | None, Header()] = None) -> None:
        if x_core_token is None or not compare_digest(x_core_token, core_token):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorized")

    @app.post("/internal/inbound", response_model=InboundResponse)
    def receive_inbound(
        request: InboundRequest, _: Annotated[None, Depends(authorize)]
    ) -> InboundResponse:
        result = service.receive_inbound(
            InboundMessage(
                platform_message_id=request.platform_message_id,
                sender_platform_id=request.sender_platform_id,
                content=request.content,
                received_at=request.received_at,
            )
        )
        return InboundResponse(
            message_id=result.message_id, accepted=result.inserted
        )

    @app.post(
        "/internal/outbound/claim",
        response_model=OutboundClaimResponse | None,
    )
    def claim_outbound(
        request: ClaimRequest, _: Annotated[None, Depends(authorize)]
    ) -> OutboundClaimResponse | None:
        record = repository.claim_outbound(
            request.worker_id, request.now, request.lease_seconds
        )
        if record is None:
            return None
        return OutboundClaimResponse(
            id=record.id,
            inbound_message_id=record.inbound_message_id,
            text=record.text,
            lease_token=record.lease_token,
            lease_expires_at=record.lease_expires_at,
            attempt_count=record.attempt_count,
        )

    @app.post(
        "/internal/outbound/{message_id}/sent", response_model=AcceptedResponse
    )
    def confirm_sent(
        message_id: UUID,
        request: SentRequest,
        _: Annotated[None, Depends(authorize)],
    ) -> AcceptedResponse:
        accepted = repository.confirm_sent(
            message_id,
            request.worker_id,
            request.lease_token,
            request.platform_sent_id,
            request.now,
        )
        return AcceptedResponse(accepted=accepted)

    @app.post("/internal/heartbeat", response_model=HeartbeatResponse)
    def record_heartbeat(
        request: HeartbeatRequest, _: Annotated[None, Depends(authorize)]
    ) -> HeartbeatResponse:
        record = repository.record_worker_heartbeat(
            WorkerHeartbeat(
                request.worker_id, request.login_state, request.recorded_at
            )
        )
        return _heartbeat_response(record)

    @app.get("/internal/login-state", response_model=HeartbeatResponse | None)
    def login_state(
        _: Annotated[None, Depends(authorize)],
    ) -> HeartbeatResponse | None:
        record = _latest_heartbeat(repository)
        return None if record is None else _heartbeat_response(record)

    @app.get("/internal/status", response_model=AdminStatusResponse)
    def admin_status(
        _: Annotated[None, Depends(authorize)],
    ) -> AdminStatusResponse:
        record = _latest_heartbeat(repository)
        return AdminStatusResponse(
            state="unknown" if record is None else record.login_state,
            last_heartbeat=None if record is None else record.recorded_at,
            queue_counts=QueueCountsResponse(**repository.queue_counts()),
        )

    @app.get(
        "/internal/game/commands", response_model=list[CommandDefinitionResponse]
    )
    def game_commands(
        _: Annotated[None, Depends(authorize)],
    ) -> list[CommandDefinitionResponse]:
        return [
            CommandDefinitionResponse(
                command=record.command,
                description=record.description,
                enabled=record.enabled,
                templates=[
                    _template_response(
                        definition,
                        repository.get_reply_template(
                            definition.command, definition.scenario
                        ),
                    )
                    for definition in definitions_for_command(record.command)
                ],
            )
            for record in repository.list_command_definitions()
        ]

    @app.patch(
        "/internal/game/commands", response_model=CommandDefinitionResponse
    )
    def set_game_command_enabled(
        request: SetCommandEnabledRequest,
        _: Annotated[None, Depends(authorize)],
    ) -> CommandDefinitionResponse:
        if not repository.set_command_enabled(request.command, request.enabled):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown command")
        record = next(
            record
            for record in repository.list_command_definitions()
            if record.command == request.command
        )
        return CommandDefinitionResponse(
            command=record.command,
            description=record.description,
            enabled=record.enabled,
            templates=[
                _template_response(
                    definition,
                    repository.get_reply_template(
                        definition.command, definition.scenario
                    ),
                )
                for definition in definitions_for_command(record.command)
            ],
        )

    @app.patch(
        "/internal/game/command-templates", response_model=CommandTemplateResponse
    )
    def set_game_command_template(
        request: SetCommandTemplateRequest,
        _: Annotated[None, Depends(authorize)],
    ) -> CommandTemplateResponse:
        try:
            record = repository.set_reply_template(
                request.command, request.scenario, request.template
            )
            definition = template_definition(request.command, request.scenario)
        except ValueError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
        return _template_response(definition, record)

    @app.get("/internal/game/users", response_model=list[UserResponse])
    def game_users(
        _: Annotated[None, Depends(authorize)],
    ) -> list[UserResponse]:
        return [
            UserResponse(
                platform_id=record.platform_id,
                display_name=record.display_name,
                balance=record.balance,
                joined_at=record.joined_at,
            )
            for record in repository.list_users()
        ]

    @app.get("/internal/game/items", response_model=list[ItemResponse])
    def game_items(
        _: Annotated[None, Depends(authorize)],
    ) -> list[ItemResponse]:
        return [_item_response(record) for record in repository.list_active_items()]

    @app.post(
        "/internal/game/items", response_model=ItemResponse, status_code=201
    )
    def create_game_item(
        request: CreateItemRequest,
        _: Annotated[None, Depends(authorize)],
    ) -> ItemResponse:
        return _item_response(
            repository.add_item(
                request.name, request.description, request.price, request.stock
            )
        )

    @app.get("/internal/game/settings", response_model=GameSettingsResponse)
    def game_settings(
        _: Annotated[None, Depends(authorize)],
    ) -> GameSettingsResponse:
        return _game_settings_response(repository.get_game_settings())

    @app.patch("/internal/game/settings", response_model=GameSettingsResponse)
    def set_game_settings(
        request: SetGameSettingsRequest,
        _: Annotated[None, Depends(authorize)],
    ) -> GameSettingsResponse:
        try:
            record = repository.set_game_settings(
                request.currency_name, request.onboarding_bonus, request.checkin_reward
            )
        except ValueError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
        return _game_settings_response(record)

    @app.get(
        "/internal/game/activity-settings", response_model=ActivitySettingsResponse
    )
    def activity_settings(
        _: Annotated[None, Depends(authorize)],
    ) -> ActivitySettingsResponse:
        return _activity_settings_response(repository.get_activity_settings())

    @app.patch(
        "/internal/game/activity-settings", response_model=ActivitySettingsResponse
    )
    def set_activity_settings(
        request: SetActivitySettingsRequest,
        _: Annotated[None, Depends(authorize)],
    ) -> ActivitySettingsResponse:
        try:
            settings = repository.set_activity_settings(
                [
                    ActivityLevelRule(
                        rule.level, rule.character_threshold, rule.reward
                    )
                    for rule in request.rules
                ],
                request.report_times,
            )
        except ValueError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
        return _activity_settings_response(settings)

    @app.post("/internal/daily-jobs/run", response_model=AcceptedResponse)
    def run_daily_jobs(
        request: DailyJobsRequest,
        _: Annotated[None, Depends(authorize)],
    ) -> AcceptedResponse:
        repository.run_daily_jobs(request.now)
        return AcceptedResponse(accepted=True)

    @app.post("/internal/worker-commands", response_model=WorkerCommandResponse)
    def enqueue_worker_command(
        request: WorkerCommandRequest, _: Annotated[None, Depends(authorize)]
    ) -> WorkerCommandResponse:
        return _worker_command_response(
            repository.enqueue_worker_command(request.command)
        )

    @app.post(
        "/internal/worker-commands/claim",
        response_model=WorkerCommandResponse | None,
    )
    def claim_worker_command(
        request: ClaimRequest, _: Annotated[None, Depends(authorize)]
    ) -> WorkerCommandResponse | None:
        record = repository.claim_worker_command(
            request.worker_id, request.now, request.lease_seconds
        )
        return None if record is None else _worker_command_response(record)

    @app.post(
        "/internal/worker-commands/{command_id}/complete",
        response_model=AcceptedResponse,
    )
    def complete_worker_command(
        command_id: UUID,
        request: CompleteWorkerCommandRequest,
        _: Annotated[None, Depends(authorize)],
    ) -> AcceptedResponse:
        accepted = repository.complete_worker_command(
            command_id,
            request.worker_id,
            request.lease_token,
            request.status,
            request.now,
        )
        return AcceptedResponse(accepted=accepted)

    @app.get("/healthz", response_model=HealthResponse)
    def health(response: Response) -> HealthResponse:
        try:
            record = _latest_heartbeat(repository)
        except SQLAlchemyError:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return HealthResponse(
                database_available=False,
                latest_worker_heartbeat_age_seconds=None,
            )
        age = None
        if record is not None:
            age = max(0.0, (clock() - record.recorded_at).total_seconds())
        return HealthResponse(
            database_available=True,
            latest_worker_heartbeat_age_seconds=age,
        )

    return app


def _latest_heartbeat(repository: CoreRepository) -> WorkerInstanceRecord | None:
    with repository._session() as session:
        return session.scalar(
            select(WorkerInstanceRecord)
            .order_by(WorkerInstanceRecord.recorded_at.desc())
            .limit(1)
        )


def _heartbeat_response(record: WorkerInstanceRecord) -> HeartbeatResponse:
    return HeartbeatResponse(
        worker_id=record.worker_id,
        login_state=record.login_state,
        recorded_at=record.recorded_at,
    )


def _worker_command_response(record: WorkerCommandRecord) -> WorkerCommandResponse:
    return WorkerCommandResponse(
        id=record.id,
        command=record.command,
        status=record.status,
        lease_token=record.lease_token,
        lease_expires_at=record.lease_expires_at,
    )


def _item_response(record) -> ItemResponse:
    return ItemResponse(
        name=record.name,
        description=record.description,
        price=record.price,
        stock=record.stock,
        enabled=record.enabled,
    )


def _game_settings_response(record) -> GameSettingsResponse:
    return GameSettingsResponse(
        currency_name=record.currency_name,
        onboarding_bonus=record.onboarding_bonus,
        checkin_reward=record.checkin_reward,
    )


def _activity_settings_response(settings) -> ActivitySettingsResponse:
    return ActivitySettingsResponse(
        rules=[
            ActivityLevelRuleModel(
                level=rule.level,
                character_threshold=rule.character_threshold,
                reward=rule.reward,
            )
            for rule in settings.rules
        ],
        report_times=settings.report_times,
    )


def _template_response(definition, record) -> CommandTemplateResponse:
    return CommandTemplateResponse(
        scenario=definition.scenario,
        label=definition.label,
        template=definition.default if record is None else record.template,
        variables=list(definition.variables),
    )
