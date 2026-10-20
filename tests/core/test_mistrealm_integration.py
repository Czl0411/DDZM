from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dzmm_bot.core.app import create_app
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base
from dzmm_bot.runtime.settings import Settings

def test_enabled_route_and_cors(tmp_path):
    e=create_engine(f"sqlite:///{tmp_path/'app.db'}",connect_args={"check_same_thread":False})
    Base.metadata.create_all(e)
    repo=CoreRepository(sessionmaker(e,expire_on_commit=False))
    assert TestClient(create_app(repo,'test')).get('/api/mistrealm/players/me').status_code==404
    c=TestClient(create_app(repo,'test',mistrealm_enabled=True))
    response=c.post('/api/mistrealm/players/me',headers={'Authorization':'MistrealmUid outsider','Origin':'null'},json={'name':'旅人'})
    assert response.status_code==200
    assert response.headers['access-control-allow-origin']=='*'
    assert response.headers['cache-control']=='no-store'

def test_setting_default_off(monkeypatch):
    monkeypatch.setenv('DZMM_DATABASE_URL','sqlite://')
    monkeypatch.setenv('DZMM_CORE_TOKEN','test')
    monkeypatch.delenv('DZMM_MISTREALM_ENABLED',raising=False)
    assert Settings.from_environment().mistrealm_enabled is False
    monkeypatch.setenv('DZMM_MISTREALM_ENABLED','true')
    assert Settings.from_environment().mistrealm_enabled is True
