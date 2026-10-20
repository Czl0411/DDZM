from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base
from dzmm_bot.core.mistrealm_api import mistrealm_router
from dzmm_bot.core.mistrealm_v3_cards import STARTER_DECKS
from dzmm_bot.core.mistrealm_classic_cards import STARTER_DECKS as OLD_DECKS

NOW=datetime(2026,10,15,tzinfo=timezone.utc)


@pytest.fixture
def client(tmp_path):
    db=create_engine(f"sqlite:///{tmp_path/'v3.db'}",connect_args={'check_same_thread':False})
    Base.metadata.create_all(db);repo=CoreRepository(sessionmaker(db,expire_on_commit=False))
    app=FastAPI();app.include_router(mistrealm_router(repo,lambda:NOW))
    for uid in ('a','b','old'):repo.mistrealm_register(uid,uid,'https://example.com/avatar.png',NOW)
    with TestClient(app) as c:yield c


def req(c,uid,path,body=None,version='v3'):
    return c.request('GET' if body is None else 'POST',f'/api/mistrealm/{version}'+path,
                     headers={'Authorization':f'MistrealmUid {uid}'},json=body)


def save(c,uid,version='v3'):
    d=deepcopy((STARTER_DECKS if version=='v3' else OLD_DECKS)[0]);d.pop('rules_version',None)
    r=req(c,uid,'/decks',d,version);assert r.status_code==200,r.text
    return r.json()


def act(c,uid,r,kind,payload=None):
    response=req(c,uid,f"/rooms/{r['room_id']}/actions",dict(action=kind,payload=payload or {},
                 version=r['state']['version'],match_id=r['match_id'],request_id=str(uuid4())))
    assert response.status_code==200,response.text
    return response.json()


def test_deck_version_isolation_and_missing_room_message(client):
    c=client;v3=save(c,'a');old=save(c,'a','classic')
    assert [x['id'] for x in req(c,'a','/decks').json()['decks']]==[v3['id']]
    assert [x['id'] for x in req(c,'a','/decks',version='classic').json()['decks']]==[old['id']]
    body={k:v for k,v in v3.items() if k!='rules_version'};body['id']=old['id']
    assert req(c,'a','/decks',body).status_code==409
    result=req(c,'a','/rooms/join',dict(code='000000',deck_id=v3['id'],request_id=str(uuid4())))
    assert result.status_code==404 and '不存在' in result.text
    assert req(c,'a','/rooms',dict(deck_id=old['id'],request_id=str(uuid4()))).status_code==409


def test_room_lifecycle_profiles_and_reconnect(client):
    c=client;a=save(c,'a');b=save(c,'b')
    r=req(c,'a','/rooms',dict(deck_id=a['id'],request_id=str(uuid4()))).json()
    r=req(c,'b','/rooms/join',dict(code=r['code'],deck_id=b['id'],request_id=str(uuid4()))).json()
    assert r['state']['players'][0]['name']=='a' and 'selection' not in r['state']['players'][0]
    r=act(c,'a',r,'lock');r=act(c,'b',r,'lock')
    r=act(c,'a',r,'mulligan',{'cards':[]});r=act(c,'b',r,'mulligan',{'cards':[]})
    assert r['state']['rules_version']==3 and r['state']['row_capacity']==4
    assert all(p['hand_count']==7 for p in r['state']['players'])
    uid=('a','b')[r['state']['turn']]
    r=req(c,uid,'/rooms/'+r['room_id']).json()
    m=next(m for m in r['state']['legal_moves'] if m['action']=='play')
    r=act(c,uid,r,'play',m['payload'])
    while r['state']['pending']:
        uid=('a','b')[r['state']['pending']['actor']]
        r=req(c,uid,'/rooms/'+r['room_id']).json()
        r=act(c,uid,r,'choose',{'option':r['state']['pending']['options'][0]['token']})
    restored=req(c,uid,'/rooms/'+r['room_id']).json()
    assert restored['state']['version']==r['state']['version']
    assert restored['state']['players'][0]['avatar']=='https://example.com/avatar.png'
    from urllib.parse import urlencode
    from dzmm_bot.core.mistrealm_sync import history_cursor
    cursor=urlencode(history_cursor(restored))
    delta=req(c,uid,'/rooms/'+r['room_id']+'?'+cursor).json()
    assert delta['history_delta']
    assert delta['state']['action_log']==[] and delta['state']['action_frames']==[]
    assert req(c,'old','/rooms/'+r['room_id']+'?'+cursor).status_code==403
    # Closing a match through the opt-in action path still returns only appended history.
    response=req(c,uid,'/rooms/'+r['room_id']+'/actions?'+cursor,dict(action='concede',payload={},
                 version=restored['state']['version'],match_id=restored['match_id'],request_id=str(uuid4())))
    assert response.status_code==200,response.text
    assert response.json()['history_delta']
    full=req(c,uid,'/rooms/'+r['room_id']).json()
    assert restored['state']['action_log']+response.json()['state']['action_log']==full['state']['action_log']


def test_matchmaking_keeps_versions_separate(client):
    c=client;a=save(c,'a');b=save(c,'b');old=save(c,'old','classic')
    first=req(c,'a','/matchmaking',dict(deck_id=a['id'])).json()
    assert first['rules_version']==3 and first['status']=='waiting'
    assert req(c,'old','/matchmaking',dict(deck_id=old['id']),version='classic').json()['status']=='waiting'
    r=req(c,'b','/matchmaking',dict(deck_id=b['id'])).json()
    assert r['status']=='matched' and r['room']['state']['rules_version']==3
    assert r['room']['state']['phase']=='mulligan'


def test_story_uses_new_engine_and_advances_ai(client):
    c=client;a=save(c,'a')
    response=req(c,'a','/story/start',dict(deck_id=a['id'],chapter=1))
    assert response.status_code==200,response.text
    r=response.json();assert r['state']['rules_version']==3
    r=act(c,'a',r,'mulligan',{'cards':[]})
    assert r['state']['phase']=='playing' and r['state']['turn']==0
    r=act(c,'a',r,'pass')
    assert r['state']['phase'] in ('round_result','finished')


def test_selected_deck_survives_reads_edits_and_is_account_scoped(client):
    c=client;first=save(c,'a');second=save(c,'a')
    selected=lambda uid:req(c,uid,'/decks').json()['selected_deck_id']
    assert selected('a')==second['id']
    assert req(c,'a',f"/decks/{first['id']}/select",{}).status_code==200
    assert selected('a')==first['id']
    other=save(c,'b')
    assert selected('b')==other['id']
    assert req(c,'b',f"/decks/{first['id']}/select",{}).status_code==404
    old=save(c,'a','classic')
    assert req(c,'a',f"/decks/{old['id']}/select",{}).status_code==409
    edited={k:v for k,v in STARTER_DECKS[-1].items() if k!='rules_version'};edited.update(id=second['id'],name='我的常用军团')
    assert req(c,'a','/decks',edited).status_code==200
    restored=req(c,'a','/decks').json()
    assert restored['selected_deck_id']==second['id']
    saved=next(d for d in restored['decks'] if d['id']==second['id'])
    assert all(saved[k]==edited[k] for k in ['name','counts','faction','leader'])
    assert selected('a')==second['id'] and selected('b')==other['id']
    assert req(c,'a',f"/decks/{second['id']}/delete",{}).status_code==200
    assert selected('a')==first['id']
    assert req(c,'a',f"/decks/{first['id']}/delete",{}).status_code==200
    assert selected('a') is None
