from copy import deepcopy
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, MistrealmPlayerRecord, MistrealmRoomRecord
from dzmm_bot.core.mistrealm_api import mistrealm_router
from dzmm_bot.core.mistrealm_classic_cards import STARTER_DECKS

NOW=datetime(2026,10,15,tzinfo=timezone.utc)
PREFIX='/api/mistrealm/classic'

def headers(uid):return {'Authorization':f'MistrealmUid {uid}'}

@pytest.fixture
def game(tmp_path):
    db=create_engine(f"sqlite:///{tmp_path/'classic.db'}",connect_args={'check_same_thread':False})
    Base.metadata.create_all(db);factory=sessionmaker(db,expire_on_commit=False);repo=CoreRepository(factory)
    app=FastAPI();app.include_router(mistrealm_router(repo,lambda:NOW));client=TestClient(app)
    for uid in ['a','b','c']:repo.mistrealm_register(uid,uid,'https://example.com/avatar.png',NOW)
    return client,repo,factory

def save(c,uid='a',index=0,**extra):
    body=deepcopy(STARTER_DECKS[index]);body.update(extra)
    r=c.post(PREFIX+'/decks',headers=headers(uid),json=body)
    assert r.status_code==200,r.text
    return r.json()

def request(c,uid,path,body=None):return c.post(PREFIX+path,headers=headers(uid),json=body or {})

def room(c,uid,deck):return request(c,uid,'/rooms',dict(deck_id=deck['id'],request_id=str(uuid4())))

def action(c,uid,r,kind,payload=None):
    return request(c,uid,f"/rooms/{r['room_id']}/actions",dict(action=kind,payload=payload or {},match_id=r['match_id'],version=r['state']['version'],request_id=str(uuid4())))

def test_saved_decks_are_private_and_owner_only(game):
    c,_,_=game;d=save(c)
    assert c.get(PREFIX+'/decks',headers=headers('a')).json()['decks'][0]['id']==d['id']
    assert c.get(PREFIX+'/decks',headers=headers('b')).json()['decks']==[]
    assert request(c,'b','/decks',dict(STARTER_DECKS[0],id=d['id'])).status_code==404
    assert request(c,'b',f"/decks/{d['id']}/delete").status_code==404
    assert room(c,'b',d).status_code==404
    assert request(c,'a',f"/decks/{d['id']}/delete").status_code==200
    assert c.get(PREFIX+'/decks').status_code==401


def test_server_rejects_illegal_deck_even_if_client_claims_it_is_valid(game):
    c,_,_=game;body=deepcopy(STARTER_DECKS[0]);body['counts']['c021']=1
    assert request(c,'a','/decks',body).status_code==409
    body['counts']={'c001':True}
    assert request(c,'a','/decks',body).status_code in (409,422)


def test_private_room_lock_and_saved_edit_do_not_change_locked_snapshot(game):
    c,_,f=game;a=save(c);b=save(c,'b',3)
    r=room(c,'a',a).json()
    joined=request(c,'b','/rooms/join',dict(code=r['code'],deck_id=b['id'],request_id=str(uuid4())))
    assert joined.status_code==200,joined.text
    r=joined.json()
    assert r['state']['players'][0]==dict(uid='a',locked=False,name='a',avatar='https://example.com/avatar.png')
    r=action(c,'a',r,'lock').json()
    save(c,'a',1,id=a['id'])
    assert request(c,'a',f"/decks/{a['id']}/delete").status_code==409
    r=action(c,'b',r,'lock').json()
    assert r['match_id'] and r['state']['players'][0]['leader']=='c019'
    assert 'hand' not in r['state']['players'][0]
    assert r['state']['players'][0]['name']=='a'
    assert action(c,'a',r,'unlock').status_code==409
    assert c.get(PREFIX+'/rooms/'+r['room_id'],headers=headers('c')).status_code==403
    with f() as s: assert s.get(MistrealmRoomRecord,UUID(r['room_id'])).state['players'][0]['selection']['leader']=='c019'


def test_player_can_observe_closed_room_after_opponent_leaves(game):
    c,_,f=game;a=save(c);b=save(c,'b',3)
    r=room(c,'a',a).json()
    r=request(c,'b','/rooms/join',dict(code=r['code'],deck_id=b['id'],request_id=str(uuid4()))).json()
    with f.begin() as session:
        record=session.get(MistrealmRoomRecord,UUID(r['room_id']))
        state=deepcopy(record.state);state.update(phase='finished',winner=0,deadline_ms=None)
        record.state=state;record.phase='finished'
    r=c.get(PREFIX+'/rooms/'+r['room_id'],headers=headers('a')).json()
    assert action(c,'a',r,'leave').json()['state']['phase']=='closed'
    closed=c.get(PREFIX+'/rooms/'+r['room_id'],headers=headers('b'))
    assert closed.status_code==200,closed.text
    assert closed.json()['state']['phase']=='closed'


def test_queues_are_versioned_and_snapshot_survives_save(game):
    c,repo,f=game;a=save(c);b=save(c,'b',3)
    first=request(c,'a','/matchmaking',{'deck_id':a['id']})
    assert first.status_code==200,first.text
    ticket=first.json()['ticket']
    save(c,'a',1,id=a['id'])
    resumed=repo.mistrealm_me('a',NOW)['matchmaking']
    assert resumed['rules_version']==2
    assert resumed['deck']=={'id':a['id'],'name':a['name'],'faction':a['faction'],'leader':a['leader']}
    # Old clients cannot pair with a Classic queue.
    old=repo.mistrealm_matchmaking('c','start',None,NOW)
    assert old['status']=='waiting'
    paired=request(c,'b','/matchmaking',{'deck_id':b['id']}).json()
    assert paired['status']=='matched'
    assert paired['room']['state']['players'][0]['leader']=='c019'
    assert paired['room']['state']['phase']=='mulligan'
    with f() as s:
        p=s.scalar(select(MistrealmPlayerRecord).where(MistrealmPlayerRecord.platform_uid=='c'))
        assert p.queue_ticket is not None
    late=request(c,'a','/matchmaking/cancel',{'ticket':ticket}).json()
    assert late['status']=='matched'


def test_late_ticket_and_deck_switch_do_not_mutate_queue(game):
    c,_,_=game;a=save(c);other=save(c,index=1)
    q=request(c,'a','/matchmaking',{'deck_id':a['id']}).json()
    assert request(c,'a','/matchmaking',{'deck_id':other['id']}).status_code==409
    late=request(c,'a','/matchmaking/cancel',{'ticket':str(uuid4())}).json()
    assert late['ticket']==q['ticket']
    assert request(c,'a','/matchmaking/heartbeat',{'ticket':str(uuid4())}).json()['status']=='idle'
    assert request(c,'a','/matchmaking/cancel',{'ticket':q['ticket']}).json()['status']=='idle'
    newer=request(c,'a','/matchmaking',{'deck_id':other['id']}).json()
    assert newer['ticket']!=q['ticket']
    assert request(c,'a','/matchmaking/heartbeat',{'ticket':q['ticket']}).json()['status']=='idle'


def test_v1_room_cannot_be_joined_with_classic_deck(game):
    c,repo,_=game;old=repo.mistrealm_create('a',uuid4(),NOW);d=save(c,'b',3)
    r=request(c,'b','/rooms/join',dict(code=old['code'],deck_id=d['id'],request_id=str(uuid4())))
    assert r.status_code==409
    assert repo.mistrealm_view(UUID(old['room_id']),'a',NOW)['state']['players'][1] is None
