import asyncio
from pathlib import Path
from secrets import compare_digest, token_urlsafe
from typing import Annotated, Callable
from uuid import UUID

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from httpx import HTTPStatusError
from sqlalchemy.exc import IntegrityError

from dzmm_bot.core.database import create_session_factory
from dzmm_bot.core.schema import beijing_now
from dzmm_bot.runtime.settings import Settings

from .core_client import (
    AdminCorePort,
    CoreClient,
    NoVNCClient,
    NoVNCWebSocketConnector,
)
from .repository import AdminIdentity, AdminRepository, IdempotencyInProgressError


_ROOT = Path(__file__).parent
_SAFE_STATUS_FIELDS = ("state", "last_heartbeat", "queue_counts")
_WORKER_COMMANDS = {
    "start": "resume_listening",
    "stop": "pause_listening",
    "restart": "restart_browser",
}
_CONSOLE_PATH = "login-console/websockify"
_CONSOLE_URL = "/login-console/?path=login-console%2Fwebsockify"


def create_app_from_environment() -> FastAPI:
    settings = Settings.from_environment()
    if settings.admin_token is None:
        raise ValueError("DZMM_ADMIN_TOKEN must be set and nonempty")
    return create_app(
        settings.admin_token,
        CoreClient(
            f"http://127.0.0.1:{settings.core_api_port}", settings.core_token
        ),
        repository=AdminRepository(create_session_factory(settings.database_url)),
        console_client=NoVNCClient(settings.novnc_port),
        websocket_connector=NoVNCWebSocketConnector(settings.novnc_port),
    )


def create_app(
    admin_token: str,
    core: AdminCorePort,
    *,
    repository: AdminRepository,
    console_client: NoVNCClient | None = None,
    websocket_connector: Callable | None = None,
) -> FastAPI:
    if not admin_token:
        raise ValueError("admin_token must be nonempty")
    app = FastAPI()
    console = console_client or NoVNCClient()
    connect_websocket = websocket_connector or NoVNCWebSocketConnector()
    console_session: str | None = None

    def authorize(
        x_admin_token: Annotated[str | None, Header()] = None,
        x_admin_session: Annotated[str | None, Header()] = None,
    ) -> AdminIdentity:
        if x_admin_token is not None and x_admin_session is not None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorized")
        if x_admin_token is not None and compare_digest(x_admin_token, admin_token):
            return AdminIdentity(None, "超级管理员", "super_admin")
        if x_admin_session is not None:
            identity = repository.resolve_session(x_admin_session, beijing_now())
            if identity is not None:
                return identity
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorized")

    def require_super_admin(
        identity: Annotated[AdminIdentity, Depends(authorize)],
    ) -> AdminIdentity:
        if identity.role != "super_admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "super admin required")
        return identity

    def idempotent_response(
        identity: AdminIdentity,
        idempotency_key: str | None,
        operation: Callable[[], tuple[int, dict]],
    ) -> JSONResponse:
        if not idempotency_key:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Idempotency-Key is required")
        actor_key = "super_admin" if identity.account_id is None else str(identity.account_id)
        try:
            replay = repository.reserve_idempotency_key(
                actor_key, idempotency_key, beijing_now()
            )
        except IdempotencyInProgressError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error))
        if replay is not None:
            status_code, body = replay
            return JSONResponse(body, status_code=status_code)
        try:
            status_code, body = operation()
        except Exception:
            repository.release_idempotency_key(actor_key, idempotency_key)
            raise
        repository.complete_idempotency_key(
            actor_key, idempotency_key, status_code, body, beijing_now()
        )
        return JSONResponse(body, status_code=status_code)

    @app.get("/", response_class=HTMLResponse)
    def index() -> FileResponse:
        return FileResponse(_ROOT / "templates" / "index.html")

    @app.get("/static/admin.js")
    def javascript() -> FileResponse:
        return FileResponse(
            _ROOT / "static" / "admin.js", media_type="text/javascript"
        )

    @app.get("/static/admin.css")
    def stylesheet() -> FileResponse:
        return FileResponse(_ROOT / "static" / "admin.css", media_type="text/css")

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/auth/login")
    def admin_login(request: dict) -> dict:
        username = request.get("username")
        password = request.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid login")
        account = repository.authenticate(username, password)
        if account is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
        return {
            "session_token": repository.create_session(account.id, beijing_now()),
            "username": account.username,
            "role": "admin",
        }

    @app.get("/api/auth/me")
    def admin_identity(
        identity: Annotated[AdminIdentity, Depends(authorize)],
    ) -> dict:
        return {"username": identity.username, "role": identity.role}

    @app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    def admin_logout(
        identity: Annotated[AdminIdentity, Depends(authorize)],
        x_admin_session: Annotated[str | None, Header()] = None,
    ) -> Response:
        if identity.account_id is not None and x_admin_session is not None:
            repository.revoke_session(x_admin_session)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/admins")
    def admin_accounts(
        _: Annotated[AdminIdentity, Depends(require_super_admin)],
    ) -> list[dict]:
        return [
            {
                "id": str(account.id),
                "username": account.username,
                "active": account.active,
                "created_at": account.created_at,
            }
            for account in repository.list_accounts()
        ]

    @app.post("/api/admins", status_code=status.HTTP_201_CREATED)
    def create_admin_account(
        request: dict,
        identity: Annotated[AdminIdentity, Depends(require_super_admin)],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> JSONResponse:
        username = request.get("username")
        password = request.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid administrator")
        username = username.strip()
        if not 1 <= len(username) <= 32 or len(password) < 8:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid administrator")

        def operation() -> tuple[int, dict]:
            try:
                account = repository.create_account(username, password)
            except IntegrityError:
                raise HTTPException(status.HTTP_409_CONFLICT, "administrator already exists")
            return 201, {
                "id": str(account.id),
                "username": account.username,
                "active": account.active,
            }

        return idempotent_response(identity, idempotency_key, operation)

    @app.patch("/api/admins/{account_id}")
    def update_admin_account(
        account_id: UUID,
        request: dict,
        _: Annotated[AdminIdentity, Depends(require_super_admin)],
    ) -> dict:
        if "active" in request:
            if not isinstance(request["active"], bool):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid administrator")
            account = repository.set_account_active(account_id, request["active"])
        elif "password" in request and isinstance(request["password"], str):
            if len(request["password"]) < 8:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid administrator")
            account = repository.reset_password(account_id, request["password"])
        else:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid administrator")
        if account is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "administrator not found")
        return {"id": str(account.id), "username": account.username, "active": account.active}

    @app.delete("/api/admins/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_admin_account(
        account_id: UUID,
        _: Annotated[AdminIdentity, Depends(require_super_admin)],
    ) -> Response:
        if not repository.delete_account(account_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "administrator not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/status")
    def operational_status(
        _: Annotated[None, Depends(authorize)],
    ) -> dict:
        raw = core.status()
        return {key: raw.get(key) for key in _SAFE_STATUS_FIELDS}

    @app.get("/api/game/commands")
    def game_commands(_: Annotated[None, Depends(authorize)]) -> list[dict]:
        return core.list_game_commands()

    @app.patch("/api/game/commands")
    def set_game_command_enabled(
        request: dict, _: Annotated[None, Depends(authorize)]
    ) -> dict:
        command = request.get("command")
        enabled = request.get("enabled")
        if not isinstance(command, str) or not isinstance(enabled, bool):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid command")
        return core.set_game_command_enabled(command, enabled)

    @app.patch("/api/game/command-templates")
    def set_game_command_template(
        request: dict, _: Annotated[None, Depends(authorize)]
    ) -> dict:
        command = request.get("command")
        scenario = request.get("scenario")
        template = request.get("template")
        if not all(isinstance(value, str) for value in (command, scenario, template)):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid template")
        try:
            return core.set_game_command_template(command, scenario, template)
        except HTTPStatusError as error:
            raise HTTPException(error.response.status_code, error.response.text)

    @app.get("/api/game/users")
    def game_users(
        _: Annotated[None, Depends(authorize)],
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ) -> dict:
        return core.list_game_users(page, page_size)

    @app.get("/api/game/items")
    def game_items(
        _: Annotated[None, Depends(authorize)],
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ) -> dict:
        return core.list_game_items(page, page_size)

    @app.post("/api/game/items", status_code=status.HTTP_201_CREATED)
    async def create_game_item(
        request: Request, _: Annotated[None, Depends(authorize)]
    ) -> dict:
        try:
            item = await request.json()
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid item")
        required = ("name", "description", "price", "stock")
        if not isinstance(item, dict) or not all(key in item for key in required):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid item")
        return core.create_game_item({key: item[key] for key in required})

    @app.get("/api/game/settings")
    def game_settings(_: Annotated[None, Depends(authorize)]) -> dict:
        return core.get_game_settings()

    @app.patch("/api/game/settings")
    def set_game_settings(
        request: dict, _: Annotated[None, Depends(authorize)]
    ) -> dict:
        required = ("currency_name", "onboarding_bonus", "checkin_reward")
        if not all(key in request for key in required):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid settings")
        try:
            return core.set_game_settings({key: request[key] for key in required})
        except HTTPStatusError as error:
            raise HTTPException(error.response.status_code, error.response.text)

    @app.get("/api/game/activity-settings")
    def activity_settings(_: Annotated[None, Depends(authorize)]) -> dict:
        return core.get_activity_settings()

    @app.patch("/api/game/activity-settings")
    def set_activity_settings(
        request: dict, _: Annotated[None, Depends(authorize)]
    ) -> dict:
        if not isinstance(request.get("rules"), list) or not isinstance(
            request.get("report_times"), list
        ):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid settings")
        try:
            return core.set_activity_settings(
                {"rules": request["rules"], "report_times": request["report_times"]}
            )
        except HTTPStatusError as error:
            raise HTTPException(error.response.status_code, error.response.text)

    @app.post("/api/session", status_code=status.HTTP_204_NO_CONTENT)
    def create_console_session(
        response: Response, identity: Annotated[AdminIdentity, Depends(authorize)]
    ) -> None:
        nonlocal console_session
        lease = core.get_manual_login_lease()
        if lease is None or lease["operator_id"] != _actor_id(identity):
            raise HTTPException(status.HTTP_409_CONFLICT, "manual login is not owned by actor")
        console_session = token_urlsafe(32)
        response.set_cookie(
            "dzmm_admin_session",
            console_session,
            httponly=True,
            max_age=900,
            path="/login-console",
            samesite="strict",
        )

    @app.post("/api/worker/{action}", status_code=status.HTTP_202_ACCEPTED)
    def worker_action(
        action: str, _: Annotated[None, Depends(authorize)]
    ) -> dict:
        command = _WORKER_COMMANDS.get(action)
        if command is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown action")
        return core.enqueue_command(command)

    @app.get("/api/login/lease")
    def login_lease(
        _: Annotated[AdminIdentity, Depends(authorize)],
    ) -> dict | None:
        return core.get_manual_login_lease()

    @app.post("/api/login/start", status_code=status.HTTP_202_ACCEPTED)
    def login_start(
        identity: Annotated[AdminIdentity, Depends(authorize)],
    ) -> dict:
        _require_login_state(core, "auth_required")
        return _relay_core(
            lambda: core.start_manual_login(_actor_id(identity), identity.username)
        )

    @app.post("/api/login/finish", status_code=status.HTTP_202_ACCEPTED)
    def login_finish(
        identity: Annotated[AdminIdentity, Depends(authorize)],
    ) -> dict:
        _require_login_state(core, "auth_in_progress")
        return _relay_core(
            lambda: core.finish_manual_login(_actor_id(identity), identity.username)
        )

    @app.post("/api/login/cancel", status_code=status.HTTP_202_ACCEPTED)
    def login_cancel(_: Annotated[AdminIdentity, Depends(authorize)]) -> dict:
        return _relay_core(core.cancel_manual_login)

    @app.get("/login-console")
    def login_console(
        x_admin_token: Annotated[str | None, Header()] = None,
        dzmm_admin_session: Annotated[str | None, Cookie()] = None,
    ) -> Response:
        _authorize_console(
            admin_token,
            console_session,
            x_admin_token,
            dzmm_admin_session,
        )
        _require_login_state(core, "auth_in_progress")
        return RedirectResponse(_CONSOLE_URL, status_code=307)

    @app.get("/login-console/")
    def login_console_index(
        request: Request,
        x_admin_token: Annotated[str | None, Header()] = None,
        dzmm_admin_session: Annotated[str | None, Cookie()] = None,
    ) -> Response:
        _authorize_console(
            admin_token,
            console_session,
            x_admin_token,
            dzmm_admin_session,
        )
        _require_login_state(core, "auth_in_progress")
        if request.query_params.getlist("path") != [_CONSOLE_PATH]:
            return RedirectResponse(_CONSOLE_URL, status_code=307)
        return _proxy_console_asset(console, "/vnc.html")

    @app.get("/login-console/{asset_path:path}")
    def login_console_asset(
        asset_path: str,
        x_admin_token: Annotated[str | None, Header()] = None,
        dzmm_admin_session: Annotated[str | None, Cookie()] = None,
    ) -> Response:
        _authorize_console(
            admin_token,
            console_session,
            x_admin_token,
            dzmm_admin_session,
        )
        _require_login_state(core, "auth_in_progress")
        if not asset_path or ".." in asset_path.split("/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "asset not found")
        return _proxy_console_asset(console, f"/{asset_path}")

    @app.websocket("/login-console/websockify")
    async def login_console_websocket(websocket: WebSocket) -> None:
        if not _console_session_matches(
            console_session, websocket.cookies.get("dzmm_admin_session")
        ):
            await websocket.close(code=4401)
            return
        if core.login_state() != "auth_in_progress":
            await websocket.close(code=4409)
            return
        offered_protocols = [
            protocol.strip()
            for protocol in websocket.headers.get(
                "sec-websocket-protocol", ""
            ).split(",")
            if protocol.strip()
        ]
        async with connect_websocket(
            "/websockify", subprotocols=offered_protocols or None
        ) as upstream:
            await websocket.accept(
                subprotocol=getattr(upstream, "subprotocol", None)
            )
            downstream = asyncio.create_task(
                _relay_to_upstream(websocket, upstream)
            )
            upstream_task = asyncio.create_task(
                _relay_to_browser(upstream, websocket)
            )
            done, pending = await asyncio.wait(
                (downstream, upstream_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)

    return app


def _require_login_state(core: AdminCorePort, expected: str) -> None:
    if core.login_state() != expected:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"login state must be {expected}",
        )


def _actor_id(identity: AdminIdentity) -> str:
    return "super_admin" if identity.account_id is None else str(identity.account_id)


def _relay_core(operation: Callable[[], dict]) -> dict:
    try:
        return operation()
    except HTTPStatusError as error:
        raise HTTPException(error.response.status_code, error.response.text)


def _authorize_console(
    admin_token: str,
    active_session: str | None,
    supplied_token: str | None,
    supplied_session: str | None,
) -> None:
    token_matches = supplied_token is not None and compare_digest(
        supplied_token, admin_token
    )
    if not token_matches and not _console_session_matches(
        active_session, supplied_session
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorized")


def _console_session_matches(
    active_session: str | None, supplied_session: str | None
) -> bool:
    return (
        active_session is not None
        and supplied_session is not None
        and compare_digest(active_session, supplied_session)
    )


def _proxy_console_asset(console: NoVNCClient, path: str) -> Response:
    upstream = console.get(path)
    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
        status_code=upstream.status_code,
    )


async def _relay_to_upstream(websocket: WebSocket, upstream) -> None:
    while True:
        event = await websocket.receive()
        if event["type"] == "websocket.disconnect":
            return
        data = event.get("bytes")
        if data is None:
            data = event.get("text")
        if data is not None:
            await upstream.send(data)


async def _relay_to_browser(upstream, websocket: WebSocket) -> None:
    async for data in upstream:
        if isinstance(data, bytes):
            await websocket.send_bytes(data)
        else:
            await websocket.send_text(data)
