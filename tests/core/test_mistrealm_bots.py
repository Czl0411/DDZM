from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from random import Random
from uuid import UUID, uuid4
import xml.etree.ElementTree as ET

import pytest
from sqlalchemy import func, select

from dzmm_bot.core import mistrealm_bots as bots, mistrealm_story as story, mistrealm_v3_state as v3
from dzmm_bot.core.mistrealm_repository import MistrealmError
from dzmm_bot.core.mistrealm_v3_cards import STARTER_DECKS
from dzmm_bot.core.schema import MistrealmPlayerRecord as Player, MistrealmRoomRecord as Room, MistrealmSeatRecord as Seat, MistrealmStoryProgressRecord as Progress
from tests.core.test_mistrealm_api import game, NOW


def deck(repo, uid='a', index=0):
    d=deepcopy(STARTER_DECKS[index])
    return repo.mistrealm_save_deck(uid,None,d['name'],d['faction'],d['leader'],d['counts'],NOW,3)


def pulse(repo, ticket, seconds=10, uid='a'):
    return repo.mistrealm_matchmaking(uid,'heartbeat',ticket,NOW+timedelta(seconds=seconds),3)


def start(repo, uid='a', index=0):
    d=deck(repo,uid,index)
    return repo.mistrealm_matchmaking(uid,'start',None,NOW,3,UUID(d['id']))


def act(repo, room, action, payload=None, seconds=11, request_id=None):
    return repo.mistrealm_action(UUID(room['room_id']),'a',UUID(room['match_id']),room['state']['version'],
                                request_id or uuid4(),action,payload or {},NOW+timedelta(seconds=seconds))


def test_fallback_threshold_identity_reconnect_and_single_membership(game):
    _,repo,factory=game
    q=start(repo)
    assert pulse(repo,q['ticket'],9.999)['status']=='waiting'
    result=pulse(repo,q['ticket'])
    assert result['status']=='matched'
    r=result['room'];p=r['state']['players'][1]
    assert r['code'] is None and r['state']['mode']=='bot' and r['state']['balance_revision']==2
    assert p['is_bot'] and p['name'] in bots.NAMES and p['avatar'].startswith('../assets/bots/')
    assert 'hand' not in p and 'deck' not in p
    assert r['state']['deadline_ms'] is not None
    assert pulse(repo,q['ticket'],11)['room']['room_id']==r['room_id']
    assert repo.mistrealm_me('a',NOW+timedelta(seconds=11))['room_id']==r['room_id']
    restored=repo.mistrealm_view(UUID(r['room_id']),'a',NOW+timedelta(seconds=11))
    assert restored['state']['players'][1]==p
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(Room))==1
        assert s.scalar(select(func.count()).select_from(Seat))==1
        assert s.scalar(select(func.count()).select_from(Player))==3
        assert s.scalar(select(func.count()).select_from(Progress))==0
    with pytest.raises(MistrealmError):repo.mistrealm_view(UUID(r['room_id']),'b',NOW)


def test_waiting_real_player_wins_at_fallback_boundary(game):
    _,repo,factory=game
    q=start(repo);other=deck(repo,'b')
    # Simulate an already committed real queue entry at the fallback boundary.
    with factory() as s:
        p=s.scalar(select(Player).where(Player.platform_uid=='b'))
        p.queue_ticket=uuid4();p.queued_at=NOW+timedelta(seconds=9)
        p.queue_expires_at=NOW+timedelta(seconds=29);p.queue_rules_version=3
        p.queue_snapshot={**other,'deck_id':other['id']};s.commit()
    r=pulse(repo,q['ticket'])['room']
    assert r['state'].get('mode')!='bot'
    assert {p['uid'] for p in r['state']['players']}=={'a','b'}


def test_cancel_at_boundary_and_old_tickets_do_not_spawn_bots(game):
    _,repo,factory=game
    q=start(repo)
    assert repo.mistrealm_matchmaking('a','cancel',q['ticket'],NOW+timedelta(seconds=10),3)['status']=='idle'
    assert pulse(repo,q['ticket'],11)['status']=='idle'
    d=deck(repo)
    fresh=repo.mistrealm_matchmaking('a','start',None,NOW+timedelta(seconds=11),3,UUID(d['id']))
    assert pulse(repo,q['ticket'],12)['status']=='idle'
    assert pulse(repo,fresh['ticket'],20)['status']=='waiting'
    assert pulse(repo,fresh['ticket'],21)['status']=='matched'
    with factory() as s:assert s.scalar(select(func.count()).select_from(Room))==1


def test_expired_lease_does_not_start_offline_bot_match(game):
    _,repo,factory=game
    q=start(repo)
    assert pulse(repo,q['ticket'],21)['status']=='idle'
    with factory() as s:assert s.scalar(select(func.count()).select_from(Room))==0


def test_later_real_player_cannot_enter_existing_bot_match(game):
    _,repo,_=game
    r=pulse(repo,start(repo)['ticket'])['room']
    d=deck(repo,'b')
    q=repo.mistrealm_matchmaking('b','start',None,NOW+timedelta(seconds=11),3,UUID(d['id']))
    assert q['status']=='waiting'
    assert pulse(repo,q['ticket'],21,uid='b')['room']['room_id']!=r['room_id']


def test_bot_actions_rematch_replay_and_exit(game):
    _,repo,factory=game
    r=pulse(repo,start(repo)['ticket'])['room']
    profile={k:r['state']['players'][1][k] for k in ('uid','name','avatar')}
    r=act(repo,r,'mulligan',{'cards':[]})
    assert r['state']['phase']=='playing' and r['state']['turn']==0
    r=act(repo,r,'pass')
    assert r['state']['phase'] in ('round_result','finished')
    r=repo.mistrealm_view(UUID(r['room_id']),'a',NOW+timedelta(seconds=17))
    if r['state']['phase']!='finished':r=act(repo,r,'concede',seconds=17)
    before=r;request=uuid4()
    r=act(repo,r,'rematch',seconds=18,request_id=request)
    assert act(repo,before,'rematch',seconds=18,request_id=request)==r
    assert r['match_id']!=before['match_id'] and r['state']['phase']=='mulligan'
    assert r['state']['mode']=='bot'
    assert {k:r['state']['players'][1][k] for k in profile}==profile
    r=act(repo,r,'concede',seconds=19)
    r=act(repo,r,'leave',seconds=20)
    assert r['state']['phase']=='closed'
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(Seat))==0
        assert s.scalar(select(func.count()).select_from(Progress))==0
    assert pulse(repo,'stale-ticket',21)['status']=='idle'


def test_deadline_job_keeps_bot_games_moving(game):
    _,repo,_=game
    r=pulse(repo,start(repo)['ticket'])['room']
    repo.advance_mistrealm_deadlines(NOW+timedelta(seconds=71))
    r=repo.mistrealm_view(UUID(r['room_id']),'a',NOW+timedelta(seconds=71))
    assert r['state']['phase']=='playing' and r['state']['turn']==0
    assert r['state']['deadline_ms'] is not None


@pytest.mark.parametrize('seed',range(20))
def test_full_bot_matches_all_starters_finish_without_stalling(seed):
    rng=Random(seed);now=1000
    state=bots.new_match('human',deepcopy(STARTER_DECKS[seed%10]),now,rng)
    for _ in range(250):
        if state['phase']=='finished':break
        if state['phase']=='round_result':
            now=state['deadline_ms'];state=v3.advance(state,now,rng)
        state=story.drive(state,now,rng)
        if state['phase']=='finished':break
        if state['phase']=='round_result':continue
        moves=[m for m in v3.legal_moves(state,0) if m['action']!='concede']
        assert moves
        play=[m for m in moves if m['action']=='play']
        move=rng.choice(play or moves)
        state=v3.apply_action(state,0,move['action'],move['payload'],now,rng)
        state=story.drive(state,now,rng)
        now+=1000
    assert state['phase']=='finished'
    assert 1<=len(state['history'])<=3
    assert state['mode']=='bot'


def test_avatar_library_is_bundled_unique_and_passive_svg():
    root=Path(__file__).resolve().parents[2]/'gamefy/mistrealm/publish/assets/bots'
    images=[(root/f'lorelei-{i:02}.svg').read_bytes() for i in range(1,bots.AVATAR_COUNT+1)]
    assert len(set(images))==bots.AVATAR_COUNT
    assert len(bots.NAMES)==len(set(bots.NAMES))==64
    for image in images:
        svg=ET.fromstring(image)
        for node in svg.iter():
            assert node.tag.rsplit('}',1)[-1] not in ('script','foreignObject','image')
            assert not any(key.lower().startswith('on') for key in node.attrib)
            assert all(value.startswith('#') for key,value in node.attrib.items() if key.rsplit('}',1)[-1]=='href')
    assert 'CC0' in (root/'LICENSE.txt').read_text()
