from datetime import UTC, datetime
from secrets import compare_digest
from typing import Annotated, Callable
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from dzmm_bot.runtime.contracts import InboundMessage, WorkerHeartbeat

from .api_models import (
    AcceptedResponse,
    ClaimRequest,
    CompleteWorkerCommandRequest,
    HealthResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    InboundRequest,
    InboundResponse,
    OutboundClaimResponse,
    SentRequest,
    WorkerCommandRequest,
    WorkerCommandResponse,
)
from .repository import CoreRepository
from .schema import WorkerCommandRecord, WorkerInstanceRecord
from .service import CoreService


def create_app(
    repository: CoreRepository,
    core_token: str,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FastAPI:
    app = FastAPI()
    service = CoreService(repository)

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
