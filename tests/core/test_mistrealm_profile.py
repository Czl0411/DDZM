"""Personal settings must be enforced by APIs, history belongs to its participant."""
from copy import deepcopy
from uuid import UUID,uuid4
from sqlalchemy import select,func
from tests.core.test_mistrealm_social import game,req,challenge,reply
from tests.core.test_mistrealm_spectate import setup_match,watch
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import MistrealmHistoryRecord as History,MistrealmRoomRecord as Room


def test_profile_defaults_persistence_and_private_settings(game):
    c,_,_,_=game
    info=req(c,'a','/v3/profile').json()
    assert info['self'] and info['uid']=='a' and info['rank']['rating']==1000
    assert info['settings']==dict(challenges='all',friend_requests=True,spectate=True,animations=True,sound=False)
    values=dict(challenges='friends',friend_requests=False,spectate=False,animations=False,sound=True)
    assert req(c,'a','/v3/profile/settings',values).json()['settings']==values
    assert req(c,'a','/v3/profile').json()['settings']==values
    other=req(c,'b','/v3/profile?uid=a').json()
    assert not other['self'] and 'settings' not in other
    assert other['interaction']['challenge_reason']=='仅接受好友挑战'
    assert req(c,'a','/v3/profile/settings',dict(uid='b')).status_code==422
    assert req(c,'a','/v3/profile/settings',dict(sound='false')).status_code==422
    assert req(c,'a','/v3/profile/settings',dict(challenges='strangers')).status_code==422
    assert req(c,'a','/v3/profile?uid=missing').status_code==404
    assert c.get('/api/mistrealm/v3/profile').status_code==401


def test_closed_challenges_friend_requests_and_pending_invites_cannot_bypass(game):
    c,_,_,_=game
    invitation=challenge(game).json()
    req(c,'b','/v3/profile/settings',dict(challenges='off',friend_requests=False))
    assert reply(game,invitation).status_code==403
    assert challenge(game).status_code==403
    assert req(c,'a','/social/friends',dict(uid='b',operation='request')).status_code==403
    p=req(c,'a','/social/players?search=b').json()['items'][0]
    assert p['challenge_reason']=='暂不接受挑战' and p['friend_request_reason']
    req(c,'b','/v3/profile/settings',dict(challenges='friends',friend_requests=True))
    assert challenge(game).status_code==403
    req(c,'a','/social/friends',dict(uid='b',operation='request'))
    req(c,'b','/social/friends',dict(uid='a',operation='accept'))
    assert reply(game,invitation).status_code==200


def test_spectator_revoked_after_settings_change(game):
    c,_,_,_=game;room,match=setup_match(game)
    assert watch(c,room,match).status_code==200
    req(c,'a','/v3/profile/settings',dict(spectate=False))
    assert watch(c,room,match).status_code==403
    assert req(c,'c','/v3/profile?uid=a').json()['interaction']['spectate_room_id'] is None
    assert req(c,'c',f'/v3/rooms/{room}/events?watch=a&watch_match={match}').status_code==403


def test_completed_match_saved_once_after_leaving_and_private_from_third_player(game):
    c,clock,_,factory=game;room,match=setup_match(game)
    with factory.begin() as session:
        r=session.get(Room,UUID(room));s=deepcopy(r.state);s['pending']=None;r.state=s
    value=req(c,'a',f'/v3/rooms/{room}').json()
    response=req(c,'a',f'/v3/rooms/{room}/actions',dict(action='concede',payload={},match_id=match,version=value['state']['version'],request_id=str(uuid4())))
    assert response.status_code==200,response.text
    history=req(c,'a','/v3/profile/history').json()
    assert history['total']==1 and history['items'][0]['winner']==1
    report=req(c,'a',f'/v3/profile/history/{match}').json()
    assert report['actions'][-1]['kind']=='concede'
    assert all(secret not in str(report) for secret in ('private-hand','private-deck','private-token'))
    assert req(c,'b',f'/v3/profile/history/{match}').json()['seat']==1
    assert req(c,'c',f'/v3/profile/history/{match}').status_code==404
    ended=response.json()
    req(c,'a',f'/v3/rooms/{room}/actions',dict(action='leave',payload={},match_id=match,version=ended['state']['version'],request_id=str(uuid4())))
    assert req(c,'a','/v3/profile/history').json()['total']==1
    assert req(c,'a','/v3/profile/history?page=1').json()['items']==[]
    assert req(c,'a','/v3/profile/history?page=-1').status_code==422
    with factory() as s:assert s.scalar(select(func.count()).select_from(History))==2


def test_retained_finished_history_backfill_and_new_room_state_cannot_replace_it(game):
    c,clock,_,factory=game;room,match=setup_match(game)
    with factory.begin() as session:
        r=session.get(Room,UUID(room));s=deepcopy(r.state);s.update(phase='finished',pending=None,winner=0)
        s['history']=[dict(round=1,scores=[9,3],winner=0),dict(round=2,scores=[10,8],winner=0)]
        r.state=s;r.phase='finished'
    report=req(c,'a','/v3/profile/history').json()['items'][0]
    assert len(report['rounds'])==2
    with factory.begin() as session:
        r=session.get(Room,UUID(room));r.match_id=uuid4();r.phase='waiting';r.state={}
    assert req(c,'a',f'/v3/profile/history/{match}').json()['rounds']==report['rounds']


def test_legacy_finished_rooms_without_v3_clock_do_not_break_history(game):
    c,_,_,factory=game;room,_=setup_match(game)
    for version in (1,2):
        with factory.begin() as session:
            r=session.get(Room,UUID(room));s=deepcopy(r.state)
            s.update(rules_version=version,phase='finished')
            s.pop('server_time_ms',None)
            r.state=s;r.phase='finished'
        response=req(c,'a','/v3/profile/history')
        assert response.status_code==200,response.text
        assert response.json()['total']==0


def test_ranked_history_contains_final_score_change(ranked):
    from tests.core.test_mistrealm_ranked import paired,act
    repo,_,_,clock,_=ranked
    room=paired(ranked);end=act(ranked,room,'a','concede')
    history=repo.mistrealm_history('a',0,clock[0])['items'][0]
    assert history['mode']=='ranked'
    assert history['ranked']['result']==end['state']['ranked']['result']
    assert history['ranked']['result']['deltas']==[-16,16]


def test_profile_migration_preserves_existing_players(tmp_path):
    import importlib.util
    from pathlib import Path
    from sqlalchemy import create_engine,text,inspect
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path=Path(__file__).resolve().parents[2]/'migrations/versions/20261019_122_mistrealm_profile.py'
    spec=importlib.util.spec_from_file_location('profile_migration',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    engine=create_engine(f"sqlite:///{tmp_path/'migration.db'}")
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE mistrealm_players (id CHAR(32) PRIMARY KEY, name TEXT)'))
        connection.execute(text("INSERT INTO mistrealm_players VALUES ('existing','旅人')"))
        with Operations.context(MigrationContext.configure(connection)):
            m.upgrade()
            assert connection.execute(text('SELECT name, preferences FROM mistrealm_players')).one()==('旅人','{}')
            assert 'mistrealm_history' in inspect(connection).get_table_names()
            m.downgrade()
            assert connection.execute(text('SELECT name FROM mistrealm_players')).scalar()=='旅人'


from tests.core.test_mistrealm_ranked import ranked
