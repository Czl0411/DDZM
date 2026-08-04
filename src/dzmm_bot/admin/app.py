from pathlib import Path
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.responses import FileResponse, HTMLResponse

from .core_client import AdminCorePort, NoVNCClient


_ROOT = Path(__file__).parent
_SAFE_STATUS_FIELDS = ("state", "last_heartbeat", "queue_counts")
_WORKER_COMMANDS = {
    "start": "resume_listening",
    "stop": "pause_listening",
    "restart": "restart_browser",
}


def create_app(
    admin_token: str,
    core: AdminCorePort,
    *,
    console_client: NoVNCClient | None = None,
) -> FastAPI:
    if not admin_token:
        raise ValueError("admin_token must be nonempty")
    app = FastAPI()
    console = console_client or NoVNCClient()

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

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/status")
    def operational_status(
        _: Annotated[None, Depends(authorize)],
    ) -> dict:
        raw = core.status()
        return {key: raw.get(key) for key in _SAFE_STATUS_FIELDS}

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
        _: Annotated[None, Depends(authorize)],
    ) -> Response:
        _require_login_state(core, "auth_in_progress")
        upstream = console.get("/vnc.html")
        upstream.raise_for_status()
        return Response(
            content=upstream.content,
            media_type=upstream.headers.get("content-type", "text/html"),
        )

    return app


def _require_login_state(core: AdminCorePort, expected: str) -> None:
    if core.login_state() != expected:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"login state must be {expected}",
        )
