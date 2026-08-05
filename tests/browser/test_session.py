from pathlib import Path

import pytest

from dzmm_bot.browser.session import BrowserSession
from dzmm_bot.runtime.contracts import LoginState


class FakePage:
    def __init__(self, url):
        self.url = url

    def goto(self, url):
        self.url = url


class FakeContext:
    def __init__(self, url):
        self.pages = [FakePage(url)]
        self.closed = False

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, context):
        self.context = context
        self.calls = []

    def launch_persistent_context(self, **kwargs):
        self.calls.append(kwargs)
        return self.context


class FakePlaywright:
    def __init__(self, chromium):
        self.chromium = chromium
        self.stopped = False

    def stop(self):
        self.stopped = True


def test_headless_session_uses_owned_profile_and_loopback_cdp(tmp_path):
    context = FakeContext("https://chat.example/room")
    chromium = FakeChromium(context)
    playwright = FakePlaywright(chromium)
    profile = tmp_path / "profile"
    session = BrowserSession(
        profile_path=profile,
        login_url="https://chat.example/login",
        cdp_port=19222,
        playwright_factory=lambda: playwright,
    )

    session.start_headless()

    assert profile.is_dir()
    assert chromium.calls == [
        {
            "user_data_dir": str(profile),
            "headless": True,
            "args": [
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=19222",
                "--restore-last-session",
            ],
        }
    ]


def test_session_rejects_nonstandard_cdp_port(tmp_path):
    with pytest.raises(ValueError, match="19222"):
        BrowserSession(tmp_path / "profile", None, cdp_port=9222)


def test_headless_session_prefers_a_restored_page_over_a_blank_page(tmp_path):
    context = FakeContext("about:blank")
    context.pages.append(FakePage("https://chat.example/room"))
    session = BrowserSession(
        tmp_path / "profile",
        "https://chat.example/login",
        playwright_factory=lambda: FakePlaywright(FakeChromium(context)),
    )

    session.start_headless()

    assert session.login_state() is LoginState.READY


def test_login_state_uses_navigation_without_platform_selectors(tmp_path):
    context = FakeContext("https://chat.example/login")
    chromium = FakeChromium(context)
    session = BrowserSession(
        tmp_path / "profile",
        "https://chat.example/login",
        playwright_factory=lambda: FakePlaywright(chromium),
    )
    session.start_headless()

    assert session.login_state() is LoginState.AUTH_REQUIRED
    context.pages[0].url = "https://chat.example/room"
    assert session.login_state() is LoginState.READY


def test_missing_login_url_requires_authentication(tmp_path):
    session = BrowserSession(
        tmp_path / "profile",
        None,
        playwright_factory=lambda: FakePlaywright(
            FakeChromium(FakeContext("about:blank"))
        ),
    )

    session.start_headless()

    assert session.login_state() is LoginState.AUTH_REQUIRED


def test_stop_releases_browser_and_playwright(tmp_path):
    context = FakeContext("https://chat.example/room")
    playwright = FakePlaywright(FakeChromium(context))
    session = BrowserSession(
        tmp_path / "profile", None, playwright_factory=lambda: playwright
    )
    session.start_headless()

    session.stop()

    assert context.closed is True
    assert playwright.stopped is True


def test_gateway_defers_platform_specific_message_operations(tmp_path):
    session = BrowserSession(
        tmp_path / "profile",
        "https://chat.example/login",
        playwright_factory=lambda: FakePlaywright(
            FakeChromium(FakeContext("https://chat.example/room"))
        ),
    )
    gateway = session.start_headless()

    with pytest.raises(NotImplementedError, match="platform adapter"):
        gateway.read_new()
    with pytest.raises(NotImplementedError, match="platform adapter"):
        gateway.send("hello")
