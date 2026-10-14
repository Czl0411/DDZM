"""Run against a disposable PostgreSQL database only."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.mistrealm_repository import MistrealmError

URL=os.environ.get('MISTREALM_TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not URL,reason='requires disposable PostgreSQL MISTREALM_TEST_DATABASE_URL')
NOW=datetime(2026,10,15,tzinfo=timezone.utc)

def test_migration_and_concurrent_seats(monkeypatch):
    monkeypatch.setenv('DZMM_DATABASE_URL',URL)
    config=Config('alembic.ini')
    command.stamp(config,'20261014_110')
    command.upgrade(config,'20261015_112')
    engine=create_engine(URL)
    repo=CoreRepository(sessionmaker(engine,expire_on_commit=False))
    for uid in ['a','b','c','d']:
        repo.mistrealm_register(uid,uid,None,NOW)
    room=repo.mistrealm_create('a',uuid4(),NOW)
    barrier=Barrier(2)
    def join(uid):
        barrier.wait()
        try: return repo.mistrealm_join(uid,room['code'],uuid4(),NOW)
        except MistrealmError as e: return e.status
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(join,['b','c']))
    assert sum(isinstance(r,dict) for r in results)==1
    assert 409 in results
    barrier=Barrier(2)
    def create(_):
        barrier.wait()
        return repo.mistrealm_create('d',uuid4(),NOW)
    with ThreadPoolExecutor(2) as pool:
        rooms=list(pool.map(create,[0,1]))
    assert rooms[0]['room_id']==rooms[1]['room_id']
    command.downgrade(config,'20261014_110')
    assert not any(n.startswith('mistrealm_') for n in inspect(engine).get_table_names())
    command.upgrade(config,'20261015_112')
    assert len([n for n in inspect(engine).get_table_names() if n.startswith('mistrealm_')])==4
    command.downgrade(config,'20261014_110')
