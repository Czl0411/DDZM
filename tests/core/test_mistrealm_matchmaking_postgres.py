"""Matchmaking races in a disposable PostgreSQL database."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, func, inspect
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import MistrealmSeatRecord as Seat, MistrealmRoomRecord as Room

URL=os.environ.get('MISTREALM_TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not URL,reason='requires disposable PostgreSQL')
NOW=datetime(2026,10,15,tzinfo=timezone.utc)


def test_pairing_and_cancellation_races(monkeypatch):
    monkeypatch.setenv('DZMM_DATABASE_URL',URL)
    config=Config('alembic.ini')
    command.stamp(config,'20261014_110')
    command.upgrade(config,'20261016_120')
    engine=create_engine(URL)
    factory=sessionmaker(engine,expire_on_commit=False)
    repo=CoreRepository(factory)
    for uid in ['a','b','c','d','e','f','g']:
        repo.mistrealm_register(uid,uid,None,NOW)
    barrier=Barrier(4)
    def start(uid):
        barrier.wait()
        return repo.mistrealm_matchmaking(uid,'start',None,NOW)
    with ThreadPoolExecutor(4) as pool:
        results=dict(zip(['a','b','c','d'],pool.map(start,['a','b','c','d'])))
    # Simultaneous starts may skip one another's locked rows; next heartbeat resolves them.
    for uid,result in results.items():
        if result['status']=='waiting':
            repo.mistrealm_matchmaking(uid,'heartbeat',result['ticket'],NOW)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Room))==2
        assert session.scalar(select(func.count()).select_from(Seat))==4
        assert len(set(session.scalars(select(Seat.player_id))))==4

    ticket=repo.mistrealm_matchmaking('e','start',None,NOW)['ticket']
    barrier=Barrier(2)
    def cancel_or_pair(i):
        barrier.wait()
        return repo.mistrealm_matchmaking('e' if i==0 else 'f','cancel' if i==0 else 'start',ticket if i==0 else None,NOW)
    with ThreadPoolExecutor(2) as pool:
        responses=list(pool.map(cancel_or_pair,[0,1]))
    assert [x['status'] for x in responses] in [['idle','waiting'],['matched','matched']]

    barrier=Barrier(2)
    def queue_or_manual(i):
        barrier.wait()
        return (repo.mistrealm_matchmaking('g','start',None,NOW) if i==0 else repo.mistrealm_create('g',uuid4(),NOW))
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(queue_or_manual,[0,1]))
    me=repo.mistrealm_me('g',NOW)
    assert me['room_id'] is not None and me['matchmaking']['status']=='idle'

    command.downgrade(config,'20261015_111')
    assert 'queue_ticket' not in {c['name'] for c in inspect(engine).get_columns('mistrealm_players')}
    command.upgrade(config,'20261015_112')
    assert 'queue_ticket' in {c['name'] for c in inspect(engine).get_columns('mistrealm_players')}
    command.downgrade(config,'20261014_110')
