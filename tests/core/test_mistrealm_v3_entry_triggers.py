"""Entry listeners use destination rows, independent of who initiated movement."""
import pytest
from dzmm_bot.core import mistrealm_v3_effects as fx, mistrealm_v3_state as game
from tests.core.test_mistrealm_v3 import empty, add, finish
from tests.core.test_mistrealm_v3_revision2 import strength


def end_action(s, actor):
    s['work'].append(fx.op('end_triggers',seat=actor))
    fx.drain(s)


@pytest.mark.parametrize('actor',[0,1])
def test_trap_and_ranger_count_enemy_entry_from_either_players_move(actor):
    s=empty();ranger=add(s,'c041',zone='rows',row=1)
    trap=add(s,'c054',zone='spells',row=1);trap['row']=1
    target=add(s,'c081',seat=1,zone='rows')
    fx.start_action(s,actor)
    fx.execute(s,actor,fx.op('move',targets=[target['id']],row=1))
    assert strength(s,ranger)==4
    assert target.get('damage',0)==0  # Trap still settles at the end of the action.
    end_action(s,actor)
    assert target['damage']==2 and trap['trap_used']==1
    fx.start_action(s,1-actor);end_action(s,1-actor)
    assert target['damage']==2 and strength(s,ranger)==4  # Old entries do not repeat.


@pytest.mark.parametrize('kind',['existing','same_row','other_row','friendly','full_row'])
def test_entry_listeners_do_not_trigger_without_eligible_enemy_entry(kind):
    s=empty();ranger=add(s,'c041',zone='rows',row=1)
    trap=add(s,'c054',zone='spells');trap['row']=1
    target=add(s,'c081',seat=0 if kind=='friendly' else 1,zone='rows',row=1 if kind in ('existing','same_row') else 0)
    if kind=='full_row':
        for _ in range(4):add(s,'c081',seat=1,zone='rows',row=1)
    fx.start_action(s,1)
    if kind!='existing':fx.execute(s,1,fx.op('move',targets=[target['id']],row=2 if kind=='other_row' else 1))
    end_action(s,1)
    assert not target.get('damage') and not trap.get('trap_used')
    assert strength(s,ranger)==3


@pytest.mark.parametrize('kind',['summon','revive'])
def test_entry_listeners_count_enemy_summon_and_revive(kind):
    s=empty();ranger=add(s,'c041',zone='rows',row=1)
    trap=add(s,'c054',zone='spells');trap['row']=1
    target=add(s,'c081',seat=1,zone='deck' if kind=='summon' else 'discard')
    fx.start_action(s,1);fx.execute(s,1,fx.op(kind,targets=[target['id']],row=1));end_action(s,1)
    assert strength(s,ranger)==4 and target['damage']==2


def test_trap_skips_departed_entrant_and_hits_only_first_remaining_entry():
    s=empty();ranger=add(s,'c041',zone='rows',row=1)
    trap=add(s,'c054',zone='spells');trap['row']=1
    units=[add(s,'c081',seat=1,zone='rows') for _ in range(3)]
    fx.start_action(s,0)
    for c in units:fx.execute(s,0,fx.op('move',targets=[c['id']],row=1))
    fx.execute(s,0,fx.op('move',targets=[units[0]['id']],row=2))
    end_action(s,0)
    assert [c.get('damage',0) for c in units]==[0,2,0]
    assert trap['trap_used']==1 and strength(s,ranger)==6


def test_trap_counts_owner_actions_toward_three_trigger_limit():
    s=empty();trap=add(s,'c054',zone='spells');trap['row']=1
    for _ in range(4):
        target=add(s,'c081',seat=1,zone='rows');fx.start_action(s,0)
        fx.execute(s,0,fx.op('move',targets=[target['id']],row=1));end_action(s,0)
        assert target.get('damage',0)==(2 if _<3 else 0)
        fx.remove_unit(s,target['id'])
    assert trap['trap_used']==3


def test_real_queen_action_triggers_trap_after_enemy_move_and_choice_resolution():
    s=empty();s['players'][0]['leader']='c059'
    trap=add(s,'c054',zone='spells');trap['row']=1
    target=add(s,'c095',seat=1,zone='rows')
    s=game.apply_action(s,0,'leader',{},0)
    option=next(o for o in s['pending']['options'] if o['card']['id']==target['id'] and o['row']==1)
    s=game.apply_action(s,0,'choose',{'option':option['token']},0)
    s=finish(s,pick=-1)
    assert fx.entity(s,target['id'])['damage']==4  # Queen 2, then trap 2.
    assert fx.entity(s,trap['id'])['trap_used']==1


def test_trap_damage_can_be_intercepted_by_guard_outside_marked_row():
    s=empty();trap=add(s,'c054',zone='spells');trap['row']=1
    guard=add(s,'c102',seat=1,zone='rows',row=2)
    target=add(s,'c081',seat=1,zone='rows')
    fx.start_action(s,0);fx.execute(s,0,fx.op('move',targets=[target['id']],row=1));end_action(s,0)
    assert not target.get('damage') and guard['damage']==2 and trap['trap_used']==1
