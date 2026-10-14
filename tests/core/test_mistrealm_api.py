from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, UserRecord
from dzmm_bot.core.mistrealm_api import mistrealm_router

NOW=datetime(2026,10,15,tzinfo=timezone.utc)

@pytest.fixture
def game(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path/'test.db'}",connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    repo=CoreRepository(factory)
    app=FastAPI(); app.include_router(mistrealm_router(repo,lambda:NOW))
    client=TestClient(app)
    for uid in ['a','b','c']:
        assert client.post('/api/mistrealm/players/me',headers=headers(uid),json={'name':uid}).status_code==200
    return client,repo,factory

def headers(uid): return {'Authorization':f'MistrealmUid {uid}'}
def create(client,uid='a',request=None):
    return client.post('/api/mistrealm/rooms',headers=headers(uid),json={'request_id':request or str(uuid4())})
def action(client,room,uid,kind,payload=None,request=None):
    return client.post(f"/api/mistrealm/rooms/{room['room_id']}/actions",headers=headers(uid),json={
        'match_id':room['match_id'],'version':room['state']['version'],'request_id':request or str(uuid4()),'action':kind,'payload':payload or {}})

def test_public_uid_no_employee_and_two_seats(game):
    c,repo,f=game
    room=create(c).json()
    assert room['code'].isdigit() and len(room['code'])==6
    joined=c.post('/api/mistrealm/rooms/join',headers=headers('b'),json={'code':room['code'],'request_id':str(uuid4())})
    assert joined.status_code==200
    assert joined.json()['state']['seat']==1
    assert c.get('/api/mistrealm/rooms/'+room['room_id'],headers=headers('c')).status_code==403
    assert c.post('/api/mistrealm/rooms/join',headers=headers('c'),json={'code':room['code'],'request_id':str(uuid4())}).status_code==409
    with f() as session: assert session.scalar(select(func.count()).select_from(UserRecord))==0

def test_create_idempotency_and_active_room(game):
    c,_,_=game; req=str(uuid4())
    a=create(c,request=req); b=create(c,request=req)
    assert a.json()==b.json()
    assert create(c).json()['room_id']==a.json()['room_id']

def test_actions_versions_and_hidden_cards(game):
    c,_,_=game; room=create(c).json()
    room=c.post('/api/mistrealm/rooms/join',headers=headers('b'),json={'code':room['code'],'request_id':str(uuid4())}).json()
    room=action(c,room,'a','ready').json()
    assert action(c,room,'a','play',{}).status_code==422
    old=room
    room=action(c,room,'b','ready').json()
    assert action(c,old,'a','start').status_code==409
    room=action(c,room,'a','start').json()
    assert room['match_id']
    assert 'hand' not in room['state']['players'][1]
    assert len(room['state']['players'][0]['hand'])==9
    assert c.get('/api/mistrealm/rooms/'+room['room_id'],headers=headers('b')).json()['state']['players'][0].get('hand') is None

def test_duplicate_action_and_changed_payload(game):
    c,_,_=game; room=create(c).json(); request=str(uuid4())
    response=action(c,room,'a','ready',request=request)
    assert response.status_code==200
    assert action(c,room,'a','ready',request=request).json()==response.json()
    assert action(c,room,'a','unready',request=request).status_code==409

def test_identity_validation_and_extra_fields(game):
    c,_,_=game
    assert c.get('/api/mistrealm/players/me').status_code==401
    assert c.post('/api/mistrealm/players/me',headers=headers('a'),json={'name':'a','employee_id':'x'}).status_code==422
    assert c.post('/api/mistrealm/players/me',headers=headers('a'),json={'name':'a','avatar':'http://bad'}).status_code==422

def test_expiry_releases_active_seat(game):
    c,repo,_=game; room=create(c).json()
    later=NOW+timedelta(minutes=31)
    assert repo.mistrealm_me('a',later)['room_id'] is None
    assert repo.mistrealm_create('a',uuid4(),later)['room_id']!=room['room_id']

def test_shared_rate_limit(game):
    c,_,_=game
    for _ in range(5): assert create(c).status_code==200
    assert create(c).status_code==429


def test_rejected_stale_action_commits_expiry(game):
    from dzmm_bot.core.schema import MistrealmRoomRecord
    from dzmm_bot.core.mistrealm_repository import MistrealmError
    from uuid import UUID
    c,repo,f=game
    room=create(c).json()
    room=c.post('/api/mistrealm/rooms/join',headers=headers('b'),json={'code':room['code'],'request_id':str(uuid4())}).json()
    room=action(c,room,'a','ready').json()
    room=action(c,room,'b','ready').json()
    room=action(c,room,'a','start').json()
    later=NOW+timedelta(seconds=46)
    with pytest.raises(MistrealmError):
        repo.mistrealm_action(UUID(room['room_id']),'a',UUID(room['match_id']),room['state']['version'],uuid4(),'mulligan',{'cards':[]},later)
    with f() as session:
        state=session.get(MistrealmRoomRecord,UUID(room['room_id'])).state
        assert state['phase']=='reserve'
        assert state['version']>room['state']['version']
