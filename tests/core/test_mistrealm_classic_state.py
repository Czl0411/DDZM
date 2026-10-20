from copy import deepcopy
import importlib
import importlib.util
import random
import json
import pytest
from dzmm_bot.core.mistrealm_classic_cards import STARTER_DECKS


def engine():
    name='dzmm_bot.core.mistrealm_classic_state'
    assert importlib.util.find_spec(name), 'Classic lifecycle must exist'
    return importlib.import_module(name)


def act(s,seat,action,payload=None):
    return engine().apply_action(s,seat,action,payload or {},1000,random.Random(7))


def paired(a=0,b=2):
    s=engine().new_state('alice',STARTER_DECKS[a],0)
    return act(s,1,'join',{'uid':'bob','deck':STARTER_DECKS[b]})


def playing(a=0,b=2):
    s=act(paired(a,b),0,'lock');s=act(s,1,'lock')
    if s['phase']=='choose_first': s=act(s,s['chooser'],'first',{'seat':0})
    s=act(s,0,'mulligan',{'cards':[]});s=act(s,1,'mulligan',{'cards':[]})
    return s


def test_lock_snapshot_hidden_until_both_lock_then_ten_cards():
    s=paired(); old=deepcopy(s)
    own=engine().project(s,0)
    assert own['players'][1]=={'uid':'bob','locked':False}
    assert own['players'][0]['selection']['leader']=='c019'
    s=act(s,0,'lock')
    assert engine().project(s,1)['players'][0]=={'uid':'alice','locked':True}
    s=act(s,1,'lock')
    assert s['rules_version']==2 and s['phase']=='mulligan'
    assert [len(p['hand']) for p in s['players']]==[10,10]
    assert all(len(p['rows'])==3 for p in s['players'])
    view=engine().project(s,0)
    assert 'deck' not in view['players'][1] and 'selection' not in view['players'][1]
    assert 'hand' not in view['players'][1] and view['players'][1]['hand_count']==10
    assert old['players'][0]['locked'] is False
    with pytest.raises(ValueError): act(s,0,'unlock')


def test_mulligan_two_replacements_never_instantly_return_and_no_extra_draws():
    s=act(act(paired(),0,'lock'),1,'lock')
    ids=[c['id'] for c in s['players'][0]['hand'][:2]]
    with pytest.raises(ValueError): act(s,0,'mulligan',{'cards':ids+[s['players'][0]['hand'][2]['id']]})
    s=act(s,0,'mulligan',{'cards':ids})
    assert not set(ids)&{c['id'] for c in s['players'][0]['hand']}
    assert len(s['players'][0]['hand'])==10
    with pytest.raises(ValueError): act(s,0,'mulligan',{'cards':[]})
    s=act(s,1,'mulligan',{'cards':[]})
    s['players'][0]['faction']=s['players'][1]['faction']='frost'
    s=act(s,s['turn'],'pass');s=act(s,s['turn'],'pass')
    assert s['lives']==[1,1]
    s=engine().advance(s,s['deadline_ms'],random.Random(3))
    assert s['round']==2
    assert [len(p['hand']) for p in s['players']]==[10,10]

@pytest.mark.parametrize('factions,lives',[(('crown','frost'),[1,1]),(('raven','crown'),[2,1]),(('crown','raven'),[1,2]),(('raven','raven'),[1,1])])
def test_ties_and_faction_advantage(factions,lives):
    s=playing()
    for p,f in zip(s['players'],factions):p['faction']=f
    s=act(s,s['turn'],'pass');s=act(s,s['turn'],'pass')
    assert s['lives']==lives


def test_pass_locks_player_and_other_player_can_keep_playing_without_row_cap():
    s=playing(); first=s['turn']; second=1-first
    s=act(s,first,'pass')
    s['players'][second]['hand']=[{'id':f'u{i}','card':'c003'} for i in range(12)]
    for i in range(12):
        s=act(s,second,'play',{'card':f'u{i}','row':0})
    assert len(s['players'][second]['rows'][0])==12
    assert engine().project(s,second)['players'][second]['score']==72
    with pytest.raises(ValueError):act(s,first,'play',{'card':'bad','row':0})
    s=act(s,second,'pass')
    assert s['lives'][first]==1

@pytest.mark.parametrize('seat,action,payload',[(4,'pass',{}),(True,'pass',{}),(0,'play',{'card':'missing','row':0}),(0,'play',{'card':'missing','row':True}),(0,'typo',{})])
def test_failed_actions_never_mutate_input(seat,action,payload):
    s=playing();before=deepcopy(s)
    with pytest.raises(ValueError):act(s,seat,action,payload)
    assert s==before


def test_frost_chooses_first_and_state_is_json_serializable():
    s=act(act(paired(5,0),0,'lock'),1,'lock')
    assert s['phase']=='choose_first' and s['chooser']==0
    with pytest.raises(ValueError):act(s,1,'first',{'seat':1})
    s=act(s,0,'first',{'seat':1})
    s=act(s,0,'mulligan',{'cards':[]});s=act(s,1,'mulligan',{'cards':[]})
    assert s['turn']==1 and s['round']==1
    assert json.loads(json.dumps(s))==s


def test_two_frost_factions_cancel_first_choice_and_use_coin_toss():
    s=act(act(paired(4,5),0,'lock'),1,'lock')
    assert s['phase']=='mulligan' and s['chooser'] is None
    assert s['first'] in (0,1)


def test_finished_rematch_requires_both_votes_and_resets_leader_lives_and_selections():
    s=act(playing(),0,'concede')
    s=act(s,0,'rematch')
    assert s['phase']=='finished'
    s=act(s,1,'rematch')
    assert s['phase']=='waiting' and s['lives']==[2,2]
    assert all(not p['locked'] and not p['leader_used'] and not p['hand'] for p in s['players'])
    assert engine().project(s,0)['players'][1]=={'uid':'bob','locked':False}
    s=act(s,1,'leave')
    assert s['phase']=='closed'


def test_server_supplies_only_current_actor_legal_moves():
    s=playing();s['turn']=0
    s['players'][0]['hand']=[{'id':'flex','card':'c107'},{'id':'horn','card':'c118'}]
    moves=engine().project(s,0)['legal_moves']
    assert {'action':'play','payload':{'card':'flex','row':0}} in moves
    assert {'action':'play','payload':{'card':'flex','row':1}} in moves
    assert {'action':'play','payload':{'card':'flex','row':2}} not in moves
    assert not any(m['action'] in ('play','leader','pass') for m in engine().project(s,1)['legal_moves'])


@pytest.mark.parametrize('expired',[False,True])
def test_closed_undealt_room_projects_without_revealing_opponent_selection(expired):
    s=paired(0,2)
    s=engine().advance(s,s['deadline_ms']) if expired else act(s,0,'leave')
    view=engine().project(s,0)
    assert view['phase']=='closed' and view['legal_moves']==[]
    assert view['players'][1]=={'uid':'bob','locked':False}
