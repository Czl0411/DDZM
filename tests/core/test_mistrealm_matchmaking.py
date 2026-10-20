from datetime import timedelta
from uuid import uuid4

from tests.core.test_mistrealm_api import game, headers, create, NOW


def match(client, uid):
    return client.post('/api/mistrealm/matchmaking',headers=headers(uid))

def heartbeat(client,uid,ticket):
    return client.post('/api/mistrealm/matchmaking/heartbeat',headers=headers(uid),json={'ticket':ticket})

def cancel(client,uid,ticket):
    return client.post('/api/mistrealm/matchmaking/cancel',headers=headers(uid),json={'ticket':ticket})


def test_pair_two_and_restore_first_player(game):
    c,repo,_=game
    a=match(c,'a')
    assert a.status_code==200
    assert a.json()['status']=='waiting'
    assert match(c,'a').json()['ticket']==a.json()['ticket']
    b=match(c,'b').json()
    assert b['status']=='matched'
    first=heartbeat(c,'a',a.json()['ticket']).json()
    assert first['room']['room_id']==b['room']['room_id']
    assert first['room']['state']['seat']!=b['room']['state']['seat']
    assert len(first['room']['state']['players'])==2
    assert repo.mistrealm_me('a',NOW)['matchmaking']['status']=='idle'


def test_private_room_is_not_a_match_candidate(game):
    c,_,_=game
    private=create(c,'a').json()
    b=match(c,'b').json()
    assert b['status']=='waiting'
    assert match(c,'a').json()['room']['room_id']==private['room_id']
    paired=match(c,'c').json()['room']
    assert paired['room_id']!=private['room_id']
    assert {p['uid'] for p in paired['state']['players']}=={'b','c'}


def test_cancel_is_idempotent_and_stale_heartbeat_cannot_rejoin(game):
    c,_,_=game
    a=match(c,'a').json()
    assert cancel(c,'a',a['ticket']).json()['status']=='idle'
    assert cancel(c,'a',a['ticket']).json()['status']=='idle'
    assert heartbeat(c,'a',a['ticket']).json()['status']=='idle'
    b=match(c,'b').json()
    assert b['status']=='waiting'


def test_expired_players_are_not_matched_and_do_not_renew(game):
    c,repo,_=game
    a=match(c,'a').json()
    later=NOW+timedelta(seconds=21)
    assert repo.mistrealm_matchmaking('b','start',None,later)['status']=='waiting'
    assert repo.mistrealm_matchmaking('a','heartbeat',a['ticket'],later)['status']=='idle'
    assert repo.mistrealm_me('a',later)['matchmaking']['status']=='idle'


def test_stale_cancel_does_not_remove_new_queue(game):
    c,_,_=game
    old=match(c,'a').json()
    cancel(c,'a',old['ticket'])
    new=match(c,'a').json()
    assert new['ticket']!=old['ticket']
    cancel(c,'a',old['ticket'])
    assert heartbeat(c,'a',new['ticket']).json()['status']=='waiting'


def test_cancel_after_pairing_returns_room(game):
    c,_,_=game
    a=match(c,'a').json()
    paired=match(c,'b').json()
    assert cancel(c,'a',a['ticket']).json()['room']['room_id']==paired['room']['room_id']


def test_manual_creation_clears_queue(game):
    c,_,_=game
    a=match(c,'a').json()
    room=create(c,'a').json()
    assert heartbeat(c,'a',a['ticket']).json()['room']['room_id']==room['room_id']
    assert match(c,'b').json()['status']=='waiting'


def test_queue_restores_on_profile_and_heartbeat_keeps_order(game):
    c,repo,_=game
    a=match(c,'a').json()
    me=c.get('/api/mistrealm/players/me',headers=headers('a')).json()
    assert me['matchmaking']['ticket']==a['ticket']
    pulse=repo.mistrealm_matchmaking('a','heartbeat',a['ticket'],NOW+timedelta(seconds=10))
    assert pulse['queued_at_ms']==a['queued_at_ms']
    assert pulse['expires_at_ms']>a['expires_at_ms']


def test_queue_elapsed_survives_heartbeat_and_reload(game):
    c,repo,_=game
    queued=match(c,'a').json()
    assert queued['elapsed_ms']==0
    later=NOW+timedelta(seconds=8)
    renewed=repo.mistrealm_matchmaking('a','heartbeat',queued['ticket'],later)
    assert renewed['elapsed_ms']==8000
    assert repo.mistrealm_me('a',later)['matchmaking']['elapsed_ms']==8000
