from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime,timezone
from uuid import UUID
from copy import deepcopy
import os
import pytest
from sqlalchemy import create_engine,select,func,text
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic import command
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import MistrealmInviteRecord as Invite,MistrealmRoomRecord as Room,MistrealmSeatRecord as Seat
from dzmm_bot.core.mistrealm_v3_cards import STARTER_DECKS

URL=os.environ.get('MISTREALM_SOCIAL_TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not URL,reason='requires empty disposable PostgreSQL database')

def test_migration_and_bilateral_challenge_races(monkeypatch):
    monkeypatch.setenv('DZMM_DATABASE_URL',URL)
    url=URL
    cfg=Config('alembic.ini');command.stamp(cfg,'20261014_110');command.upgrade(cfg,'20261015_115')
    engine=create_engine(url);now=datetime.now(timezone.utc)
    # A pre-migration player remains intact across upgrade/downgrade/upgrade.
    with engine.begin() as c:
     c.execute(text("insert into mistrealm_players (id,platform_uid,name,created_at,updated_at,rate_limits) values ('00000000-0000-0000-0000-000000000001','preserved','旧玩家',now(),now(),'{}')"))
    for target in ('20261016_116','20261015_115','20261016_116'):
     (command.downgrade if target.endswith('115') else command.upgrade)(cfg,target)
     with engine.connect() as c:assert c.execute(text("select name from mistrealm_players where platform_uid='preserved'")).scalar()=='旧玩家'
    command.upgrade(cfg,'20261016_120')
    factory=sessionmaker(engine,expire_on_commit=False);repo=CoreRepository(factory);decks={}
    for uid in ('a','b','c'):
     repo.mistrealm_register(uid,uid,None,now);repo.mistrealm_social_pulse(uid,now)
     d=deepcopy(STARTER_DECKS[0]);decks[uid]=repo.mistrealm_save_deck(uid,None,d['name'],d['faction'],d['leader'],d['counts'],now,3)['id']
    barrier=Barrier(2)
    def simultaneous(i):
     barrier.wait();sender,receiver=('a','b') if i==0 else ('b','a')
     return repo.mistrealm_invite(sender,receiver,UUID(decks[sender]),now)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(simultaneous,[0,1]))
    assert results[0]['id']==results[1]['id']
    with factory() as s:
     item=s.get(Invite,UUID(results[0]['id']));receiver='b' if results[0]['outgoing'] else 'a'
    barrier=Barrier(2)
    def accept(_):
     barrier.wait();return repo.mistrealm_invite_reply(receiver,item.id,'accept',UUID(decks[receiver]),now)
    with ThreadPoolExecutor(2) as pool:rooms=list(pool.map(accept,[0,1]))
    assert rooms[0]['room']['room_id']==rooms[1]['room']['room_id']
    with factory() as s:
     assert s.scalar(select(func.count()).select_from(Room))==1
     assert s.scalar(select(func.count()).select_from(Seat))==2
     assert s.scalar(select(func.count()).select_from(Invite))==1

    # The new migration preserves an existing friendship; private send retries race safely.
    repo.mistrealm_friend('a','b','request',now);repo.mistrealm_friend('b','a','accept',now)
    command.downgrade(cfg,'20261016_116');command.upgrade(cfg,'20261016_120')
    assert repo.mistrealm_social_players('a','friends','',0,now)['total']==1
    from uuid import uuid4
    from dzmm_bot.core.schema import MistrealmDirectMessageRecord as Message
    request_id=uuid4();barrier=Barrier(2)
    def send(_):
     barrier.wait();return repo.mistrealm_dm_send('a','b','并发重试',request_id,now)
    with ThreadPoolExecutor(2) as pool:messages=list(pool.map(send,[0,1]))
    assert messages[0]['id']==messages[1]['id']
    with factory() as s:assert s.scalar(select(func.count()).select_from(Message))==1
    assert repo.mistrealm_social_pulse('b',now)['unread_messages']==1
    repo.mistrealm_dm_read('b','a',messages[0]['id'],now)
    assert repo.mistrealm_social_pulse('b',now)['unread_messages']==0
