from copy import deepcopy
from datetime import datetime,timedelta,timezone
from uuid import UUID,uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.mistrealm_api import mistrealm_router
from dzmm_bot.core.mistrealm_repository import MistrealmError
from dzmm_bot.core.mistrealm_ranked import elo_delta,tier,search_radius
from dzmm_bot.core.mistrealm_v3_cards import STARTER_DECKS
from dzmm_bot.core.schema import Base,MistrealmPlayerRecord as P,MistrealmSeasonRecord as S,MistrealmRatingRecord as R,MistrealmRankedMatchRecord as M,MistrealmRoomRecord as Room

NOW=datetime(2026,10,16,4,tzinfo=timezone.utc)

@pytest.fixture
def ranked(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path/'ranked.db'}",connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    f=sessionmaker(engine,expire_on_commit=False);repo=CoreRepository(f);clock=[NOW];decks={}
    for uid in ['a','b','c','d']:
        repo.mistrealm_register(uid,uid,None,NOW)
        data=deepcopy(STARTER_DECKS[0])
        decks[uid]=UUID(repo.mistrealm_save_deck(uid,None,data['name'],data['faction'],data['leader'],data['counts'],NOW,3)['id'])
    app=FastAPI();app.include_router(mistrealm_router(repo,lambda:clock[0]))
    with TestClient(app) as client:yield repo,f,decks,clock,client


def queue(r,uid,mode='ranked',operation='start',ticket=None):
    repo,_,decks,clock,_=r
    return repo.mistrealm_matchmaking(uid,operation,ticket,clock[0],3,decks[uid] if operation=='start' else None,mode)


def paired(r):
    a=queue(r,'a');assert a['status']=='waiting'
    b=queue(r,'b');assert b['status']=='matched'
    return b['room']


def act(r,room,uid,kind,payload=None,request_id=None):
    return r[0].mistrealm_action(UUID(room['room_id']),uid,UUID(room['match_id']),room['state']['version'],request_id or uuid4(),kind,payload or {},r[3][0])


def profile(r,uid='a'):
    return r[0].mistrealm_ranked_profile(uid,r[3][0])


def test_elo_tiers_and_window():
    assert elo_delta(1000,1000,0)==[16,-16]
    assert elo_delta(1000,1400,0)==[29,-29]
    assert elo_delta(1000,1000,None)==[0,0]
    assert elo_delta(1000,1000,0,16)==[8,-8]
    assert tier(1099)['key']=='bronze' and tier(1100)['key']=='silver'
    assert tier(1800)['next'] is None
    assert [search_radius(x) for x in [0,5,10,50]]==[100,200,300,400]


def test_ranked_isolated_from_casual_and_queue_restores(ranked):
    casual=queue(ranked,'a','casual');rank=queue(ranked,'b')
    assert rank['status']=='waiting' and rank['mode']=='ranked'
    me=ranked[0].mistrealm_me('b',NOW)
    assert me['matchmaking']['mode']=='ranked'
    assert queue(ranked,'b','casual','heartbeat',UUID(rank['ticket']))['status']=='idle'
    room=queue(ranked,'d')['room']
    assert {p['uid'] for p in room['state']['players']}=={'b','d'}
    assert room['code'] is None and room['state']['ranked']['season_id']==1
    assert rank['ticket']!=casual['ticket']


def test_full_match_settles_once_and_rematch_cannot_farm(ranked):
    room=paired(ranked);request=uuid4();end=act(ranked,room,'a','concede',request_id=request)
    assert end['state']['ranked']['result']['deltas']==[-16,16]
    assert profile(ranked)['player']['rating']==984
    assert profile(ranked,'b')['player']['wins']==1
    assert act(ranked,room,'a','concede',request_id=request)==end
    for _ in range(3):ranked[0].mistrealm_view(UUID(room['room_id']),'b',NOW)
    assert profile(ranked,'b')['player']['rating']==1016
    with pytest.raises(MistrealmError,match='重新匹配'):act(ranked,end,'b','rematch')
    act(ranked,end,'a','leave')
    assert profile(ranked,'b')['player']['wins']==1
    with ranked[1]() as s:assert s.scalar(select(func.count()).select_from(M))==1


def test_small_round_does_not_settle_ranked(ranked):
    room=paired(ranked)
    # Let normal engine timeouts finish mulligans and a tied first round.
    for _ in range(6):
        if room['state']['phase']=='round_result':break
        ranked[3][0]+=timedelta(seconds=46)
        room=ranked[0].mistrealm_view(UUID(room['room_id']),'a',ranked[3][0])
    assert room['state']['phase']=='round_result'
    assert profile(ranked)['player']['games']==0
    assert room['state']['ranked']['result'] is None
    for _ in range(6):
        if room['state']['phase']=='finished':break
        ranked[3][0]+=timedelta(seconds=46)
        room=ranked[0].mistrealm_view(UUID(room['room_id']),'a',ranked[3][0])
    assert room['state']['phase']=='finished'
    assert profile(ranked)['player']['draws']==1
    assert profile(ranked)['player']['rating']==1000


def test_ranked_bot_fallback_counts_half_without_bot_ranking(ranked):
    q=queue(ranked,'a');ranked[3][0]+=timedelta(seconds=10)
    room=queue(ranked,'a',operation='heartbeat',ticket=UUID(q['ticket']))['room']
    assert room['state']['mode']=='ranked' and room['state']['players'][1]['is_bot']
    end=act(ranked,room,'a','concede')
    assert end['state']['ranked']['result']['deltas']==[-8,0]
    board=ranked[0].mistrealm_ranked_leaderboard('a',None,0,ranked[3][0])
    assert board['total']==1 and board['items'][0]['uid']=='a'
    with ranked[1]() as s:assert s.scalar(select(func.count()).select_from(P))==4


def test_strength_filter_expands_and_real_opponent_wins_over_fallback(ranked):
    a=queue(ranked,'a')
    queue(ranked,'b',operation='start') # First ensure B has a rating, then cancel by ending this pairing.
    room=ranked[0].mistrealm_me('a',NOW)['room_id']
    view=ranked[0].mistrealm_view(UUID(room),'a',NOW)
    end=act(ranked,view,'a','concede');act(ranked,end,'a','leave')
    with ranked[1].begin() as s:
        player=s.scalar(select(P).where(P.platform_uid=='b'))
        s.get(R,(1,player.id)).rating=1250
    a=queue(ranked,'a');b=queue(ranked,'b')
    assert a['status']==b['status']=='waiting'
    ranked[3][0]+=timedelta(seconds=10)
    room=queue(ranked,'a',operation='heartbeat',ticket=UUID(a['ticket']))['room']
    assert {p['uid'] for p in room['state']['players']}=={'a','b'}


def test_season_rollover_waits_for_old_match_and_grants_reward_once(ranked):
    room=paired(ranked)
    with ranked[1].begin() as s:
        end_at=NOW+timedelta(seconds=5)
        s.get(S,1).ends_at=end_at
    ranked[3][0]=end_at+timedelta(seconds=1)
    info=profile(ranked)
    assert info['season']['id']==2 and info['seasons'][1]['status']=='closing'
    assert info['rewards']==[]
    # Even though it ends during S2, this match belongs to S1.
    end=act(ranked,room,'a','concede')
    assert end['state']['ranked']['season_id']==1
    act(ranked,end,'a','leave')
    info=profile(ranked,'b')
    assert len(info['rewards'])==1 and info['rewards'][0]['season_id']==1
    assert info['player']['rating']==1008 and info['player']['games']==0
    ranked[0].mistrealm_ranked_equip('b',1,ranked[3][0])
    assert profile(ranked,'b')['honor']['title']=='S1 · 青铜征服者'
    assert len(profile(ranked,'b')['rewards'])==1
    with pytest.raises(ValueError):ranked[0].mistrealm_ranked_equip('c',1,ranked[3][0])
    assert ranked[0].mistrealm_ranked_equip('b',None,ranked[3][0])['honor'] is None


def test_queue_ticket_cannot_carry_across_season(ranked):
    q=queue(ranked,'a')
    with ranked[1].begin() as s:s.get(S,1).ends_at=NOW+timedelta(seconds=5)
    ranked[3][0]+=timedelta(seconds=6)
    response=queue(ranked,'a',operation='heartbeat',ticket=UUID(q['ticket']))
    assert response['status']=='idle' and '新赛季' in response['message']
    assert queue(ranked,'a')['ranked']['season']==2


def test_api_leaderboard_validation_and_no_client_scores(ranked):
    client=ranked[4];headers={'Authorization':'MistrealmUid a'}
    assert client.get('/api/mistrealm/v3/ranked').status_code==401
    assert client.get('/api/mistrealm/v3/ranked/leaderboard?page=-1',headers=headers).status_code==422
    assert client.post('/api/mistrealm/v3/ranked/matchmaking',headers=headers,json={'deck_id':str(ranked[2]['a']),'rating':5000}).status_code==422
    end=act(ranked,paired(ranked),'a','concede')
    board=client.get('/api/mistrealm/v3/ranked/leaderboard',headers=headers).json()
    assert [p['uid'] for p in board['items']]==['b','a'] and board['my_position']==2
    assert client.get('/api/mistrealm/v3/ranked/leaderboard?page=1',headers=headers).json()['items']==[]
    assert client.get('/api/mistrealm/v3/ranked',headers=headers).json()['player']['losses']==1


def test_peak_reward_and_soft_reset_are_server_owned(ranked):
    room=paired(ranked)
    with ranked[1].begin() as s:
        season=s.get(S,1)
        assert season.ends_at-season.starts_at==timedelta(days=28)
        p=s.scalar(select(P).where(P.platform_uid=='a'))
        entry=s.get(R,(1,p.id));entry.peak=1300
        season.ends_at=NOW+timedelta(seconds=5)
    end=act(ranked,room,'a','concede');act(ranked,end,'a','leave')
    ranked[3][0]+=timedelta(seconds=6)
    info=profile(ranked)
    assert info['rewards'][0]['badge']=='gold' and info['rewards'][0]['peak']==1300
    assert info['player']['rating']==992
    ranked[0].mistrealm_ranked_equip('a',1,ranked[3][0])
    next_room=paired(ranked)
    assert next_room['state']['players'][0]['honor']['title']=='S1 · 黄金征服者'


def test_casual_bot_and_custom_rooms_never_change_rankings(ranked):
    q=queue(ranked,'a','casual');ranked[3][0]+=timedelta(seconds=10)
    bot=queue(ranked,'a','casual','heartbeat',UUID(q['ticket']))['room']
    assert bot['state']['mode']=='bot' and 'ranked' not in bot['state']
    end=act(ranked,bot,'a','concede');act(ranked,end,'a','leave')
    assert profile(ranked)['player']['games']==0
    with ranked[1]() as s:assert s.scalar(select(func.count()).select_from(M))==0


def test_ranked_bot_can_complete_through_engine_and_deadline_worker(ranked):
    q=queue(ranked,'a');ranked[3][0]+=timedelta(seconds=10)
    room=queue(ranked,'a',operation='heartbeat',ticket=UUID(q['ticket']))['room']
    for _ in range(25):
        ranked[3][0]+=timedelta(seconds=46)
        ranked[0].advance_mistrealm_deadlines(ranked[3][0])
        with ranked[1]() as s:
            record=s.get(M,UUID(room['match_id']))
            if record.finished_at:break
    assert record.finished_at is not None
    assert profile(ranked)['player']['games']==1
    ranked[0].advance_mistrealm_deadlines(ranked[3][0]+timedelta(seconds=46))
    assert profile(ranked)['player']['games']==1


@pytest.mark.parametrize('score',[0,5,1000,1400,1800,2200])
@pytest.mark.parametrize('winner,delta',[(0,8),(1,-8),(None,0)])
def test_ranked_bot_uses_players_match_rating_for_result_and_display(ranked,score,winner,delta):
    delta=max(-score,delta)
    q=queue(ranked,'a')
    queue(ranked,'a',operation='cancel',ticket=UUID(q['ticket']))
    with ranked[1].begin() as s:
        player=s.scalar(select(P).where(P.platform_uid=='a'))
        entry=s.get(R,(1,player.id));entry.rating=score;entry.peak=score
    q=queue(ranked,'a');ranked[3][0]+=timedelta(seconds=10)
    room=queue(ranked,'a',operation='heartbeat',ticket=UUID(q['ticket']))['room']
    assert room['state']['ranked']['ratings']==[score,score]
    assert room['state']['ranked']['tiers']==[tier(score),tier(score)]
    with ranked[1].begin() as s:
        record=s.get(Room,UUID(room['room_id']))
        record.state={**record.state,'phase':'finished','winner':winner};record.phase='finished'
        ranked[0]._rank_settle(s,record,ranked[3][0])
        ranked[0]._rank_settle(s,record,ranked[3][0])
        result=s.get(M,UUID(room['match_id'])).result
        assert result['before']==[score,score]
        assert result['deltas']==[delta,0]
        assert result['after']==[score+delta,score]
    assert profile(ranked)['player']['rating']==score+delta
    assert profile(ranked)['player']['games']==1
