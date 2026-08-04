from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from dzmm_bot.runtime.settings import Settings


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://dzmm@localhost/dzmm",
        core_token="core-secret",
        admin_token="admin-secret",
        browser_profile=Path("/var/lib/dzmm-browser/profile"),
        login_url=None,
        core_api_port=18120,
        browser_cdp_port=19222,
        admin_web_port=18090,
        novnc_port=16080,
    )


def test_core_production_factory_reads_environment_and_builds_an_asgi_app(monkeypatch):
    from dzmm_bot.core import app as core_app
    from dzmm_bot.core.schema import Base

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(core_app.Settings, "from_environment", _settings)
    monkeypatch.setattr(core_app, "create_session_factory", lambda _: session_factory)

    app = core_app.create_app_from_environment()

    assert TestClient(app).get("/healthz").json()["database_available"] is True


def test_admin_production_factory_reads_environment_and_uses_local_core(monkeypatch):
    from dzmm_bot.admin import app as admin_app

    received = {}

    class FakeCore:
        def __init__(self, base_url, token):
            received["base_url"] = base_url
            received["token"] = token

    monkeypatch.setattr(admin_app.Settings, "from_environment", _settings)
    monkeypatch.setattr(admin_app, "CoreClient", FakeCore)

    app = admin_app.create_app_from_environment()

    assert TestClient(app).get("/healthz").status_code == 200
    assert received == {
        "base_url": "http://127.0.0.1:18120",
        "token": "core-secret",
    }
