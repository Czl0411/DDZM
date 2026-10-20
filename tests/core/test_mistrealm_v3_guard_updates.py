"""Guard interception, swapped movement deployments and winter draw counts."""
from copy import deepcopy
from random import Random
import pytest
from dzmm_bot.core import mistrealm_v3_effects as fx, mistrealm_v3_state as game
from dzmm_bot.core.mistrealm_v3_cards import CARDS
from dzmm_bot.core.mistrealm_v3_hints import choice_preview
from tests.core.test_mistrealm_v3 import empty,add,play,finish
from tests.core.test_mistrealm_v3_beast import strength


@pytest.mark.parametrize('cid,row',[('c032',2),('c111',-1),('c039',-1)])
def test_guard_intercepts_units_spells_and_leaders_across_rows(cid,row):
    s=empty();guard=add(s,'c102',seat=1,zone='rows',row=0)
    victim=add(s,'c109',seat=1,zone='rows',row=2)
    if cid=='c039':
        s['players'][0]['leader']=cid;s=game.apply_action(s,0,'leader',{},0)
    else:s=play(s,add(s,cid),row)
    pick=next(i for i,o in enumerate(s['pending']['options']) if o.get('card',{}).get('id')==victim['id'])
    s=finish(s,pick)
    assert fx.entity(s,guard['id']) in s['players'][1]['discard']
    assert not fx.entity(s,victim['id']).get('damage')


def test_guard_intercepts_aoe_once_no_spillover_then_next_hit_uses_next_guard():
    s=empty();first=add(s,'c102',seat=1,zone='rows',row=2)
    second=add(s,'c102',seat=1,zone='rows',row=0)
    victims=[add(s,'c081',seat=1,zone='rows',row=1) for _ in range(2)]
    targets=[c['id'] for c in fx.units(s,1)]
    fx.damage(s,0,targets,2);fx.settle(s)
    assert strength(s,first)==1 and strength(s,second)==3
    assert all(not c.get('damage') for c in victims)
    fx.damage(s,0,targets,5);fx.settle(s)
    assert not fx.location(s,first['id']) and strength(s,second)==3
    assert all(not c.get('damage') for c in victims)
    fx.damage(s,0,[c['id'] for c in victims],2);fx.settle(s)
    assert strength(s,second)==1 and all(not c.get('damage') for c in victims)


def test_guard_does_not_intercept_friendly_damage_sacrifice_or_while_sealed():
    s=empty();guard=add(s,'c102',zone='rows');victim=add(s,'c081',zone='rows',row=1)
    fx.damage(s,0,[victim['id']],1)
    assert victim['damage']==1 and strength(s,guard)==3
    guard['sealed']=True;fx.damage(s,1,[victim['id']],1)
    assert victim['damage']==2 and strength(s,guard)==3
    guard.pop('sealed');fx.execute(s,1,fx.op('sacrifice',targets=[victim['id']]))
    fx.settle(s);assert not fx.location(s,victim['id']) and strength(s,guard)==3


def test_global_damage_protects_only_enemy_side_and_preview_shows_actual_guard():
    s=empty();own=add(s,'c102',zone='rows');ally=add(s,'c081',zone='rows',row=1)
    enemy=add(s,'c102',seat=1,zone='rows');foe=add(s,'c081',seat=1,zone='rows',row=1)
    choice=dict(ops=[fx.op('damage',targets=[foe['id']],amount=2)])
    before=deepcopy(s);lines,_=choice_preview(s,0,choice)
    assert any('铁盾卫士' in line and '3 → 1' in line for line in lines) and s==before
    s=finish(play(s,add(s,'c119')))
    assert strength(s,own)==1 and strength(s,ally)==2
    assert strength(s,enemy)==1 and strength(s,foe)==4


def test_guard_mark_and_shield_apply_to_actual_recipient():
    s=empty();guard=add(s,'c102',seat=1,zone='rows',shield=1)
    foe=add(s,'c081',seat=1,zone='rows')
    mark=add(s,'c034',zone='spells',targets=[guard['id'],foe['id']])
    fx.damage(s,0,[guard['id'],foe['id']],1)
    assert guard['damage']==2 and guard['shield']==0 and not foe.get('damage')
    assert mark['targets']==[foe['id']]


@pytest.mark.parametrize('count',[0,1,2,4])
def test_winter_noble_draws_count_of_played_persistents_on_deploy_only(count):
    s=empty();s['players'][0].update(spell_count=count+2,instant_count=2)
    for _ in range(6):add(s,'c081',zone='deck')
    noble=add(s,'c056');s=finish(play(s,noble,1))
    assert len(s['players'][0]['hand'])==count
    s['turn']=0;s=finish(play(s,add(s,'c094')))
    assert len(s['players'][0]['hand'])==count
    game._begin_round(s,0,Random(0));assert s['players'][0]['spell_count']==0


def test_swapped_movers_keep_stats_and_rows_but_change_legal_sides():
    s=empty();friend=add(s,'c081',zone='rows');foe=add(s,'c081',seat=1,zone='rows')
    wind=add(s,'c052',zone='rows',row=1);mediator=add(s,'c107',zone='rows',row=1)
    assert CARDS['c052']['power']==4 and CARDS['c052']['rows']==[1]
    assert CARDS['c107']['power']==4 and CARDS['c107']['rows']==[0,1]
    assert {o['card']['id'] for o in fx.menu(s,0,wind)}=={friend['id'],foe['id'],wind['id'],mediator['id']}
    assert {o['card']['id'] for o in fx.menu(s,0,mediator)}=={foe['id']}
