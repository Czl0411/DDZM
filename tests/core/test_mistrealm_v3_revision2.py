"""Balance revision 2: target legality, conditional power and card conservation."""
import json
from random import Random

from dzmm_bot.core import mistrealm_v3_state as game, mistrealm_v3_effects as fx
from dzmm_bot.core.mistrealm_v3_scoring import row_power_details
from tests.core.test_mistrealm_v3 import empty,add,play,finish


def strength(s,c):
    side,row,_=fx.location(s,c['id'])
    return row_power_details(s,side,row)[s['players'][side]['rows'][row].index(fx.entity(s,c['id']))]['power']


def test_infantry_and_guard_are_live_conditions_not_deployment():
    s=empty();inf=add(s,'c001',zone='rows');guard=add(s,'c003',zone='rows',row=1)
    assert strength(s,inf)==3 and strength(s,guard)==5
    friend=add(s,'c101',zone='rows')
    assert strength(s,inf)==5
    fx.execute(s,0,fx.op('move',targets=[friend['id']],row=1))
    assert strength(s,inf)==3 and strength(s,guard)==3
    fx.remove_unit(s,friend['id']);assert strength(s,guard)==5
    assert not guard.get('boost')


def test_damage_options_keep_targets_but_redirect_to_guard():
    s=empty();tank=add(s,'c102',seat=1,zone='rows');other=add(s,'c109',seat=1,zone='rows')
    archer=add(s,'c028',zone='rows',row=1)
    choices=fx.menu(s,0,archer)
    assert any(o['ops'][0]['targets']==[other['id']] for o in choices)
    assert any(set(o['ops'][0]['targets'])=={tank['id'],other['id']} for o in choices)
    # Row restrictions apply to selection; the guard can intercept from another row.
    ranged=add(s,'c109',seat=1,zone='rows',row=1)
    assert [o['card']['id'] for o in fx.menu(s,0,dict(card='c007',id='archer'))]==[ranged['id']]
    assert len(fx.menu(s,0,dict(card='c111',id='spell')))==3
    tank['sealed']=True
    assert any(o['ops'][0]['targets']==[other['id']] for o in fx.menu(s,0,archer))


def test_mark_snapshots_all_enemies_and_each_damage_consumes_one_mark():
    s=empty();a=add(s,'c109',seat=1,zone='rows');b=add(s,'c109',seat=1,zone='rows',row=1)
    spell=add(s,'c034');s=finish(play(s,spell));mark=fx.entity(s,spell['id'])
    later=add(s,'c109',seat=1,zone='rows',row=2)
    assert set(mark['targets'])=={a['id'],b['id']}
    fx.damage(s,0,[a['id'],b['id'],later['id']],1)
    assert [fx.entity(s,c['id'])['damage'] for c in [a,b,later]]==[3,3,1]
    assert not mark['targets']
    fx.damage(s,0,[a['id']],1);assert fx.entity(s,a['id'])['damage']==4
    # Destroying a mark before damage removes its bonus.
    mark['targets']=[later['id']];fx.execute(s,1,fx.op('destroy_spell',targets=[mark['id']]))
    fx.damage(s,0,[later['id']],1);assert fx.entity(s,later['id'])['damage']==2


def test_executioner_counts_actual_normal_unit_hits_on_enemy_melee_without_cap():
    s=empty();attacker=add(s,'c027',zone='rows',row=1);foe=add(s,'c004',seat=1,zone='rows',boost=4)
    for _ in range(3):fx.damage(s,0,[foe['id']],1,attacker['id'])
    hero=add(s,'c036',zone='rows');assert strength(s,hero)==11
    fx.damage(s,0,[foe['id']],1) # A spell/leader hit has no unit source.
    assert strength(s,hero)==11
    distant=add(s,'c109',seat=1,zone='rows',row=1)
    fx.damage(s,0,[distant['id']],1,attacker['id']);assert strength(s,hero)==11
    fx.damage(s,0,[foe['id']],1,attacker['id']);assert strength(s,hero)==13
    hero['sealed']=True;assert strength(s,hero)==5


def test_traveler_uses_current_enemy_normal_power_and_excludes_heroes():
    s=empty();a=add(s,'c109',zone='rows');b=add(s,'c109',seat=1,zone='rows')
    assert strength(s,a)==strength(s,b)==5 # No self-starting circular bonus.
    add(s,'c015',seat=1,zone='rows',row=1,boost=4)
    assert strength(s,a)==5 # Heroes do not count.
    target=add(s,'c004',seat=1,zone='rows',row=2,boost=4)
    assert strength(s,a)==8 and strength(s,b)==5
    target['damage']=1;assert strength(s,a)==strength(s,b)==5 # Exactly 6 is excluded.


def test_wall_draws_per_entry_twice_and_never_reduces_damage():
    s=empty();spell=add(s,'c014',zone='spells');spell['row']=0
    for _ in range(4):add(s,'c109',zone='deck')
    fx.start_action(s,0)
    a=add(s,'c101');b=add(s,'c101')
    for c in [a,b]:s['players'][0]['hand'].remove(c);fx.put(s,0,c,0)
    s['work']=[fx.op('end_triggers',seat=0)];fx.drain(s)
    assert len(s['players'][0]['hand'])==2 and spell['entry_draws']==2
    fx.damage(s,1,[a['id']],1);assert a['damage']==1
    fx.start_action(s,0);c=add(s,'c101');s['players'][0]['hand'].remove(c);fx.put(s,0,c,0)
    s['work']=[fx.op('end_triggers',seat=0)];fx.drain(s)
    assert len(s['players'][0]['hand'])==2


def test_scout_grows_on_every_successful_movement():
    s=empty();c=add(s,'c042');s=finish(play(s,c,0));c=fx.entity(s,c['id'])
    assert c.get('boost',0)==0
    for row in [1,0,1]:fx.execute(s,0,fx.op('move',targets=[c['id']],row=row));fx.drain(s)
    assert c['boost']==6 and s['move_count']==3
    fx.execute(s,0,fx.op('move',targets=[c['id']],row=1));fx.drain(s)
    assert s['move_count']==3


def test_agile_spy_uses_enemy_slot_and_draws_two_once():
    s=empty();c=add(s,'c044')
    for _ in range(4):add(s,'c109',zone='deck')
    s=finish(play(s,c,1));assert fx.location(s,c['id'])[:2]==(1,1)
    assert len(s['players'][0]['hand'])==2 and strength(s,c)==2
    fx.deployment(s,0,fx.entity(s,c['id']));fx.drain(s)
    assert len(s['players'][0]['hand'])==2


def test_muster_one_worm_and_return_on_death_but_not_round_cleanup():
    s=empty();a=add(s,'c064');b=add(s,'c065',zone='deck');c=add(s,'c066',zone='deck')
    s=finish(play(s,a,0));assert sum(len(r) for r in s['players'][0]['rows'])==2
    assert len(s['players'][0]['deck'])==1
    fx.damage(s,1,[a['id']],2);fx.settle(s);fx.drain(s,Random(0))
    assert fx.entity(s,a['id']) in s['players'][0]['deck']
    assert not s['players'][0]['discard']
    remaining=next(c for row in s['players'][0]['rows'] for c in row)
    game._begin_round(s,0,Random(0))
    assert fx.entity(s,remaining['id']) in s['players'][0]['discard']


def test_deck_retrieval_and_top_three_bottoming_preserve_entities_and_order():
    s=empty();normal=add(s,'c101',zone='discard');add(s,'c015',zone='discard');spell=add(s,'c111',zone='discard')
    s=play(s,add(s,'c116'));assert {o['card']['id'] for o in s['pending']['options']}=={normal['id'],spell['id']}
    s=finish(s);assert fx.entity(s,normal['id']) in s['players'][0]['deck']
    s=empty();cards=[add(s,'c101',zone='deck') for _ in range(5)]
    s=play(s,add(s,'c106'),0)
    assert {o['card']['id'] for o in s['pending']['options']}=={c['id'] for c in cards[-3:]}
    assert 'options' not in game.project(s,1)['pending']
    token=next(o['token'] for o in s['pending']['options'] if o['card']['id']==cards[-2]['id'])
    s=game.apply_action(json.loads(json.dumps(s)),0,'choose',{'option':token},0)
    assert [c['id'] for c in s['players'][0]['deck']]==[cards[-2]['id']]+[c['id'] for c in cards if c!=cards[-2]]
    assert len(s['players'][0]['hand'])==0


def test_beast_leader_draws_three_then_bottoms_a_hand_card():
    s=empty();s['players'][0]['leader']='c080'
    cards=[add(s,'c101',zone='deck') for _ in range(4)];old=add(s,'c109')
    s=game.apply_action(s,0,'leader',{},0);s=game.apply_action(s,0,'choose',{'option':s['pending']['options'][0]['token']},0)
    assert len(s['players'][0]['hand'])==4
    token=next(o['token'] for o in s['pending']['options'] if o['card']['id']==old['id'])
    s=game.apply_action(s,0,'choose',{'option':token},0)
    assert s['players'][0]['deck'][0]['id']==old['id'] and len(s['players'][0]['hand'])==3


def test_crown_leader_summons_low_normal_without_deploying():
    s=empty();s['players'][0]['leader']='c019';c=add(s,'c027',zone='deck');foe=add(s,'c109',seat=1,zone='rows')
    add(s,'c015',zone='deck');add(s,'c109',zone='deck')
    s=game.apply_action(s,0,'leader',{},0)
    assert {o['card']['id'] for o in s['pending']['options']}=={c['id']}
    s=finish(s);assert fx.location(s,c['id']) and not fx.entity(s,foe['id']).get('damage')


def test_mercenary_destroys_spell_and_snow_guest_condition_is_friendly_siege():
    s=empty();spell=add(s,'c094',seat=1,zone='spells');c=add(s,'c101')
    s=finish(play(s,c,0));assert not s['players'][1]['spells'] and strength(s,c)==2
    hero=add(s,'c055',zone='rows',row=1);assert strength(s,hero)==9
    add(s,'c101',zone='rows',row=2);assert strength(s,hero)==5


def test_gray_veil_starts_after_enemy_card_completion_and_ticks_only_three_times():
    s=empty();target=add(s,'c015',seat=1,zone='rows',boost=4)
    spell=add(s,'c114');s=finish(play(s,spell))
    assert fx.entity(s,target['id']).get('damage',0)==0
    assert fx.entity(s,spell['id']).get('ticks',0)==0
    # Neither the caster's other cards nor an enemy leader action count.
    s['turn']=0;s=finish(play(s,add(s,'c008'),1))
    s['players'][1]['leader']='c019';add(s,'c008',seat=1,zone='deck')
    s=finish(game.apply_action(s,1,'leader',{},0))
    assert fx.entity(s,target['id']).get('damage',0)==0
    for index,(cid,row) in enumerate([('c008',1),('c008',1),('c008',1),('c032',2)]):
        s['turn']=1;s=finish(play(s,add(s,cid,seat=1),row))
        assert fx.entity(s,target['id'])['damage']==min(6,2*(index+1))
    assert fx.entity(s,spell['id'])['ticks']==3
    assert any('2 点伤害' in detail for entry in s['action_log'] for detail in entry['details'])


def test_gray_veil_waits_for_enemy_deployment_choice_to_finish():
    s=empty();target=add(s,'c015',seat=1,zone='rows',boost=4)
    s=finish(play(s,add(s,'c114')))
    s=play(s,add(s,'c004',seat=1),0)
    assert s['pending'] and fx.entity(s,target['id']).get('damage',0)==0
    s=finish(s)
    assert fx.entity(s,target['id'])['damage']==2


def test_gray_veil_stops_on_pass_target_departure_or_spell_destruction():
    for reason in ('pass','bounce','destroy'):
        s=empty();target=add(s,'c015',seat=1,zone='rows',boost=4)
        spell=add(s,'c114');s=finish(play(s,spell))
        if reason=='pass':s=game.apply_action(s,1,'pass',{},0)
        elif reason=='bounce':fx.remove_unit(s,target['id'])
        else:fx.execute(s,1,fx.op('destroy_spell',targets=[spell['id']]))
        assert not fx.entity(s,spell['id']).get('targets') or reason=='destroy'
        before=fx.entity(s,target['id']).get('damage',0)
        fx.start_action(s,1);s['played_card']='some-other-card'
        s['work']=[fx.op('end_triggers',seat=1)];fx.drain(s)
        assert fx.entity(s,target['id']).get('damage',0)==before


def test_ironwall_requires_two_persistents_and_returns_distinct_cards_after_reconnect():
    s=empty();s['players'][0]['leader']='c020'
    a=add(s,'c014',zone='discard');add(s,'c111',zone='discard')
    assert not fx.can_lead(s,0)
    b=add(s,'c094',zone='discard');assert fx.can_lead(s,0)
    s=game.apply_action(s,0,'leader',{},0)
    assert len(s['pending']['options'])==2
    selected=next(o for o in s['pending']['options'] if o['ops'][0]['targets']==[a['id']])
    s=game.apply_action(json.loads(json.dumps(s)),0,'choose',{'option':selected['token']},0)
    assert fx.entity(s,a['id']) in s['players'][0]['hand']
    assert fx.entity(s,b['id']) in s['players'][0]['deck']
    assert len(s['players'][0]['discard'])==1 and s['players'][0]['leader_used']


def test_hero_conditions_use_latest_counts_and_sealing_disables_them():
    s=empty();guard=add(s,'c016',zone='rows');neutral=add(s,'c110',zone='rows',row=1)
    assert strength(s,guard)==5 and strength(s,neutral)==8
    add(s,'c101',zone='rows');add(s,'c008',zone='rows');add(s,'c003',zone='rows')
    assert strength(s,guard)==11 # Three other units, no former +3 ceiling.
    assert strength(s,neutral)==10 # Only the neutral mercenary and itself.
    fx.remove_unit(s,guard['id']);assert strength(s,neutral)==10
    neutral['sealed']=True;assert strength(s,neutral)==6


def test_patroller_counts_every_move_by_both_sides_and_resets_next_round():
    s=empty();hero=add(s,'c058',zone='rows',row=2);a=add(s,'c101',zone='rows');b=add(s,'c101',seat=1,zone='rows')
    for i,(seat,c,row) in enumerate([(0,a,1),(1,b,1),(1,b,0),(0,a,0)]):
        fx.execute(s,seat,fx.op('move',targets=[c['id']],row=row));fx.drain(s)
        assert strength(s,hero)==5+2*(i+1)
    fx.execute(s,1,fx.op('move',targets=[b['id']],row=0));fx.drain(s)
    assert strength(s,hero)==13
    game._begin_round(s,0,Random(0));assert s['move_count']==0


def test_marshal_repeats_deploy_with_taunt_and_no_extra_boost_after_reconnect():
    s=empty();archer=add(s,'c027',zone='rows',row=1)
    tank=add(s,'c102',seat=1,zone='rows',damage=1);other=add(s,'c109',seat=1,zone='rows')
    marshal=add(s,'c037');s=play(s,marshal,1)
    assert {o['card']['id'] for o in s['pending']['options']}=={archer['id']}
    s=finish(s)
    assert fx.entity(s,tank['id']) in s['players'][1]['discard']
    assert fx.entity(s,other['id'])['damage']==2
    assert not fx.entity(s,archer['id']).get('boost') and strength(s,marshal)==5


def test_new_deployment_amounts_and_grave_hero_count():
    for cid,power,amount,row in [('c007',2,3,1),('c027',2,2,1),('c032',2,3,2)]:
        s=empty();foe=add(s,'c109',seat=1,zone='rows',row=1)
        card=add(s,cid);s=finish(play(s,card,row))
        assert strength(s,card)==power and fx.entity(s,foe['id'])['damage']==amount
    s=empty();hero=add(s,'c038',zone='rows')
    for cid in ['c101','c015','c111','c094']:add(s,cid,zone='discard')
    assert strength(s,hero)==6
    add(s,'c108',zone='discard');assert strength(s,hero)==6
    returned=add(s,'c102',zone='discard');assert strength(s,hero)==7
    s['players'][0]['discard'].remove(returned);assert strength(s,hero)==6
    add(s,'c101',seat=1,zone='discard');assert strength(s,hero)==6
    hero['sealed']=True;assert strength(s,hero)==5


def test_general_and_standard_boost_distinct_other_units():
    s=empty();a=add(s,'c101',zone='rows');b=add(s,'c101',zone='rows',row=1)
    c=add(s,'c004');s=finish(play(s,c,0));assert fx.entity(s,a['id'])['boost']==3
    s['turn']=0;c=add(s,'c005');s=play(s,c,0)
    chosen=next(o for o in s['pending']['options'] if set(o['ops'][0]['targets'])=={a['id'],b['id']})
    s=game.apply_action(s,0,'choose',{'option':chosen['token']},0)
    assert fx.entity(s,a['id'])['boost']==5 and fx.entity(s,b['id'])['boost']==2
    assert not fx.entity(s,c['id']).get('boost')


def test_decree_bounces_either_side_normal():
    s=empty();friend=add(s,'c101',zone='rows');add(s,'c015',zone='rows',row=1)
    foe=add(s,'c101',seat=1,zone='rows');add(s,'c056',zone='rows',row=1)
    s['turn']=0;s=play(s,add(s,'c033'))
    assert {o['card']['id'] for o in s['pending']['options']}=={friend['id'],foe['id']}
    s=finish(s);assert fx.entity(s,friend['id']) in s['players'][0]['hand']
    assert fx.location(s,foe['id'])[:2]==(1,0)


def test_frozen_revision_one_keeps_deployed_card_behavior_and_catalogue():
    from pathlib import Path
    from dzmm_bot.core.mistrealm_v3_r1 import mistrealm_v3_state as old
    from dzmm_bot.core.mistrealm_v3_r1.mistrealm_v3_cards import CARDS as previous
    from dzmm_bot.core.mistrealm_repository import _engine
    s=empty();s['balance_revision']=1;card=add(s,'c101')
    s=_engine(s).apply_action(s,0,'play',dict(card=card['id'],row=0),0,Random(0))
    assert old.score_rows(s,0)[0]==5 and not s['pending']
    root=Path(__file__).resolve().parents[2]/'gamefy/mistrealm/publish'
    assert json.loads((root/'v3-r1/cards.json').read_text())['cards']==previous
    assert 'value.state.balance_revision!==2' in (root/'v3/game.js').read_text()
    assert 'value.state.balance_revision!==1' in (root/'v3-r1/game.js').read_text()


def test_last_castellan_scales_with_current_friendly_persistents_and_loses_bonus():
    s=empty();hero=add(s,'c018',zone='rows',row=2)
    add(s,'c094',seat=1,zone='spells')
    add(s,'c014',zone='hand');add(s,'c014',zone='discard')
    assert strength(s,hero)==5
    spells=[]
    for power in (7,9,11):
        spells.append(add(s,'c014',zone='spells'))
        assert strength(s,hero)==power
    assert not hero.get('boost')
    hero['sealed']=True;assert strength(s,hero)==5
    hero.pop('sealed');assert strength(s,hero)==11
    for spell,power in zip(spells,(9,7,5)):
        fx.execute(s,1,fx.op('destroy_spell',targets=[spell['id']]))
        fx.settle(s)
        assert strength(s,hero)==power


def test_last_castellan_can_die_when_persistent_bonus_disappears():
    s=empty();hero=add(s,'c018',zone='rows',row=2,damage=5)
    spell=add(s,'c014',zone='spells')
    assert strength(s,hero)==2
    fx.execute(s,1,fx.op('destroy_spell',targets=[spell['id']]))
    fx.settle(s)
    assert fx.location(s,hero['id']) is None
    assert any(c['id']==hero['id'] for c in s['players'][0]['discard'])


def test_mist_clear_recycles_each_nonhero_type_from_own_discard_only():
    for cid in ('c101','c111','c118'):
        s=empty();target=add(s,cid,zone='discard')
        hero=add(s,'c015',zone='discard');enemy=add(s,cid,seat=1,zone='discard')
        s=play(s,add(s,'c116'))
        assert {o['card']['id'] for o in s['pending']['options']}=={target['id']}
        s=finish(s)
        assert [c['id'] for c in s['players'][0]['deck']]==[target['id']]
        assert hero['id'] in {c['id'] for c in s['players'][0]['discard']}
        assert enemy['id'] in {c['id'] for c in s['players'][1]['discard']}
