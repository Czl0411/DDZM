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


def test_settings_reads_configured_group_chat_url(monkeypatch):
    monkeypatch.setenv("DZMM_DATABASE_URL", "postgresql+psycopg://dzmm@localhost/dzmm")
    monkeypatch.setenv("DZMM_CORE_TOKEN", "core-secret")
    monkeypatch.setenv("DZMM_CHAT_URL", "https://chat.example/chat?c=group-1")

    assert Settings.from_environment().chat_url == "https://chat.example/chat?c=group-1"


def test_settings_reads_optional_minimax_runtime_configuration(monkeypatch):
    monkeypatch.setenv("DZMM_DATABASE_URL", "postgresql+psycopg://dzmm@localhost/dzmm")
    monkeypatch.setenv("DZMM_CORE_TOKEN", "core-secret")
    monkeypatch.setenv("DZMM_MINIMAX_API_KEY", "minimax-secret")

    settings = Settings.from_environment()

    assert settings.minimax_api_key == "minimax-secret"
    assert settings.minimax_model == "MiniMax-M2.5"
    assert settings.minimax_base_url == "https://api.minimax.io/v1"


def test_settings_accepts_the_existing_minimax_api_key_name(monkeypatch):
    monkeypatch.setenv("DZMM_DATABASE_URL", "postgresql+psycopg://dzmm@localhost/dzmm")
    monkeypatch.setenv("DZMM_CORE_TOKEN", "core-secret")
    monkeypatch.delenv("DZMM_MINIMAX_API_KEY", raising=False)
    monkeypatch.setenv("API_KEY", "minimax-secret")

    assert Settings.from_environment().minimax_api_key == "minimax-secret"
