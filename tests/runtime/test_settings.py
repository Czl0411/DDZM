import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from dzmm_bot.runtime.settings import Settings


def test_settings_requires_nonempty_database_url_and_core_token(monkeypatch):
    monkeypatch.delenv("DZMM_DATABASE_URL", raising=False)
    monkeypatch.delenv("DZMM_CORE_TOKEN", raising=False)

    with pytest.raises(ValueError, match="DZMM_DATABASE_URL"):
        Settings.from_environment()


def test_settings_uses_isolated_default_browser_port(monkeypatch):
    monkeypatch.setenv("DZMM_DATABASE_URL", "postgresql+psycopg://dzmm:x@localhost/dzmm")
    monkeypatch.setenv("DZMM_CORE_TOKEN", "core-token")

    assert Settings.from_environment().browser_cdp_port == 19222


def test_settings_rejects_empty_secret_and_relative_browser_profile(monkeypatch):
    monkeypatch.setenv("DZMM_DATABASE_URL", "postgresql+psycopg://dzmm:x@localhost/dzmm")
    monkeypatch.setenv("DZMM_CORE_TOKEN", "")

    with pytest.raises(ValueError, match="DZMM_CORE_TOKEN"):
        Settings.from_environment()

    monkeypatch.setenv("DZMM_CORE_TOKEN", "core-token")
    monkeypatch.setenv("DZMM_BROWSER_PROFILE", "relative-profile")

    with pytest.raises(ValueError, match="DZMM_BROWSER_PROFILE"):
        Settings.from_environment()


def test_settings_treats_an_empty_login_url_as_not_configured(monkeypatch):
    monkeypatch.setenv("DZMM_DATABASE_URL", "postgresql+psycopg://dzmm:x@localhost/dzmm")
    monkeypatch.setenv("DZMM_CORE_TOKEN", "core-token")
    monkeypatch.setenv("DZMM_LOGIN_URL", "")

    assert Settings.from_environment().login_url is None
