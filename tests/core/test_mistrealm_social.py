from copy import deepcopy
from datetime import datetime,timedelta,timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base,MistrealmRoomRecord,MistrealmSeatRecord
from dzmm_bot.core.mistrealm_api import mistrealm_router
from dzmm_bot.core.mistrealm_v3_cards import STARTER_DECKS


@pytest.fixture
def game(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path/'social.db'}",connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine);factory=sessionmaker(engine,expire_on_commit=False)
    repo=CoreRepository(factory);clock=[datetime(2026,10,16,15,59,30,tzinfo=timezone.utc)]
    app=FastAPI();app.include_router(mistrealm_router(repo,lambda:clock[0]))
    client=TestClient(app);decks={}
    for uid in ('a','b','c'):
        repo.mistrealm_register(uid,uid,None,clock[0])
        deck=deepcopy(STARTER_DECKS[0]);deck.pop('rules_version',None)
        decks[uid]=req(client,uid,'/v3/decks',deck).json()['id']
        req(client,uid,'/social/presence',{})
    return client,clock,decks,factory


def req(c,uid,path,body=None):
    return c.request('POST' if body is not None else 'GET','/api/mistrealm'+path,
        headers={'Authorization':'MistrealmUid '+uid},json=body)


def challenge(g,sender='a',receiver='b'):
    c,_,decks,_=g
    return req(c,sender,'/social/challenges',dict(uid=receiver,deck_id=decks[sender]))


def reply(g,item,operation='accept',uid='b'):
    c,_,decks,_=g
    return req(c,uid,'/social/challenges/'+item['id'],dict(operation=operation,deck_id=decks[uid]))


def test_presence_expiry_sort_search_and_pagination(game):
    c,clock,_,_=game
    assert req(c,'a','/social/presence',{}).json()['online_count']==3
    clock[0]+=timedelta(seconds=61)
    req(c,'b','/social/presence',{})
    rows=req(c,'a','/social/players').json()['items']
    assert [(p['uid'],p['presence']) for p in rows]==[('b','online'),('c','offline')]
    assert req(c,'a','/social/players?search=%25').json()['total']==0
    assert req(c,'a','/social/players?search=c').json()['items'][0]['uid']=='c'
    assert req(c,'a','/social/players?page=1').json()['items']==[]
    assert req(c,'a','/social/players?page=-1').status_code==422
    assert challenge(game,'b','c').status_code==409


def test_friend_consent_duplicate_and_recipient_authority(game):
    c,_,_,_=game
    for _ in range(2):
        assert req(c,'a','/social/friends',dict(uid='b',operation='request')).json()['status']=='pending'
    assert req(c,'a','/social/players?scope=friends').json()['total']==0
    assert req(c,'b','/social/presence',{}).json()['friend_requests']==1
    assert req(c,'a','/social/friends',dict(uid='b',operation='accept')).status_code==409
    assert req(c,'c','/social/friends',dict(uid='b',operation='accept')).status_code==409
    assert req(c,'b','/social/friends',dict(uid='a',operation='accept')).json()['status']=='accepted'
    for uid in ('a','b'):
        assert req(c,uid,'/social/players?scope=friends').json()['total']==1
    assert req(c,'a','/social/friends',dict(uid='a',operation='request')).status_code==409


def test_daily_limit_bilateral_midnight_and_friend_exemption(game):
    c,clock,_,_=game
    first=challenge(game).json()
    assert challenge(game).json()['id']==first['id']
    assert reply(game,first,'decline').status_code==200
    denied=challenge(game,'b','a')
    assert denied.status_code==409 and '每天' in denied.text
    clock[0]+=timedelta(seconds=31) # Beijing midnight, not UTC midnight.
    second=challenge(game,'b','a').json();assert second['id']!=first['id']
    assert reply(game,second,'decline','a').status_code==200
    req(c,'a','/social/friends',dict(uid='b',operation='request'))
    req(c,'b','/social/friends',dict(uid='a',operation='accept'))
    assert challenge(game).status_code==200


def test_accept_creates_one_room_only_after_consent_and_both_clients_recover(game):
    c,_,_,factory=game
    inv=challenge(game).json()
    with factory() as session: assert session.scalar(select(func.count()).select_from(MistrealmRoomRecord))==0
    assert reply(game,inv,uid='c').status_code==403
    assert reply(game,inv,uid='a').status_code==403
    response=reply(game,inv);assert response.status_code==200,response.text
    room=response.json()['room'];assert room['state']['seat']==1 and room['state']['phase']=='waiting'
    assert 'selection' not in room['state']['players'][0]
    assert reply(game,inv).json()['room']['room_id']==room['room_id']
    for uid in ('a','b'):
        pulse=req(c,uid,'/social/presence',{}).json()
        assert pulse['joined_room_id']==room['room_id']
        assert 'deck_snapshot' not in str(pulse)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(MistrealmRoomRecord))==1
        assert session.scalar(select(func.count()).select_from(MistrealmSeatRecord))==2
    assert challenge(game,'c','a').status_code==409


def test_expired_cancelled_busy_and_invalid_deck_do_not_create_rooms(game):
    c,clock,decks,factory=game
    assert req(c,'a','/social/challenges',dict(uid='b',deck_id=decks['b'])).status_code==404
    inv=challenge(game).json()
    assert reply(game,inv,'cancel').status_code==403
    clock[0]+=timedelta(seconds=61)
    assert reply(game,inv).status_code==409
    inv=challenge(game,'c','b')
    assert inv.status_code==409 # offline
    for uid in ('b','c'):req(c,uid,'/social/presence',{})
    inv=challenge(game,'c','b').json()
    assert reply(game,inv,'cancel','c').status_code==200
    assert reply(game,inv).status_code==409
    with factory() as session: assert session.scalar(select(func.count()).select_from(MistrealmRoomRecord))==0


def test_match_or_room_started_while_invite_pending_cannot_be_interrupted(game):
    c,_,decks,factory=game
    inv=challenge(game).json()
    created=req(c,'b','/v3/rooms',dict(deck_id=decks['b'],request_id=str(uuid4())))
    assert created.status_code==200
    result=reply(game,inv)
    assert result.status_code==409 and '离开' in result.text
    with factory() as session: assert session.scalar(select(func.count()).select_from(MistrealmRoomRecord))==1


def test_unauthenticated_social_routes_rejected(game):
    c,*_=game
    assert c.post('/api/mistrealm/social/presence').status_code==401
    assert c.get('/api/mistrealm/social/players').status_code==401


def test_chat_presence_follows_heartbeat_and_invite_pending_is_visible(game):
    c,clock,_,_=game
    req(c,'b','/channel/messages',{'text':'来一局吗'})
    assert req(c,'a','/channel/messages').json()['items'][0]['player']['online'] is True
    challenge(game)
    player=next(p for p in req(c,'a','/social/players').json()['items'] if p['uid']=='b')
    assert player['challenge_reason']=='已有待回应挑战'
    clock[0]+=timedelta(seconds=61)
    assert req(c,'a','/channel/messages').json()['items'][0]['player']['online'] is False


def befriend(c,a='a',b='b'):
    req(c,a,'/social/friends',dict(uid=b,operation='request'))
    req(c,b,'/social/friends',dict(uid=a,operation='accept'))


def dm(c,uid='a',target='b',text='雾境见',request_id=None):
    return req(c,uid,'/social/messages',dict(uid=target,text=text,request_id=str(request_id or uuid4())))


def test_private_chat_requires_accepted_friendship_and_own_identity(game):
    c,*_=game
    assert dm(c).status_code==403
    req(c,'a','/social/friends',dict(uid='b',operation='request'))
    assert dm(c).status_code==403
    assert req(c,'a','/social/messages?uid=b').status_code==403
    req(c,'b','/social/friends',dict(uid='a',operation='accept'))
    assert dm(c).status_code==200
    for path in ('/social/conversations','/social/messages?uid=b'):
        assert c.get('/api/mistrealm'+path).status_code==401
    assert dm(c,target='a').status_code==409


def test_private_offline_delivery_history_and_unread_survive_reload(game):
    c,clock,_,_=game;befriend(c)
    clock[0]+=timedelta(seconds=61)
    message=dm(c,text='<img src=x onerror=alert(1)>').json()
    assert message['outgoing']
    inbox=req(c,'b','/social/conversations').json()
    assert inbox['items'][0]['unread']==1 and inbox['items'][0]['player']['uid']=='a'
    assert req(c,'b','/social/presence',{}).json()['unread_messages']==1
    req(c,'b','/players/me',{'name':'重新登录'})
    history=req(c,'b','/social/messages?uid=a').json()
    assert history['items'][0]['text']==message['text'] and not history['items'][0]['outgoing']
    assert req(c,'b','/social/presence',{}).json()['unread_messages']==1 # Fetch is not read acknowledgement.
    assert req(c,'c','/social/conversations').json()['total']==0
    assert req(c,'b','/channel/messages').json()['items']==[]


def test_private_read_marker_only_clears_received_messages_through_seen_id(game):
    c,*_=game;befriend(c)
    first=dm(c).json();second=dm(c,text='第二条').json()
    own=dm(c,'b','a','回复').json()
    result=req(c,'b','/social/messages/read',dict(uid='a',through_id=first['id']))
    assert result.status_code==200
    assert req(c,'b','/social/presence',{}).json()['unread_messages']==1
    assert req(c,'a','/social/presence',{}).json()['unread_messages']==1
    req(c,'b','/social/messages/read',dict(uid='a',through_id=own['id']))
    assert req(c,'b','/social/presence',{}).json()['unread_messages']==0
    req(c,'b','/social/messages/read',dict(uid='a',through_id=first['id']))
    assert req(c,'b','/social/presence',{}).json()['unread_messages']==0
    assert req(c,'b','/social/messages/read',dict(uid='a',through_id=second['id']+100)).status_code==404


def test_third_player_cannot_read_or_ack_another_pairs_message(game):
    c,*_=game;befriend(c);befriend(c,'a','c');befriend(c,'b','c')
    message=dm(c,text='仅双方可见').json()
    assert req(c,'c','/social/messages?uid=a').json()['items']==[]
    assert req(c,'c','/social/messages?uid=b').json()['items']==[]
    assert req(c,'c','/social/messages/read',dict(uid='a',through_id=message['id'])).status_code==404
    assert req(c,'b','/social/presence',{}).json()['unread_messages']==1


def test_private_send_retry_is_idempotent_and_cannot_reuse_id_for_different_content(game):
    c,*_=game;befriend(c);key=uuid4()
    first=dm(c,request_id=key).json()
    assert dm(c,request_id=key).json()['id']==first['id']
    assert dm(c,text='不同消息',request_id=key).status_code==409
    assert len(req(c,'b','/social/messages?uid=a').json()['items'])==1
    assert req(c,'b','/social/presence',{}).json()['unread_messages']==1


def test_private_history_paginates_both_directions_without_gaps(game):
    from dzmm_bot.core.schema import MistrealmDirectMessageRecord as Message,MistrealmPlayerRecord as Player
    c,clock,_,factory=game;befriend(c)
    with factory.begin() as s:
        ids={p.platform_uid:p.id for p in s.scalars(select(Player))}
        for i in range(65):s.add(Message(sender_id=ids['a'],receiver_id=ids['b'],text=str(i),request_id=uuid4(),created_at=clock[0]))
    latest=req(c,'b','/social/messages?uid=a').json();assert latest['has_more'] and len(latest['items'])==30
    cursor=latest['items'][0]['id'];older=req(c,'b',f'/social/messages?uid=a&before={cursor}').json()
    assert older['items'][-1]['id']<cursor and len(older['items'])==30
    oldest=req(c,'b',f"/social/messages?uid=a&before={older['items'][0]['id']}").json()
    assert len(oldest['items'])==5 and not oldest['has_more']
    catchup=req(c,'b',f"/social/messages?uid=a&after={oldest['items'][-1]['id']}").json()
    assert catchup['items']==older['items'] and catchup['has_more']
    assert req(c,'b','/social/messages?uid=a&before=3&after=1').status_code==422
    assert req(c,'b','/social/messages?uid=a&before=0').status_code==422


def test_private_text_validation_and_rate_limit(game):
    c,clock,*_=game;befriend(c)
    for _ in range(15):assert req(c,'a','/channel/messages',{'text':'公共频道消息'}).status_code==200
    assert dm(c,text='  ').status_code==409
    assert dm(c,text='').status_code==422
    assert dm(c,text='字'*201).status_code==422
    for _ in range(30): assert dm(c,text='正常消息').status_code==200
    blocked=dm(c)
    assert blocked.status_code==429 and '60秒后重试' in blocked.json()['detail']
    clock[0]+=timedelta(seconds=59,milliseconds=1)
    blocked=dm(c)
    assert blocked.status_code==429 and '1秒后重试' in blocked.json()['detail']
    clock[0]+=timedelta(milliseconds=999)
    assert dm(c).status_code==200
