"""Friend spectators receive public data and never acquire a player seat."""
from copy import deepcopy
from uuid import UUID,uuid4
from sqlalchemy import select,func

from tests.core.test_mistrealm_social import game,req,challenge,reply
from tests.core.test_mistrealm_v3 import empty,add
from dzmm_bot.core.schema import MistrealmRoomRecord as Room,MistrealmSeatRecord as Seat,MistrealmFriendRecord as Friend


def setup_match(g):
    c,clock,decks,factory=g
    room=reply(g,challenge(g).json()).json()['room']
    req(c,'c','/social/friends',dict(uid='a',operation='request'))
    req(c,'a','/social/friends',dict(uid='c',operation='accept'))
    state=empty();state['deadline_ms']=int(clock[0].timestamp()*1000)+60000
    state['players'][0]['uid']='a';state['players'][1]['uid']='b'
    add(state,'c101',zone='rows');add(state,'c081',seat=1,zone='rows')
    add(state,'c082',zone='hand')['id']='private-hand-a'
    add(state,'c083',seat=1,zone='hand')['id']='private-hand-b'
    add(state,'c084',zone='deck')['id']='private-deck-a'
    state['pending']=dict(actor=0,kind='v3',title='private-title',options=[dict(token='private-token',label='private-label',ops=[])])
    match=uuid4()
    with factory.begin() as session:
        stored=session.get(Room,UUID(room['room_id']));stored.state=state;stored.phase='playing';stored.match_id=match
    return room['room_id'],str(match)


def watch(c,room,match,uid='c',target='a'):
    return req(c,uid,f'/v3/rooms/{room}?watch={target}&watch_match={match}')


def test_friend_watch_hides_private_choices_hands_and_keeps_seats_unchanged(game):
    c,_,_,factory=game;room,match=setup_match(game)
    listing=req(c,'c','/social/players?scope=friends').json()['items'][0]
    assert listing['spectate_room_id']==room and listing['spectate_match_id']==match
    response=watch(c,room,match);assert response.status_code==200,response.text
    value=response.json();state=value['state']
    assert state['spectator'] and state['you'] is None and state['seat']==0 and value['code'] is None
    assert state['legal_moves']==[] and state['pending']=={'actor':0}
    assert all('hand' not in p and 'deck' not in p and 'selection' not in p for p in state['players'])
    assert all(p['hand_count']==1 for p in state['players'])
    for secret in ('private-hand-a','private-hand-b','private-deck-a','private-title','private-token','private-label'):
        assert secret not in response.text
    with factory() as session: assert session.scalar(select(func.count()).select_from(Seat))==2
    assert req(c,'c',f'/v3/rooms/{room}').status_code==403
    action=dict(action='concede',payload={},match_id=match,version=state['version'],request_id=str(uuid4()))
    assert req(c,'c',f'/v3/rooms/{room}/actions',action).status_code==403


def test_spectator_authorization_rechecked_and_bound_to_one_match(game):
    c,_,_,factory=game;room,match=setup_match(game)
    assert watch(c,room,match,target='b').status_code==403
    assert req(c,'c',f'/v3/rooms/{room}?watch=a').status_code==422
    assert watch(c,room,str(uuid4())).json()['state']['phase']=='closed'
    with factory.begin() as session:
        stored=session.get(Room,UUID(room));state=deepcopy(stored.state)
        state['phase']='mulligan';state['pending']=None;stored.state=state;stored.phase='mulligan'
    assert watch(c,room,match).json()['state']['spectator']
    with factory.begin() as session:
        friend=session.scalar(select(Friend));friend.status='declined'
    assert watch(c,room,match).status_code==403
    assert req(c,'c',f'/v3/rooms/{room}/events?watch=a&watch_match={match}').status_code==403


def test_busy_viewer_rejected_and_closed_room_exits_without_mutation(game):
    c,_,decks,factory=game;room,match=setup_match(game)
    with factory.begin() as session:
        stored=session.get(Room,UUID(room));state=deepcopy(stored.state)
        state['phase']='closed';stored.state=state;stored.phase='closed'
    assert watch(c,room,match).json()['state']['phase']=='closed'
    req(c,'c','/v3/rooms',dict(deck_id=decks['c'],request_id=str(uuid4())))
    assert watch(c,room,match).status_code==409


def test_guest_friend_view_and_finished_results_are_public(game):
    c,_,_,factory=game;room,match=setup_match(game)
    req(c,'c','/social/friends',dict(uid='b',operation='request'))
    req(c,'b','/social/friends',dict(uid='c',operation='accept'))
    value=watch(c,room,match,target='b').json()
    assert value['state']['seat']==1 and all('hand' not in p for p in value['state']['players'])
    with factory.begin() as session:
        stored=session.get(Room,UUID(room));state=deepcopy(stored.state)
        state.update(phase='finished',pending=None,winner=1,deadline_ms=None)
        stored.state=state;stored.phase='finished'
    value=watch(c,room,match,target='b').json()
    assert value['state']['winner']==1 and value['state']['legal_moves']==[]
    assert all('hand' not in p for p in value['state']['players'])
    with factory.begin() as session:
        session.get(Room,UUID(room)).match_id=uuid4()
    assert watch(c,room,match,target='b').json()['state']['phase']=='closed'
