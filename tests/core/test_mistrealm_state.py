from copy import deepcopy
from random import Random

import pytest

from dzmm_bot.core.mistrealm_cards import CARDS, deck
from dzmm_bot.core.mistrealm_state import new_state, apply_action, advance, project


def act(s, seat, action, payload=None, now=100):
    return apply_action(s, seat, action, payload or {}, now, Random(42))


def playing():
    s = new_state('a', 0)
    s = act(s, 1, 'join', {'uid': 'b'})
    for i in range(2):
        s = act(s, i, 'ready')
    s = act(s, 0, 'start')
    for i in range(2):
        s = act(s, i, 'mulligan', {'cards': []})
    for i in range(2):
        s = act(s, i, 'reserve', {'card': s['players'][i]['hand'][0]['id']})
    return s


def unit(key, id='target', power=None, armor=0):
    return {'id': id, 'key': key, 'power': CARDS[key]['power'] if power is None else power, 'armor': armor}


def play_card(key, enemy=None, friends=None, targets=None, row=None):
    s = playing()
    s['turn'] = 0
    s['first_bonus'] = False
    s['players'][0]['hand'] = [{'id': 'test', 'key': key}]
    s['players'][1]['rows'] = [enemy or [], []]
    s['players'][0]['rows'] = [friends or [], []]
    row = row if row is not None else (1 if CARDS[key]['row'] == 'back' else 0)
    return s, act(s, 0, 'play', {'card': 'test', 'row': row, 'targets': targets or []})


def test_decks_and_unique_instances():
    assert len(CARDS) == 16
    for faction in ['raven', 'crown']:
        d = deck(faction, 0)
        assert len(d) == 20 == len({c['id'] for c in d})
        assert sum(CARDS[c['key']]['type'] == 'tactic' for c in d) == 4


def test_opening_and_privacy():
    s = playing()
    assert s['phase'] == 'playing'
    assert all(len(p['hand']) == 8 and len(p['deck']) == 11 for p in s['players'])
    v = project(s, 0)
    assert isinstance(v['players'][0]['hand'], list)
    assert v['players'][1]['hand_count'] == 8
    assert 'hand' not in v['players'][1] and 'reserve' not in v['players'][1]
    assert all('deck' not in p for p in v['players'])


@pytest.mark.parametrize('key,row,power', [('neutral_mercenary',0,7),('neutral_guard',0,5),('raven_hunter',1,8),('raven_guide',1,6),('crown_infantry',0,8)])
def test_deployment_conditions(key,row,power):
    _,s=play_card(key,[unit('neutral_mercenary',power=5)],[unit('neutral_guard','friend')],row=row)
    card=s['players'][0]['rows'][row][-1]
    assert card['power']==power
    if key=='neutral_guard': assert card['armor']==3


@pytest.mark.parametrize('key,amount', [('neutral_crossbow',3),('raven_knight',2),('raven_assassin',4)])
def test_damage_and_armor(key,amount):
    _,s=play_card(key,[unit('neutral_mercenary',power=6,armor=1)],targets=['target'])
    assert s['players'][1]['rows'][0][0]['power']==6-(amount-1)
    assert s['players'][1]['rows'][0][0]['armor']==0


def test_pierce_removes_armor_and_kills():
    _,s=play_card('neutral_pierce',[unit('neutral_guard',armor=10)],targets=['target'])
    assert not s['players'][1]['rows'][0]
    assert s['players'][1]['discard'][-1]['key']=='neutral_guard'


@pytest.mark.parametrize('key,gain,armor', [('neutral_medic',3,0),('neutral_mobilize',3,0),('crown_banner',2,0),('crown_guard',2,2)])
def test_friendly_effects(key,gain,armor):
    _,s=play_card(key,friends=[unit('neutral_guard','friend')],targets=['friend'])
    assert s['players'][0]['rows'][0][0]['power']==5+gain
    assert s['players'][0]['rows'][0][0]['armor']==armor


def test_commander_requires_two_same_row_targets():
    friends=[unit('neutral_guard','a'),unit('neutral_guard','b')]
    _,s=play_card('crown_commander',friends=friends,targets=['a','b'])
    assert [c['power'] for c in s['players'][0]['rows'][0]]==[7,7,5]


def test_invalid_action_is_atomic():
    s=playing(); original=deepcopy(s)
    with pytest.raises(ValueError): act(s,1-s['turn'],'pass')
    assert s==original
    s['turn']=0; s['players'][0]['hand']=[{'key':'neutral_mobilize','id':'x'}]
    s['players'][0]['rows'][0]=[unit('neutral_guard')]
    for targets in [['target','target'],['missing'],[]]:
        with pytest.raises(ValueError): act(s,0,'play',{'card':'x','row':0,'targets':targets})


def test_full_row_wrong_row_and_bool_rejected():
    s=playing(); s['turn']=0; s['players'][0]['hand']=[{'id':'x','key':'neutral_guard'}]
    for row in [1,True,2]:
        with pytest.raises(ValueError): act(s,0,'play',{'card':'x','row':row,'targets':[]})
    s['players'][0]['rows'][0]=[unit('neutral_guard',str(i)) for i in range(6)]
    with pytest.raises(ValueError): act(s,0,'play',{'card':'x','row':0,'targets':[]})


def test_pass_round_draw_and_reserve_return():
    s=playing()
    reserved=[p['reserve']['id'] for p in s['players']]
    for round_no in [1,2,3]:
        s=act(s,s['turn'],'pass'); s=act(s,s['turn'],'pass')
        assert s['scores']==[round_no,round_no]
        if round_no<3:
            s=advance(s,s['deadline_ms'],Random(1))
            assert s['round']==round_no+1
    assert s['phase']=='finished' and s['winner'] is None
    assert all(reserved[i] in [c['id'] for c in p['hand']] for i,p in enumerate(s['players']))


def test_leader_consumes_turn_and_is_once_per_match():
    s=playing(); s['turn']=0; s['players'][1]['rows'][0]=[unit('neutral_mercenary')]
    s=act(s,0,'leader',{'targets':['target']})
    assert s['players'][0]['leader_used'] and s['turn']==1
    assert s['players'][1]['rows'][0][0]['power']==4
    s['turn']=0
    with pytest.raises(ValueError): act(s,0,'leader',{'targets':['target']})


def test_timeout_uses_original_deadline():
    s=playing(); deadline=s['deadline_ms']
    s=advance(s,deadline+1,Random(1))
    assert s['players'][1-s['turn']]['passed']
    assert s['deadline_ms']==deadline+45000


def test_bonus_once_and_early_victory():
    s=playing(); first=s['turn']; s['players'][first]['hand']=[{'id':'x','key':'neutral_mercenary'}]
    s=act(s,first,'play',{'card':'x','row':0,'targets':[]})
    assert s['players'][first]['rows'][0][0]['power']==9
    assert s['first_bonus'] is False
    for n in range(2):
        if n: s['players'][first]['rows'][0]=[unit('neutral_mercenary')]
        s=act(s,s['turn'],'pass');s=act(s,s['turn'],'pass')
        if not n: s=advance(s,s['deadline_ms'],Random(1))
    assert s['phase']=='finished' and s['winner']==first


def setup_started():
    s=new_state('a',0)
    s=act(s,1,'join',{'uid':'b'})
    for i in range(2):s=act(s,i,'ready')
    return act(s,0,'start')


def test_both_preparation_timeouts_cancel_match():
    s=setup_started()
    s=advance(s,s['deadline_ms'],Random(1))
    assert [p['timeouts'] for p in s['players']]==[1,1]
    s=advance(s,s['deadline_ms'],Random(1))
    assert s['phase']=='finished' and s['reason']=='cancelled' and s['winner'] is None


def test_active_preparation_resets_timeout_counter():
    s=setup_started()
    s=advance(s,s['deadline_ms'],Random(1))
    s=act(s,0,'reserve',{'card':s['players'][0]['hand'][0]['id']})
    assert s['players'][0]['timeouts']==0
    s=advance(s,s['deadline_ms'],Random(1))
    assert s['phase']=='finished' and s['winner']==0


def test_mulligan_never_redraws_removed_instances():
    s=setup_started()
    old=[c['id'] for c in s['players'][0]['hand'][:2]]
    s=act(s,0,'mulligan',{'cards':old})
    assert not set(old)&{c['id'] for c in s['players'][0]['hand']}
    assert set(old)<={c['id'] for c in s['players'][0]['deck']}


def test_friendly_targets_cannot_target_enemy_and_vice_versa():
    s=playing();s['turn']=0
    s['players'][0]['hand']=[{'id':'x','key':'neutral_crossbow'}]
    s['players'][0]['rows'][0]=[unit('neutral_guard','friend')]
    s['players'][1]['rows'][0]=[unit('neutral_guard','enemy')]
    with pytest.raises(ValueError):act(s,0,'play',{'card':'x','row':1,'targets':['friend']})
    s['players'][0]['hand'][0]['key']='neutral_medic'
    with pytest.raises(ValueError):act(s,0,'play',{'card':'x','row':1,'targets':['enemy']})


def test_mirror_decks_and_crown_leader():
    s=playing()
    assert s['players'][0]['faction']==s['players'][1]['faction']=='raven'
    ids=[c['id'] for p in s['players'] for area in ['hand','deck'] for c in p[area]]
    assert len(ids)==len(set(ids))
    s['turn']=0;s['players'][0]['faction']='crown'
    s['players'][0]['rows'][0]=[unit('neutral_guard','friend')]
    s=act(s,0,'leader',{'targets':['friend']})
    c=s['players'][0]['rows'][0][0]
    assert (c['power'],c['armor'])==(8,2)
