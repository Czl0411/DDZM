import asyncio
from pathlib import Path
from secrets import compare_digest, token_urlsafe
from typing import Annotated, Callable

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
    WebSocket,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from dzmm_bot.runtime.settings import Settings

from .core_client import (
    AdminCorePort,
    CoreClient,
    NoVNCClient,
    NoVNCWebSocketConnector,
)


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
        console_client=NoVNCClient(settings.novnc_port),
        websocket_connector=NoVNCWebSocketConnector(settings.novnc_port),
    )


def create_app(
    admin_token: str,
    core: AdminCorePort,
    *,
    console_client: NoVNCClient | None = None,
    websocket_connector: Callable | None = None,
) -> FastAPI:
    if not admin_token:
        raise ValueError("admin_token must be nonempty")
    app = FastAPI()
    console = console_client or NoVNCClient()
    connect_websocket = websocket_connector or NoVNCWebSocketConnector()
    console_session: str | None = None

    def authorize(x_admin_token: Annotated[str | None, Header()] = None) -> None:
        if x_admin_token is None or not compare_digest(x_admin_token, admin_token):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorized")

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

    @app.get("/api/game/users")
    def game_users(_: Annotated[None, Depends(authorize)]) -> list[dict]:
        return core.list_game_users()

    @app.get("/api/game/items")
    def game_items(_: Annotated[None, Depends(authorize)]) -> list[dict]:
        return core.list_game_items()

    @app.post("/api/game/items", status_code=status.HTTP_201_CREATED)
    def create_game_item(
        request: dict, _: Annotated[None, Depends(authorize)]
    ) -> dict:
        required = ("name", "description", "price", "stock")
        if not all(key in request for key in required):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid item")
        return core.create_game_item({key: request[key] for key in required})

    @app.post("/api/session", status_code=status.HTTP_204_NO_CONTENT)
    def create_console_session(
        response: Response, _: Annotated[None, Depends(authorize)]
    ) -> None:
        nonlocal console_session
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

    @app.post("/api/login/start", status_code=status.HTTP_202_ACCEPTED)
    def login_start(_: Annotated[None, Depends(authorize)]) -> dict:
        _require_login_state(core, "auth_required")
        return core.enqueue_command("start_auth")

    @app.post("/api/login/finish", status_code=status.HTTP_202_ACCEPTED)
    def login_finish(_: Annotated[None, Depends(authorize)]) -> dict:
        _require_login_state(core, "auth_in_progress")
        return core.enqueue_command("finish_auth")

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
