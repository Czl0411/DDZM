import asyncio
import json
import os
import signal
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol


class ChildProcess(Protocol):
    pid: int


ProcessFactory = Callable[..., Awaitable[ChildProcess]]


class AuthDesktopController:
    def __init__(
        self,
        *,
        runtime_dir: Path,
        profile_dir: Path,
        login_url: str | None,
        login_state: Callable[[], str | None],
        browser_stopped: Callable[[], bool],
        novnc_port: int = 16080,
        process_factory: ProcessFactory = asyncio.create_subprocess_exec,
        getpgid: Callable[[int], int] = os.getpgid,
        killpg: Callable[[int, int], None] = os.killpg,
    ) -> None:
        self._runtime_dir = runtime_dir
        self._profile_dir = profile_dir
        self._login_url = login_url
        self._login_state = login_state
        self._browser_stopped = browser_stopped
        self._novnc_port = novnc_port
        self._process_factory = process_factory
        self._getpgid = getpgid
        self._killpg = killpg
        self.lock = asyncio.Lock()
        self._pid_file = runtime_dir / "auth-desktop.json"

    def start(self) -> None:
        asyncio.run(self._start())

    async def _start(self) -> None:
        async with self.lock:
            if self._login_state() != "auth_required":
                raise RuntimeError("login state must be auth_required")
            if not self._browser_stopped():
                raise RuntimeError("browser worker must be stopped")
            if self._pid_file.exists():
                raise RuntimeError("authentication desktop is already active")

            self._runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            display_environment = {**os.environ, "DISPLAY": ":99"}
            commands = [
                (("Xvfb", ":99", "-screen", "0", "1280x800x24"), {}),
                (("fluxbox",), {"env": display_environment}),
                (
                    (
                        "google-chrome",
                        f"--user-data-dir={self._profile_dir}",
                        "--no-first-run",
                        "--disable-dev-shm-usage",
                        *(tuple([self._login_url]) if self._login_url else ()),
                    ),
                    {"env": display_environment},
                ),
                (
                    (
                        "x11vnc",
                        "-display",
                        ":99",
                        "-localhost",
                        "-rfbport",
                        "15900",
                        "-forever",
                        "-shared",
                        "-nopw",
                    ),
                    {},
                ),
                (
                    (
                        "websockify",
                        "--web",
                        "/usr/share/novnc/",
                        f"127.0.0.1:{self._novnc_port}",
                        "127.0.0.1:15900",
                    ),
                    {},
                ),
            ]
            pids: list[int] = []
            groups: list[int] = []
            try:
                for command, options in commands:
                    process = await self._process_factory(
                        *command, start_new_session=True, **options
                    )
                    pids.append(process.pid)
                    groups.append(self._getpgid(process.pid))
                self._pid_file.write_text(
                    json.dumps({"process_groups": groups, "pids": pids})
                )
                self._pid_file.chmod(0o600)
            except Exception:
                self._stop_groups(groups)
                raise

    def stop(self) -> None:
        asyncio.run(self._stop())

    async def _stop(self) -> None:
        async with self.lock:
            if not self._pid_file.exists():
                return
            state = json.loads(self._pid_file.read_text())
            self._stop_groups(state["process_groups"])
            self._pid_file.unlink()

    def _stop_groups(self, groups: list[int]) -> None:
        for group in reversed(groups):
            try:
                self._killpg(group, signal.SIGTERM)
            except ProcessLookupError:
                pass
