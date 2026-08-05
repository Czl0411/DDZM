from datetime import datetime
from pathlib import Path
from time import time
from typing import Callable, Protocol
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from dzmm_bot.runtime.contracts import InboundMessage, LoginState
from dzmm_bot.dzmm_source import DzmmMessageSource


class ChatGateway(Protocol):
    def read_new(self) -> list[InboundMessage]: ...

    def send(self, text: str) -> str: ...

    def is_authenticated(self) -> bool: ...

    def close(self) -> None: ...


class BrowserSession:
    def __init__(
        self,
        profile_path: Path,
        login_url: str | None,
        *,
        cdp_port: int = 19222,
        playwright_factory: Callable | None = None,
    ) -> None:
        if cdp_port != 19222:
            raise ValueError("browser CDP port must be the isolated port 19222")
        self.profile_path = profile_path
        self.login_url = login_url
        self.cdp_port = cdp_port
        self._playwright_factory = playwright_factory or _start_playwright
        self._playwright = None
        self._context = None
        self._gateway = None
        self._attached = False

    def attach_existing(self) -> ChatGateway:
        if self._gateway is not None:
            return self._gateway
        self._playwright = self._playwright_factory()
        browser = self._playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{self.cdp_port}"
        )
        self._context = browser.contexts[0]
        self._attached = True
        self._gateway = _PlaywrightGateway(self._context, self.login_url)
        return self._gateway

    def start_headless(self) -> ChatGateway:
        if self._gateway is not None:
            return self._gateway
        self.profile_path.mkdir(parents=True, exist_ok=True)
        self._playwright = self._playwright_factory()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_path),
            headless=True,
            args=[
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={self.cdp_port}",
                "--restore-last-session",
            ],
        )
        page = next(
            (
                restored
                for restored in self._context.pages
                if restored.url != "about:blank"
            ),
            self._context.pages[0],
        )
        if self.login_url and page.url == "about:blank":
            page.goto(self.login_url)
        self._gateway = _PlaywrightGateway(self._context, self.login_url)
        return self._gateway

    def stop(self) -> None:
        if self._context is not None and not self._attached:
            self._context.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._gateway = None
        self._context = None
        self._attached = False
        self._playwright = None

    def login_state(self) -> LoginState:
        if self._gateway is None:
            return LoginState.AUTH_REQUIRED
        return (
            LoginState.READY
            if self._gateway.is_authenticated()
            else LoginState.AUTH_REQUIRED
        )


class _PlaywrightGateway:
    def __init__(self, context, login_url: str | None) -> None:
        self._context = context
        self._login_url = login_url

    def read_new(self) -> list[InboundMessage]:
        page = self._active_page()
        return [
            InboundMessage(
                message.message_id,
                message.sender,
                message.text,
                datetime.now(ZoneInfo("Asia/Shanghai")),
            )
            for message in DzmmMessageSource(page).read_new()
        ]

    def send(self, text: str) -> str:
        page = self._active_page()
        editor = page.locator("textarea, [contenteditable='true']").last
        editor.fill(text)
        editor.press("Enter")
        return f"dzmm:{int(time() * 1000)}"

    def _active_page(self):
        return next((page for page in self._context.pages if "/chat" in page.url), self._context.pages[0])

    def is_authenticated(self) -> bool:
        if not self._context.pages:
            return False
        if self._login_url is None:
            return False
        return _location(self._context.pages[0].url) != _location(self._login_url)

    def close(self) -> None:
        self._context.close()


def _location(url: str) -> tuple[str, str]:
    parsed = urlsplit(url)
    return parsed.netloc, parsed.path.rstrip("/")


def _start_playwright():
    from playwright.sync_api import sync_playwright

    return sync_playwright().start()
