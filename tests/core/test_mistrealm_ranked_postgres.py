"""Concurrent settlement and migrations on an explicitly disposable PostgreSQL DB."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from threading import Barrier
from uuid import UUID,uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine,select,func,text,inspect
from sqlalchemy.orm import sessionmaker
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.mistrealm_repository import MistrealmError
from dzmm_bot.core.mistrealm_v3_cards import STARTER_DECKS
from dzmm_bot.core.schema import MistrealmPlayerRecord as P,MistrealmRatingRecord as R,MistrealmRankedMatchRecord as M,MistrealmSeasonRecord as S

URL=os.environ.get('MISTREALM_RANKED_TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not URL,reason='requires disposable MISTREALM_RANKED_TEST_DATABASE_URL')
NOW=datetime(2026,10,16,4,tzinfo=timezone.utc)


def test_ranked_migration_concurrency_and_rollover(monkeypatch):
    monkeypatch.setenv('DZMM_DATABASE_URL',URL)
    cfg=Config('alembic.ini');command.stamp(cfg,'20261014_110');command.upgrade(cfg,'20261016_120')
    engine=create_engine(URL);f=sessionmaker(engine,expire_on_commit=False);repo=CoreRepository(f);decks={}
    for uid in ['a','b','c','d']:
        repo.mistrealm_register(uid,uid,None,NOW)
        d=STARTER_DECKS[0];decks[uid]=UUID(repo.mistrealm_save_deck(uid,None,d['name'],d['faction'],d['leader'],d['counts'],NOW,3)['id'])
    # Preference survives fresh sessions; the additive migration keeps existing decks.
    for uid in decks:assert repo.mistrealm_decks(uid,NOW,3)['selected_deck_id']==str(decks[uid])
    command.downgrade(cfg,'20261016_119')
    command.upgrade(cfg,'20261016_120')
    for uid in decks:
        assert repo.mistrealm_decks(uid,NOW,3)['selected_deck_id']==str(decks[uid])
        repo.mistrealm_select_v3_deck(uid,decks[uid],NOW)
    barrier=Barrier(4)
    def queue(uid):
        barrier.wait()
        return repo.mistrealm_matchmaking(uid,'start',None,NOW,3,decks[uid],'ranked')
    with ThreadPoolExecutor(4) as pool:list(pool.map(queue,decks))
    # Simultaneous starts may SKIP LOCKED; live queue heartbeats finish pairing.
    for uid in decks:
        p=repo.mistrealm_me(uid,NOW)
        if p['matchmaking']['status']=='waiting':
            repo.mistrealm_matchmaking(uid,'heartbeat',UUID(p['matchmaking']['ticket']),NOW,3,None,'ranked')
    with f() as s:
        matches=list(s.scalars(select(M)))
        assert len(matches)==2 and len({m.room_id for m in matches})==2
        assert s.scalar(select(func.count()).select_from(R))==4
        assert s.scalar(select(func.count()).select_from(S))==1
    rooms={repo.mistrealm_me(uid,NOW)['room_id'] for uid in decks};assert None not in rooms and len(rooms)==2
    room_id=next(iter(rooms))
    with f() as s:
        m=s.scalar(select(M).where(M.room_id==UUID(room_id)))
        users=[s.get(P,p).platform_uid for p in [m.player_a,m.player_b]]
    room=repo.mistrealm_view(UUID(room_id),users[0],NOW)
    barrier=Barrier(2)
    def concede(uid):
        barrier.wait()
        try:return repo.mistrealm_action(UUID(room_id),uid,UUID(room['match_id']),room['state']['version'],uuid4(),'concede',{},NOW)
        except (MistrealmError,ValueError):return None
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(concede,users))
    assert any(results)
    with f() as s:
        a=s.get(M,UUID(room['match_id']))
        assert a.finished_at and sum(a.result['deltas'])==0
        values=list(s.scalars(select(R).where(R.player_id.in_([a.player_a,a.player_b]))))
        assert sum(r.wins for r in values)==1 and sum(r.losses for r in values)==1
        assert sum(r.rating for r in values)==2000
    # Concurrent readers do not grant an unfinished season early or duplicate rewards.
    with f.begin() as s:s.get(S,1).ends_at=NOW+timedelta(seconds=1)
    later=NOW+timedelta(seconds=2)
    with ThreadPoolExecutor(4) as pool:infos=list(pool.map(lambda uid:repo.mistrealm_ranked_profile(uid,later),decks))
    assert all(info['season']['id']==2 for info in infos)
    assert all(not info['rewards'] for info in infos)
    for rid in rooms-{room_id}:
        with f() as s:
            m=s.scalar(select(M).where(M.room_id==UUID(rid)));uid=s.get(P,m.player_a).platform_uid
        view=repo.mistrealm_view(UUID(rid),uid,later)
        repo.mistrealm_action(UUID(rid),uid,UUID(view['match_id']),view['state']['version'],uuid4(),'concede',{},later)
    with ThreadPoolExecutor(4) as pool:infos=list(pool.map(lambda uid:repo.mistrealm_ranked_profile(uid,later),decks))
    assert all(len(info['rewards'])==1 for info in infos)
    with f() as s:
        assert s.scalar(select(func.count()).select_from(S))==2
        original=list(s.execute(text('select platform_uid,name from mistrealm_players order by platform_uid')))
    command.downgrade(cfg,'20261016_118')
    assert 'mistrealm_ratings' not in inspect(engine).get_table_names()
    with engine.connect() as c:assert list(c.execute(text('select platform_uid,name from mistrealm_players order by platform_uid')))==original
    command.upgrade(cfg,'20261016_120')
    with f() as s:assert all(p.queue_mode=='casual' for p in s.scalars(select(P)))
    engine.dispose()
