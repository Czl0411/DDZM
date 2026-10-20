"""Frost deployments: played-persistent history and full-row damage."""
import pytest
from dzmm_bot.core import mistrealm_v3_effects as fx, mistrealm_v3_state as game
from dzmm_bot.core.mistrealm_v3_cards import CARDS
from tests.core.test_mistrealm_v3 import empty,add,play,finish
from tests.core.test_mistrealm_v3_revision2 import strength


def test_winter_noble_draws_after_played_persistent_even_if_destroyed():
    s=empty();spell=add(s,'c014');s=finish(play(s,spell))
    fx.execute(s,0,fx.op('destroy_spell',targets=[spell['id']]))
    s['turn']=0;drawn=add(s,'c081',zone='deck')
    a=add(s,'c081',zone='rows');b=add(s,'c081',zone='rows',row=2)
    hero=add(s,'c056');s=finish(play(s,hero,1))
    assert s['players'][0]['hand']==[drawn] and strength(s,hero)==5
    assert fx.location(s,a['id'])[:2]==(0,0) and fx.location(s,b['id'])[:2]==(0,2)
    assert not s['pending']


@pytest.mark.parametrize('instant', [0,1,3])
def test_winter_noble_does_not_count_instants_enemy_spells_or_unplayed_cards(instant):
    s=empty();s['players'][0].update(spell_count=instant,instant_count=instant)
    s['players'][1]['spell_count']=1
    add(s,'c014',seat=1,zone='spells');add(s,'c014',zone='hand');add(s,'c014',zone='discard')
    drawn=add(s,'c081',zone='deck');hero=add(s,'c056')
    s=finish(play(s,hero,1))
    assert drawn in s['players'][0]['deck'] and strength(s,hero)==5


@pytest.mark.parametrize('count', [1,2,3,4])
def test_white_stone_hits_every_unit_in_selected_row_counts_self_and_has_no_old_boost(count):
    s=empty()
    for _ in range(count-1):add(s,'c015',zone='rows')
    a=add(s,'c095',seat=1,zone='rows',row=1)
    b=add(s,'c095',seat=1,zone='rows',row=1)
    untouched=add(s,'c095',seat=1,zone='rows',row=2)
    hero=add(s,'c057');s=play(s,hero,0)
    assert {o['row'] for o in s['pending']['options']}=={1,2}
    token=next(o['token'] for o in s['pending']['options'] if o['row']==1)
    s=game.apply_action(s,0,'choose',{'option':token},0)
    for c in (a,b):assert fx.entity(s,c['id'])['damage']==count
    assert not fx.entity(s,untouched['id']).get('damage')
    assert strength(s,hero)==5 and not fx.entity(s,hero['id']).get('boost')


def test_white_stone_row_damage_is_intercepted_once_by_guard():
    s=empty();add(s,'c015',zone='rows')
    tank=add(s,'c102',seat=1,zone='rows',row=1)
    small=add(s,'c043',seat=1,zone='rows',row=1)
    other=add(s,'c095',seat=1,zone='rows',row=2)
    hero=add(s,'c057');s=play(s,hero,0)
    assert {o['row'] for o in s['pending']['options']}=={1,2}
    s=finish(s)
    assert strength(s,tank)==1 and fx.location(s,small['id'])
    assert not fx.entity(s,small['id']).get('damage')
    assert not fx.entity(s,other['id']).get('damage')


def test_bow_description_shortened_without_changing_muster_group():
    assert CARDS['c045']['text']=='召集1。'
    s=empty();bow=add(s,'c045');blade=add(s,'c046',zone='deck');add(s,'c048',zone='deck')
    s=play(s,bow,1)
    assert {o['card']['id'] for o in s['pending']['options'] if o.get('card')}=={blade['id']}
    s=finish(s)
    assert fx.location(s,blade['id'])[:2]==(0,0)


@pytest.mark.parametrize('side',[0,1])
def test_khan_returns_either_persistent_to_its_owner_after_reconnect(side):
    import json
    s=empty();s['players'][0]['leader']='c060'
    spells=[add(s,'c114',seat=i,zone='spells',ticks=2,targets=['old-target']) for i in (0,1)]
    add(s,'c014',zone='discard');add(s,'c014',zone='hand');add(s,'c081',zone='rows')
    s=game.apply_action(s,0,'leader',{},0)
    assert {o['card']['id'] for o in s['pending']['options']}=={c['id'] for c in spells}
    index=next(i for i,o in enumerate(s['pending']['options']) if o['card']['id']==spells[side]['id'])
    s=finish(json.loads(json.dumps(s)),pick=index)
    returned=fx.entity(s,spells[side]['id'])
    assert returned in s['players'][side]['hand'] and returned not in s['players'][side]['discard']
    assert 'ticks' not in returned and 'targets' not in returned
    assert len(s['players'][side]['spells'])==0 and len(s['players'][1-side]['spells'])==1
    assert s['players'][0]['leader_used'] and s['action_id']==1


def test_khan_keeps_draw_two_alternative_and_requires_a_legal_effect():
    s=empty();s['players'][0]['leader']='c060'
    assert not fx.can_lead(s,0)
    drawn=[add(s,'c081',zone='deck') for _ in range(2)]
    spell=add(s,'c014',seat=1,zone='spells')
    s=game.apply_action(s,0,'leader',{},0)
    index=next(i for i,o in enumerate(s['pending']['options']) if o['label']=='抽2张牌')
    s=finish(s,pick=index)
    assert {c['id'] for c in s['players'][0]['hand']}=={c['id'] for c in drawn}
    assert s['players'][1]['spells']==[spell]
    assert not fx.can_lead(s,0)


@pytest.mark.parametrize('cid,name,row',[('c048','雪垒盾卫',0),('c049','寒铁长矛',0),('c050','冰崖弩卫',1)])
def test_renamed_whitewood_units_no_longer_summon(cid,name,row):
    s=empty();unit=add(s,cid)
    reserves=[add(s,other,zone='deck') for other in ('c048','c049','c050') if other!=cid]
    s=play(s,unit,row)
    if cid=='c048':s=finish(s,pick=next(i for i,o in enumerate(s['pending']['options']) if o['label']=='跳过'))
    assert not s['pending'] and s['turn']==1
    assert len(fx.units(s,0))==1 and s['players'][0]['deck']==reserves
    assert strength(s,unit)=={'c048':4,'c049':3,'c050':2}[cid]
    assert CARDS[cid]['name']==name and CARDS[cid]['abilities']==[]
    assert '召集' not in CARDS[cid]['text']+CARDS[cid]['note']


@pytest.mark.parametrize('count',[0,1,2])
def test_snow_guard_can_skip_or_boost_up_to_two_own_units_including_self_and_hero(count):
    s=empty();hero=add(s,'c056',zone='rows',row=2);friend=add(s,'c081',zone='rows',row=1)
    enemy=add(s,'c081',seat=1,zone='rows');guard=add(s,'c048');s=play(s,guard,0)
    chosen=[guard['id'],hero['id']][:count]
    options=s['pending']['options']
    all_targets=[t for o in options for op in o['ops'] for t in op.get('targets',[])]
    assert set(all_targets)=={hero['id'],friend['id'],guard['id']}
    assert all(len(op.get('targets',[]))<=2 and len(set(op.get('targets',[])))==len(op.get('targets',[])) for o in options for op in o['ops'])
    index=next(i for i,o in enumerate(options) if (o['ops'][0]['targets'] if o['ops'] else [])==chosen)
    s=finish(s,pick=index)  # Includes JSON reconnect before applying the choice.
    assert strength(s,guard)==(6 if count else 4)
    assert strength(s,hero)==(7 if count==2 else 5)
    assert not fx.entity(s,friend['id']).get('boost') and not fx.entity(s,enemy['id']).get('boost')
    fx.remove_unit(s,enemy['id'])
    assert strength(s,guard)==(6 if count else 4)


def test_snow_guard_can_choose_two_other_units_and_seal_blocks_deployment():
    s=empty();a=add(s,'c081',zone='rows');b=add(s,'c056',zone='rows',row=2)
    guard=add(s,'c048');s=play(s,guard,0)
    index=next(i for i,o in enumerate(s['pending']['options']) if o['ops'] and set(o['ops'][0]['targets'])=={a['id'],b['id']})
    s=finish(s,pick=index)
    assert strength(s,guard)==4
    assert all(fx.entity(s,c['id'])['boost']==2 for c in (a,b))
    fx.entity(s,guard['id'])['sealed']=True
    fx.deployment(s,0,fx.entity(s,guard['id']));fx.drain(s)
    assert not s['pending'] and all(fx.entity(s,c['id'])['boost']==2 for c in (a,b))


def test_lance_boosts_before_enemy_spell_resolution_without_cap():
    s=empty();lance=add(s,'c049',zone='rows')
    own=add(s,'c014');s=finish(play(s,own))
    assert strength(s,lance)==3
    for cid,expected in [('c014',5),('c093',7),('c014',9)]:
        s['turn']=1
        if cid=='c093':
            add(s,'c081',seat=1,zone='deck');add(s,'c081',seat=1,zone='deck')
        spell=add(s,cid,seat=1);s=play(s,spell)
        assert s['pending'] and strength(s,lance)==expected
        s=finish(s)  # Persist/reconnect during selection must not award the boost again.
        assert strength(s,lance)==expected
    assert fx.entity(s,lance['id'])['uncapped_boost']==6


@pytest.mark.parametrize('spell_id,expected',[('c111',1),('c120',3)])
def test_lance_boost_precedes_incoming_damage_or_seal(spell_id,expected):
    s=empty();lance=add(s,'c049',zone='rows');s['turn']=1
    spell=add(s,spell_id,seat=1);s=play(s,spell)
    assert strength(s,lance)==5
    s=finish(s)
    assert fx.location(s,lance['id']) is not None
    assert strength(s,lance)==expected and fx.entity(s,lance['id'])['uncapped_boost']==2


def test_already_sealed_lance_does_not_react():
    s=empty();lance=add(s,'c049',zone='rows',sealed=True);s['turn']=1
    spell=add(s,'c014',seat=1);s=finish(play(s,spell))
    assert strength(s,lance)==3 and not fx.entity(s,lance['id']).get('uncapped_boost')


def test_lance_does_not_retroactively_count_spells_or_react_to_unit_plays():
    s=empty();s['players'][1]['spell_count']=5
    lance=add(s,'c049');s=play(s,lance,0)
    assert strength(s,lance)==3
    unit=add(s,'c081',seat=1);s=play(s,unit,0)
    assert strength(s,lance)==3


def test_persistent_later_ticks_do_not_boost_lance_again():
    s=empty();lance=add(s,'c049',zone='rows');s['turn']=1
    spell=add(s,'c114',seat=1);s=finish(play(s,spell))
    assert strength(s,lance)==5
    for damage in (2,4):
        s['turn']=0;unit=add(s,'c081');s=play(s,unit,0)
        current=fx.entity(s,lance['id'])
        assert current['uncapped_boost']==2 and current['damage']==damage
        assert strength(s,lance)==5-damage


@pytest.mark.parametrize('side',[0,1])
def test_cliff_guard_deployment_moves_other_normal_on_either_side(side):
    s=empty();friend=add(s,'c081',zone='rows');foe=add(s,'c081',seat=1,zone='rows')
    add(s,'c056',seat=1,zone='rows');add(s,'c056',zone='rows')
    guard=add(s,'c050');s=play(s,guard,1)
    assert {o['card']['id'] for o in s['pending']['options'] if o.get('card')}=={friend['id'],foe['id']}
    target=(friend,foe)[side]
    index=next(i for i,o in enumerate(s['pending']['options']) if o.get('card',{}).get('id')==target['id'] and o['row']==2)
    s=finish(s,pick=index)
    assert fx.location(s,target['id'])[:2]==(side,2)
    assert strength(s,guard)==2


@pytest.mark.parametrize('side',[0,1])
def test_cliff_guard_moved_returns_to_original_owner_clears_effects_and_can_redeploy(side):
    s=empty();guard=add(s,'c050',seat=side,zone='rows',row=1,boost=2,damage=1)
    guard['owner']=0
    spell=add(s,'c118',zone='spells',targets=[guard['id']])
    fx.execute(s,0,fx.op('move',targets=[guard['id']],row=2));fx.drain(s)
    assert fx.location(s,guard['id']) is None and guard in s['players'][0]['hand']
    assert guard not in s['players'][0]['discard'] and s['move_count']==1
    assert 'boost' not in guard and 'damage' not in guard and not spell['targets']
    target=add(s,'c081',seat=1,zone='rows')
    s['turn']=0;s=play(s,guard,1)
    assert any(o.get('card',{}).get('id')==target['id'] for o in s['pending']['options'])
    s=finish(s)
    assert fx.location(s,guard['id'])[:2]==(0,1) and strength(s,guard)==2


@pytest.mark.parametrize('reason',['sealed','same_row','full_row'])
def test_cliff_guard_does_not_bounce_without_successful_unsealed_move(reason):
    s=empty();guard=add(s,'c050',zone='rows',row=1)
    if reason=='sealed':guard['sealed']=True
    if reason=='full_row':
        for _ in range(4):add(s,'c081',zone='rows',row=2)
    fx.execute(s,0,fx.op('move',targets=[guard['id']],row=1 if reason=='same_row' else 2));fx.drain(s)
    assert fx.location(s,guard['id'])[:2]==(0,2 if reason=='sealed' else 1)
    assert guard not in s['players'][0]['hand'] and 'bounce_round' not in guard


def test_snowline_ranger_replaces_deployment_and_does_not_count_existing_units():
    s=empty();add(s,'c081',seat=1,zone='rows');friend=add(s,'c081',zone='rows')
    ranger=add(s,'c041');s=play(s,ranger,0)
    assert strength(s,ranger)==3 and not s['pending']
    assert fx.location(s,friend['id'])[:2]==(0,0)
    enemy=add(s,'c081',seat=1);s=finish(play(s,enemy,0))
    assert strength(s,ranger)==4
    fx.remove_unit(s,enemy['id'])
    assert strength(s,ranger)==4  # Entry reward remains after the entrant leaves.


@pytest.mark.parametrize('kind',['summon','revive'])
def test_snowline_ranger_counts_summon_and_revive_once(kind):
    s=empty();ranger=add(s,'c041',zone='rows')
    unit=add(s,'c081',seat=1,zone='deck' if kind=='summon' else 'discard')
    fx.execute(s,1,fx.op(kind,targets=[unit['id']],row=0));fx.drain(s)
    assert strength(s,ranger)==4
    fx.execute(s,1,fx.op(kind,targets=[unit['id']],row=0));fx.drain(s)
    assert strength(s,ranger)==4


def test_snowline_ranger_counts_reentry_without_cap_and_tracks_current_row():
    s=empty();ranger=add(s,'c041',zone='rows');enemy=add(s,'c081',seat=1,zone='rows',row=1)
    for expected in (4,5,6,7,8,9):
        fx.execute(s,0,fx.op('move',targets=[enemy['id']],row=0));fx.drain(s)
        assert strength(s,ranger)==expected
        fx.execute(s,0,fx.op('move',targets=[enemy['id']],row=0));fx.drain(s)
        assert strength(s,ranger)==expected  # Moving to the same row is not an entry.
        fx.execute(s,0,fx.op('move',targets=[enemy['id']],row=1));fx.drain(s)
    assert ranger['uncapped_boost']==6
    ranger['uncapped_boost']=0
    fx.execute(s,0,fx.op('move',targets=[ranger['id']],row=1));fx.drain(s)
    assert strength(s,ranger)==3  # Moving the ranger does not count enemies already there.
    fx.execute(s,0,fx.op('move',targets=[enemy['id']],row=0));fx.drain(s)
    assert strength(s,ranger)==3
    fx.execute(s,0,fx.op('move',targets=[enemy['id']],row=1));fx.drain(s)
    assert strength(s,ranger)==4


def test_snowline_ranger_ignores_heroes_own_entries_other_rows_and_sealed_effect():
    s=empty();ranger=add(s,'c041',zone='rows')
    for cid,seat,row in [('c056',1,0),('c081',0,0),('c081',1,1)]:
        c=add(s,cid,seat=seat);s['players'][seat]['hand'].remove(c);fx.put(s,seat,c,row)
    assert strength(s,ranger)==3
    ranger['sealed']=True
    c=add(s,'c081',seat=1);s['players'][1]['hand'].remove(c);fx.put(s,1,c,0)
    assert strength(s,ranger)==3
    ranger['sealed']=False
    assert strength(s,ranger)==3


def test_snowline_ranger_rewards_entry_before_enemy_deployment_damage():
    s=empty();ranger=add(s,'c041',zone='rows');s['turn']=1
    attacker=add(s,'c022',seat=1);s=play(s,attacker,0)
    assert s['pending'] and strength(s,ranger)==4
    s=finish(s)
    assert strength(s,ranger)==2 and fx.entity(s,ranger['id'])['uncapped_boost']==1


def test_snowline_ranger_triggers_for_all_unsealed_rangers_on_destination_board():
    s=empty();rangers=[add(s,'c041',seat=1,zone='rows') for _ in range(2)]
    unit=add(s,'c081');s=play(s,unit,0)
    assert [strength(s,c) for c in rangers]==[4,4]


def test_cliff_guard_bounce_once_per_round_survives_reconnect_redeploy_and_revive():
    import json
    s=empty();guard=add(s,'c050',zone='rows',row=1)
    fx.execute(s,0,fx.op('move',targets=[guard['id']],row=2));fx.drain(s)
    assert guard in s['players'][0]['hand'] and guard['bounce_round']==1
    s=json.loads(json.dumps(s));guard=fx.entity(s,guard['id'])
    s=finish(play(s,guard,1))
    fx.execute(s,0,fx.op('move',targets=[guard['id']],row=2));fx.drain(s)
    assert fx.location(s,guard['id'])[:2]==(0,2)
    fx.execute(s,0,fx.op('sacrifice',targets=[guard['id']]));fx.settle(s);fx.drain(s)
    fx.execute(s,0,fx.op('revive',targets=[guard['id']],row=1));fx.drain(s)
    fx.execute(s,0,fx.op('move',targets=[guard['id']],row=2));fx.drain(s)
    assert fx.location(s,guard['id'])[:2]==(0,2)
    s['turn']=0
    s=game.apply_action(s,0,'pass',{},0)
    s=game.apply_action(s,1,'pass',{},0)
    assert s['phase']=='round_result'
    s=game.advance(s,s['deadline_ms'])
    assert s['round']==2
    fx.execute(s,0,fx.op('revive',targets=[guard['id']],row=1));fx.drain(s)
    fx.execute(s,0,fx.op('move',targets=[guard['id']],row=2));fx.drain(s)
    current=fx.entity(s,guard['id'])
    assert current in s['players'][0]['hand'] and current['bounce_round']==2


def test_cliff_guard_bounce_quota_is_per_entity():
    s=empty();guards=[add(s,'c050',zone='rows',row=1) for _ in range(2)]
    for c in guards:
        fx.execute(s,0,fx.op('move',targets=[c['id']],row=2));fx.drain(s)
    assert all(c in s['players'][0]['hand'] and c['bounce_round']==1 for c in guards)


@pytest.mark.parametrize('side',[0,1])
def test_frost_banish_moves_own_or_enemy_normal_and_boosts_or_damages(side):
    s=empty();own=add(s,'c081',zone='rows');foe=add(s,'c081',seat=1,zone='rows',boost=4)
    add(s,'c056',zone='rows');add(s,'c056',seat=1,zone='rows')
    spell=add(s,'c053');s=play(s,spell)
    assert {o['card']['id'] for o in s['pending']['options']}=={own['id'],foe['id']}
    target=(own,foe)[side]
    index=next(i for i,o in enumerate(s['pending']['options']) if o['card']['id']==target['id'] and o['row']==2)
    s=finish(s,pick=index)
    assert fx.location(s,target['id'])[:2]==(side,2)
    current=fx.entity(s,target['id'])
    if side==0:
        assert current['boost']==4 and not current.get('damage')
        assert not fx.entity(s,foe['id']).get('damage')
    else:
        assert current['damage']==4 and current['boost']==4
        assert not fx.entity(s,own['id']).get('boost')
    assert fx.entity(s,spell['id']) in s['players'][0]['discard']


def test_frost_banish_enemy_damage_can_kill_and_triggers_movement_draw_first():
    s=empty();target=add(s,'c043',seat=1,zone='rows');drawn=add(s,'c081',seat=1,zone='deck')
    spell=add(s,'c053');s=finish(play(s,spell))
    assert fx.location(s,target['id']) is None
    assert fx.entity(s,target['id']) in s['players'][1]['discard']
    assert drawn in s['players'][1]['hand']


def test_frost_banish_requires_available_destination_on_targets_own_side():
    s=empty();unit=add(s,'c081',zone='rows')
    for row in (1,2):
        for _ in range(4):add(s,'c056',zone='rows',row=row)
    spell=add(s,'c053')
    assert not fx.can_play(s,0,spell,-1)
    s['players'][0]['rows'][2].pop()
    choices=fx.menu(s,0,spell)
    assert len(choices)==1 and choices[0]['card']['id']==unit['id'] and choices[0]['row']==2
    assert fx.can_play(s,0,spell,-1)
