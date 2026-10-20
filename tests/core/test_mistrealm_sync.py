from copy import deepcopy

from dzmm_bot.core.mistrealm_sync import history_cursor, history_delta, channel_delta


def room(version=3, match='match'):
    return dict(room_id='room', match_id=match, state=dict(rules_version=3, version=version,
        action_log=[dict(id=i, text=str(i)) for i in range(1, version+1)],
        action_frames=[dict(version=i, state={'round': 1}) for i in range(1, version+1)]))


def test_history_only_appends_and_never_mutates_full_snapshot():
    value=room();before=deepcopy(value)
    delta=history_delta(value, history_cursor(room(1)))
    assert [x['id'] for x in delta['state']['action_log']]==[2,3]
    assert [x['version'] for x in delta['state']['action_frames']]==[2,3]
    assert delta['history_delta']==dict(log=1,frame=1)
    assert value==before
    assert history_delta(value, history_cursor(value))['state']['action_frames']==[]


def test_reconnect_legacy_rematch_and_invalid_cursor_restore_full_history():
    value=room()
    for cursor in ({},history_cursor(room(1,'old')),history_cursor(room(10)),{'sync_match':'match','sync_log':'bad'}):
        assert history_delta(value,cursor)==value
    cursor=history_cursor(room(0))
    assert history_delta(value,cursor)['state']['action_log']==value['state']['action_log']


def test_missing_animation_window_still_recovers_every_log():
    value=room(100);value['state']['action_frames']=value['state']['action_frames'][-80:]
    delta=history_delta(value,history_cursor(room(1)))
    assert len(delta['state']['action_log'])==99
    assert len(delta['state']['action_frames'])==80


def test_channel_handles_deletions_presence_and_challenge_expiry_without_repeated_text():
    value={'items':[{'id':str(i),'text':'message','player':{'uid':'a','online':False}} for i in (1,3,4)]}
    value['items'][1]['challenge']={'status':'ended','code':None}
    delta=channel_delta(value,'3')
    assert delta['ids']==['1','3','4']
    assert [x['id'] for x in delta['items']]==['4']
    assert delta['players']=={'a':{'uid':'a','online':False}}
    assert delta['challenges']['3']['status']=='ended'
    assert channel_delta(value,'deleted')['items']==value['items']
    unchanged=channel_delta(value,'4',delta['revision'])
    assert unchanged=={'unchanged':True,'revision':delta['revision']}
    value['items'][0]['player']['online']=True
    assert not channel_delta(value,'4',delta['revision']).get('unchanged')
