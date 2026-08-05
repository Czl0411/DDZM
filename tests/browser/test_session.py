from pathlib import Path

import pytest

from dzmm_bot.browser.session import BrowserSession
from dzmm_bot.runtime.contracts import LoginState


class FakePage:
    def __init__(self, url, rows=None):
        self.url = url
        self.rows = rows or []
        self.filled = []
        self.pressed = []

    def goto(self, url):
        self.url = url

    def evaluate(self, _script, _selectors):
        return self.rows

    def locator(self, _selector):
        return self

    @property
    def last(self):
        return self

    def fill(self, text):
        self.filled.append(text)

    def press(self, key):
        self.pressed.append(key)


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

    def connect_over_cdp(self, url):
        self.calls.append({"cdp_url": url})
        return type("Browser", (), {"contexts": [self.context]})()


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


def test_session_attaches_to_the_existing_desktop_browser(tmp_path):
    context = FakeContext("https://chat.example/room")
    chromium = FakeChromium(context)
    session = BrowserSession(
        tmp_path / "profile",
        "https://chat.example/login",
        playwright_factory=lambda: FakePlaywright(chromium),
    )

    assert session.attach_existing().is_authenticated()
    assert chromium.calls == [{"cdp_url": "http://127.0.0.1:19222"}]


def test_attached_desktop_opens_configured_group_chat(tmp_path):
    context = FakeContext("https://chat.example/chat")
    chromium = FakeChromium(context)
    session = BrowserSession(
        tmp_path / "profile",
        "https://chat.example/login",
        chat_url="https://chat.example/chat?c=group-1",
        playwright_factory=lambda: FakePlaywright(chromium),
    )

    session.attach_existing()

    assert context.pages[0].url == "https://chat.example/chat?c=group-1"


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


def test_gateway_reads_and_sends_platform_messages(tmp_path):
    page = FakePage(
        "https://chat.example/room",
        rows=[{"source_index": "42", "sender": "甲", "text": "你好", "is_self": False}],
    )
    session = BrowserSession(
        tmp_path / "profile",
        "https://chat.example/login",
        playwright_factory=lambda: FakePlaywright(FakeChromium(FakeContext(page.url))),
    )
    session._playwright_factory = lambda: FakePlaywright(FakeChromium(type("Context", (), {"pages": [page], "close": lambda self: None})()))
    gateway = session.start_headless()

    messages = gateway.read_new()
    platform_id = gateway.send("hello")

    assert messages[0].platform_message_id == "main:stable:42"
    assert messages[0].sender_platform_id == "甲"
    assert messages[0].content == "你好"
    assert page.filled == ["hello"]
    assert page.pressed == ["Enter"]
    assert platform_id.startswith("dzmm:")
