"""Raven target scope and once-only kill follow-up."""
from random import Random
from dzmm_bot.core import mistrealm_v3_effects as fx, mistrealm_v3_state as game
from tests.core.test_mistrealm_v3 import empty,add,play,finish


def choose_card(s,c):
    token=next(o['token'] for o in s['pending']['options'] if o.get('card',{}).get('id')==c['id'])
    return game.apply_action(s,s['pending']['actor'],'choose',{'option':token},0,Random(0))


def test_decree_targets_both_sides_normals_and_returns_to_original_owner():
    for target_side,owner in ((0,0),(1,1),(1,0)):
        s=empty();own=add(s,'c081',zone='rows');foe=add(s,'c081',seat=1,zone='rows')
        target=own if target_side==0 else foe;target['owner']=owner;target['boost']=4
        add(s,'c095',zone='rows',row=2);add(s,'c095',seat=1,zone='rows',row=2)
        decree=add(s,'c033');s=play(s,decree)
        assert {o['card']['id'] for o in s['pending']['options']}=={own['id'],foe['id']}
        s=choose_card(s,target);assert not s['pending']
        assert not fx.location(s,target['id'])
        assert any(c['id']==target['id'] for c in s['players'][owner]['hand'])
        assert not fx.entity(s,target['id']).get('boost')


def test_hunter_kill_offers_one_followup_with_taunt_then_stops_after_second_kill():
    s=empty();first=add(s,'c102',seat=1,zone='rows',damage=1);second=add(s,'c102',seat=1,zone='rows',damage=1)
    third=add(s,'c101',seat=1,zone='rows');hunter=add(s,'c027')
    s=play(s,hunter,1);s=choose_card(s,third)
    assert not fx.location(s,first['id'])
    assert {o['card']['id'] for o in s['pending']['options'] if 'card' in o}=={second['id'],third['id']}
    s=finish(s)
    assert not s['pending'] and not fx.location(s,second['id']) and fx.location(s,third['id'])
    assert s['players'][0]['melee_hits']==2 and s['turn']==1


def test_hunter_survivor_or_shield_does_not_trigger_and_followup_is_optional():
    for cid,shield in (('c081',0),('c101',2)):
        s=empty();target=add(s,cid,seat=1,zone='rows',shield=shield)
        s=finish(play(s,add(s,'c027'),1))
        assert fx.location(s,target['id']) and not s['pending']
    s=empty();first=add(s,'c101',seat=1,zone='rows');second=add(s,'c081',seat=1,zone='rows')
    s=play(s,add(s,'c027'),1);s=choose_card(s,first)
    skip=next(o['token'] for o in s['pending']['options'] if not o['ops'])
    s=game.apply_action(s,0,'choose',{'option':skip},0,Random(0))
    assert not fx.entity(s,second['id']).get('damage') and not s['pending']


def test_hunter_kill_death_triggers_finish_before_followup_and_no_foes_skips_choice():
    s=empty();victim=add(s,'c071',seat=1,zone='rows',damage=1)
    ally=add(s,'c081',seat=1,zone='rows');s=play(s,add(s,'c027'),1);s=choose_card(s,victim)
    assert s['pending']['actor']==1 and s['pending']['title'].startswith('阵亡')
    s=choose_card(s,ally)
    assert s['pending']['actor']==0 and '追击' in s['pending']['title']
    s=finish(s);assert fx.entity(s,ally['id'])['boost']==3 and fx.entity(s,ally['id'])['damage']==2
    s=empty();add(s,'c101',seat=1,zone='rows');s=finish(play(s,add(s,'c027'),1))
    assert not s['pending'] and not fx.units(s,1)
