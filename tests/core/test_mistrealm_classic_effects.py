"""Real state transitions for card chains, choices and conservation."""
from copy import deepcopy
import json
import random
import pytest
from dzmm_bot.core import mistrealm_classic_state as game
from dzmm_bot.core.mistrealm_classic_cards import STARTER_DECKS


def card(cid, ident=None): return {'id': ident or cid, 'card':cid}

def act(s,seat,action,payload=None):return game.apply_action(s,seat,action,payload or {},1000,random.Random(7))

def playing():
    s=game.new_state('a',STARTER_DECKS[0],0)
    s=act(s,1,'join',{'uid':'b','deck':STARTER_DECKS[3]})
    s=act(act(s,0,'lock'),1,'lock')
    s=act(act(s,0,'mulligan',{'cards':[]}),1,'mulligan',{'cards':[]})
    s['turn']=0
    for p in s['players']:
        p.update(hand=[],deck=[],discard=[],rows=[[],[],[]])
    return s

def play(s,cid,row=0):
    s['players'][0]['hand'].append(card(cid))
    return act(s,0,'play',{'card':cid,'row':row})

def choose(s,cid):
    option=next(o for o in s['pending']['options'] if o['card']['id']==cid)
    return act(s,s['pending']['actor'],'choose',{'option':option['token']})

def physical_ids(s):
    out=[]
    for p in s['players']:
        for zone in [p['hand'],p['deck'],p['discard'],*p['rows'],*p['supports']]:out.extend(c['id'] for c in zone)
    out.extend(c['id'] for c in s['weather'])
    if s['pending'] and s['pending'].get('source'):out.append(s['pending']['source']['id'])
    return sorted(out)

@pytest.mark.parametrize('spy',['c006','c108'])
def test_spy_draws_two_but_never_fabricates_cards(spy):
    s=playing();s['players'][0]['deck']=[card('c003','draw')]
    s=play(s,spy)
    assert [c['card'] for c in s['players'][1]['rows'][0]]==[spy]
    assert s['players'][0]['hand']==[card('c003','draw')]
    assert s['turn']==1


def test_nested_medic_chain_restores_spy_once_and_keeps_choices_private():
    s=playing();s['players'][0]['discard']=[card('c105'),card('c006'),card('c110')]
    s['players'][0]['deck']=[card('c003','draw1'),card('c003','draw2')]
    s=play(s,'c112',1)
    assert s['turn']==0 and s['pending']['kind']=='medic'
    assert 'options' not in game.project(s,1)['pending']
    assert all(o['card']['card']!='c110' for o in s['pending']['options'])
    s=choose(json.loads(json.dumps(s)),'c105')
    assert s['turn']==0 and s['pending']['kind']=='medic'
    s=choose(s,'c006')
    assert s['pending'] is None and s['turn']==1
    assert len(s['players'][0]['hand'])==2
    assert [c['card'] for c in s['players'][1]['rows'][0]]==['c006']
    assert len(physical_ids(s))==len(set(physical_ids(s)))
    with pytest.raises(ValueError):act(s,0,'choose',{'option':'c006:0'})


def test_empty_medic_finishes_and_illegal_choice_is_atomic():
    s=play(playing(),'c105',1)
    assert s['pending'] is None and s['turn']==1
    s=playing();s['players'][0]['discard']=[card('c003')]
    s=play(s,'c105',1);before=deepcopy(s)
    with pytest.raises(ValueError):act(s,0,'choose',{'option':'nonexistent'})
    assert s==before
    s=game.advance(s,s['deadline_ms'],random.Random(7))
    assert s['pending'] is None and s['turn']==1
    assert s['players'][0]['rows'][0]==[card('c003')]
    assert not s['players'][0]['passed']


def test_revived_muster_pulls_from_hand_and_deck_once():
    s=playing();s['players'][0]['discard']=[card('c061')]
    s['players'][0]['hand']=[card('c062')];s['players'][0]['deck']=[card('c063')]
    s=choose(play(s,'c105',1),'c061')
    assert {c['card'] for c in s['players'][0]['rows'][0]}=={'c061','c062','c063'}
    assert s['players'][0]['hand']==s['players'][0]['deck']==[]
    assert len(physical_ids(s))==4


def test_decoy_keeps_physical_placeholder_and_can_reuse_nonhero_spy():
    s=playing();s['players'][0]['rows'][0]=[card('c006'),card('c108')]
    s=play(s,'c117',-1)
    assert [o['card']['card'] for o in s['pending']['options']]==['c006']
    s=choose(s,'c006')
    assert s['players'][0]['hand']==[card('c006')]
    assert {c['card'] for c in s['players'][0]['rows'][0]}=={'c117','c108'}
    assert game.project(s,0)['players'][0]['score']==0


@pytest.mark.parametrize('seat',[0,1])
def test_concede_during_decoy_choice_preserves_the_pending_physical_card(seat):
    s=playing();s['players'][0]['rows'][0]=[card('c006')]
    s=play(s,'c117',-1);before=physical_ids(s)
    s=act(s,seat,'concede')
    assert s['phase']=='finished' and s['pending'] is None
    assert physical_ids(s)==before
    assert card('c117') in s['players'][0]['discard']


def test_global_scorch_removes_all_highest_nonhero_ties_on_both_sides():
    s=playing();s['players'][0]['rows'][0]=[card('c003'),card('c110')]
    s['players'][1]['rows'][1]=[card('c027')]
    s['players'][1]['rows'][0]=[card('c022')]
    s=play(s,'c119',-1)
    assert s['players'][0]['rows'][0]==[card('c110')]
    assert s['players'][1]['rows'][1]==[]
    assert s['players'][1]['rows'][0]==[card('c022')]

@pytest.mark.parametrize('enemy,want', [(['c003'],['c003']),(['c003','c003'],[]),(['c003','c110'],['c003','c110'])])
def test_row_scorch_threshold_ignores_heroes(enemy,want):
    s=playing();s['players'][1]['rows'][0]=[card(cid,f'e{i}') for i,cid in enumerate(enemy)]
    s=play(s,'c109')
    assert [c['card'] for c in s['players'][1]['rows'][0]]==want

@pytest.mark.parametrize('cid,row',[('c113',0),('c114',1),('c115',2)])
def test_weather_and_clear_weather(cid,row):
    s=playing();s['players'][0]['rows'][row]=[card('c003','unit')]
    s=play(s,cid,-1)
    assert game.project(s,0)['players'][0]['row_scores'][row]==1
    s['turn']=0;s=play(s,'c116',-1)
    assert not s['weather']
    assert game.project(s,0)['players'][0]['row_scores'][row]==6
    assert {c['card'] for c in s['players'][0]['discard']}=={cid,'c116'}


def test_horn_and_ritual_are_row_support_and_transform_both_forms():
    s=playing();s['players'][0]['rows'][0]=[card('c003')]
    s=play(s,'c118',0)
    assert game.project(s,0)['players'][0]['score']==12
    s['turn']=0;s['players'][0]['rows'][1]=[card('c089','young1'),card('c089','young2')]
    s=play(s,'c120',1)
    assert [c['form'] for c in s['players'][0]['rows'][1]]==['t002','t002']
    assert game.project(s,0)['players'][0]['row_scores'][1]==32
    s=playing();s['players'][0]['rows'][0]=[card('c088')]
    s=play(s,'c090',0)
    assert s['players'][0]['rows'][0][0]['form']=='t001'
    assert game.project(s,0)['players'][0]['score']==16

@pytest.mark.parametrize('leader,row',[('c020',2),('c060',1),('c079',0)])
def test_active_horn_leader_consumes_exactly_one_turn(leader,row):
    s=playing();s['players'][0]['leader']=leader
    s=act(s,0,'leader')
    assert s['players'][0]['leader_horns'][row] and s['turn']==1
    s['turn']=0
    with pytest.raises(ValueError):act(s,0,'leader')

@pytest.mark.parametrize('leader,grave_seat',[('c040',1),('c080',0)])
def test_recover_leaders_choose_eligible_grave_card(leader,grave_seat):
    s=playing();s['players'][0]['leader']=leader
    s['players'][grave_seat]['discard']=[card('c003'),card('c110'),card('c119')]
    s=act(s,0,'leader')
    assert [o['card']['card'] for o in s['pending']['options']]==['c003']
    s=choose(s,'c003')
    assert s['players'][0]['hand']==[card('c003')] and s['turn']==1


def test_clear_leader_and_grave_shuffle_include_heroes_and_specials():
    s=playing();s['weather']=[dict(card('c113'),row=0,owner=1)]
    s=act(s,0,'leader');assert not s['weather']
    s=playing();s['players'][0]['leader']='c099'
    s['players'][0]['discard']=[card('c110'),card('c119')]
    s['players'][1]['discard']=[card('c003')]
    s=act(s,0,'leader')
    assert len(s['players'][0]['deck'])==2 and len(s['players'][1]['deck'])==1
    assert not any(p['discard'] for p in s['players'])


def test_cancellation_precedes_passive_extra_hand():
    for opponent,count in [(0,11),(2,10)]:
        s=game.new_state('a',STARTER_DECKS[4],0)
        s=act(s,1,'join',{'uid':'b','deck':STARTER_DECKS[opponent]})
        s=act(act(s,0,'lock'),1,'lock')
        assert len(s['players'][0]['hand'])==count
        assert s['players'][0]['leader_disabled']==(opponent==2)


def test_beast_retains_one_nonhero_without_retriggering_spy():
    s=playing();s['round']=1;s['phase']='round_result';s['deadline_ms']=0;s['first']=0
    s['players'][0]['faction']='beast'
    s['players'][0]['rows'][0]=[card('c006'),card('c110')]
    s['players'][0]['deck']=[card('c003')]
    s=game.advance(s,1000,random.Random(7))
    assert s['players'][0]['rows'][0]==[card('c006')]
    assert s['players'][0]['hand']==[]
    assert s['players'][0]['discard']==[card('c110')]


def test_mirror_third_round_revives_and_resumes_opening_after_medic_choice():
    s=playing();s.update(round=2,phase='round_result',deadline_ms=0,first=1)
    s['players'][0]['faction']='mirror'
    s['players'][0]['discard']=[card('c105'),card('c003'),card('c006'),card('c110')]
    s['players'][0]['deck']=[card('c102','draw1'),card('c102','draw2')]
    s=game.advance(s,1000,random.Random(1))
    assert s['round']==3
    if s['pending']:
        s=game.advance(s,s['deadline_ms'],random.Random(1))
    assert s['pending'] is None and s['turn']==1
    assert card('c110') in s['players'][0]['discard']
    assert sum(len(r) for p in s['players'] for r in p['rows'])>=2
    assert len(physical_ids(s))==len(set(physical_ids(s)))


def test_transformed_card_reverts_when_discarded_between_rounds():
    s=playing();s.update(round=1,phase='round_result',deadline_ms=0,first=0)
    s['players'][0]['rows'][0]=[dict(card('c088'),form='t001')]
    s=game.advance(s,1000,random.Random(1))
    assert s['players'][0]['discard']==[card('c088')]


def test_half_weather_only_protects_own_units_and_cancel_disables_it():
    s=playing();s['players'][0]['leader']='c100'
    s['players'][0]['rows'][0]=[card('c021'),card('c110')]
    s['players'][1]['rows'][0]=[card('c003')]
    s=play(s,'c113',-1)
    assert game.project(s,0)['players'][0]['score']==19
    assert game.project(s,0)['players'][1]['score']==1
    s['players'][0]['leader_disabled']=True
    assert game.project(s,0)['players'][0]['score']==16


@pytest.mark.parametrize('first',[0,1])
@pytest.mark.parametrize('timeout',[False,True])
@pytest.mark.parametrize('nested',[False,True])
def test_opening_medic_completion_starts_full_first_turn(first,timeout,nested):
    class OpeningRandom(random.Random):
        def sample(self,population,k):return population[:k]
    rng=OpeningRandom(7)
    s=playing();s.update(round=2,phase='round_result',deadline_ms=100,first=first)
    s['players'][0]['faction']='mirror'
    s['players'][0]['discard']=[card('c105'),card('c003')]
    if nested:s['players'][0]['discard'].append(card('c105','nested-medic'))
    s['players'][0]['discard'].append(card('c007'))
    s=game.advance(s,100,rng)
    assert s['pending']['continuation']=='opening'
    completed_at=60100 if timeout else 60000
    if timeout:s=game.advance(s,completed_at,rng)
    else:
        while s['pending']:
            s=game.apply_action(s,0,'choose',{'option':s['pending']['options'][0]['token']},completed_at,rng)
            if s['pending']:assert s['deadline_ms']==60100
    assert s['pending'] is None and s['opening']==[]
    assert s['turn']==first
    assert s['deadline_ms']==completed_at+game.TURN_MS
    s=game.advance(s,completed_at+700,rng)
    assert not any(p['passed'] for p in s['players'])
    assert s['turn']==first
