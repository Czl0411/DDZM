"""Run only against a deliberately named disposable local PostgreSQL database."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from uuid import UUID
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, func, inspect
from sqlalchemy.orm import sessionmaker
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import MistrealmSeatRecord as Seat, MistrealmRoomRecord as Room
from dzmm_bot.core.mistrealm_classic_cards import STARTER_DECKS

URL=os.environ.get('MISTREALM_CLASSIC_TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not URL,reason='requires disposable Classic PostgreSQL')
NOW=datetime(2026,10,15,tzinfo=timezone.utc)


def test_migrations_concurrent_pairing_and_saved_snapshot(monkeypatch):
    assert '127.0.0.1:18746/mistrealm_classic_test' in URL
    monkeypatch.setenv('DZMM_DATABASE_URL',URL)
    config=Config('alembic.ini');command.stamp(config,'20261014_110')
    command.upgrade(config,'20261015_112');command.upgrade(config,'20261015_113')
    engine=create_engine(URL);factory=sessionmaker(engine,expire_on_commit=False);repo=CoreRepository(factory)
    decks={}
    for uid in ['a','b','c','d']:
        repo.mistrealm_register(uid,uid,None,NOW)
        d=STARTER_DECKS[0]
        decks[uid]=UUID(repo.mistrealm_save_deck(uid,None,d['name'],d['faction'],d['leader'],d['counts'],NOW)['id'])
    barrier=Barrier(4)
    def start(uid):
        barrier.wait()
        return repo.mistrealm_matchmaking(uid,'start',None,NOW,2,decks[uid])
    with ThreadPoolExecutor(4) as pool: results=dict(zip(decks,pool.map(start,decks)))
    for uid,result in results.items():
        if result['status']=='waiting':repo.mistrealm_matchmaking(uid,'heartbeat',UUID(result['ticket']),NOW,2)
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(Room))==2
        assert s.scalar(select(func.count()).select_from(Seat))==4
        assert len(set(s.scalars(select(Seat.player_id))))==4
        for room in s.scalars(select(Room)):
            assert room.state['rules_version']==2 and room.state['phase']=='mulligan'
            assert all(p['selection']['leader']=='c019' for p in room.state['players'])
    # Dispose completed test rooms before rehearsing a code/schema rollback.
    with factory.begin() as s:
        for room in s.scalars(select(Room)):
            state=dict(room.state);state.update(phase='closed',deadline_ms=None)
            repo._mr_sync(s,room,state)
    command.downgrade(config,'20261015_112')
    assert 'mistrealm_decks' not in inspect(engine).get_table_names()
    command.upgrade(config,'20261015_113')
    assert 'mistrealm_decks' in inspect(engine).get_table_names()
    engine.dispose()
