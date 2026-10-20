"""Mirror changes: real card transfers and spell-dependent effects."""
from random import Random
from dzmm_bot.core import mistrealm_v3_state as game, mistrealm_v3_effects as fx
from dzmm_bot.core.mistrealm_v3_cards import CARDS
from tests.core.test_mistrealm_v3 import empty,add,play,finish
from tests.core.test_mistrealm_v3_beast import strength


def test_morning_takes_one_discards_the_other_and_handles_one_remaining_card():
    s=empty();bottom=add(s,'c101',zone='deck');a=add(s,'c007',zone='deck');b=add(s,'c008',zone='deck')
    s=play(s,add(s,'c084'),0)
    assert {o['card']['id'] for o in s['pending']['options']}=={a['id'],b['id']}
    assert 'options' not in game.project(s,1)['pending']
    s=finish(s)
    assert s['players'][0]['hand']==[a] and s['players'][0]['deck']==[bottom]
    assert [c['id'] for c in s['players'][0]['discard']]==[b['id']]
    s=empty();a=add(s,'c007',zone='deck');s=finish(play(s,add(s,'c084'),0))
    assert s['players'][0]['hand']==[a] and not s['players'][0]['discard']


def test_night_boosts_exactly_two_friendly_units_including_itself():
    s=empty();s['players'][0]['instant_count']=1;ally=add(s,'c101',zone='rows',row=1)
    night=add(s,'c086');s=play(s,night,0)
    assert all(len(o['ops'][0]['targets'])==2 for o in s['pending']['options'])
    s=finish(s)
    assert fx.entity(s,ally['id'])['boost']==2 and fx.entity(s,night['id'])['boost']==2
    s=empty();s['players'][0]['instant_count']=1;night=add(s,'c086');s=finish(play(s,night,0))
    assert not fx.entity(s,night['id']).get('boost')


def test_hand_advantage_is_live_nonnegative_and_sealable():
    s=empty();hero=add(s,'c096',zone='rows')
    for _ in range(6):add(s,'c101')
    add(s,'c101',seat=1)
    assert strength(s,hero)==10
    for _ in range(7):add(s,'c101',seat=1)
    assert strength(s,hero)==5
    s['players'][1]['hand']=[];hero['sealed']=True;assert strength(s,hero)==5


def test_sage_gets_one_per_instant_and_round_reset_clears_count():
    s=empty();hero=add(s,'c097',zone='rows',row=1)
    for n in range(1,6):
        add(s,'c101',zone='discard');s['turn']=0;s=finish(play(s,add(s,'c116')))
        assert strength(s,hero)==5+n
    game._begin_round(s,0,Random(0));assert s['players'][0]['instant_count']==0
    assert CARDS['c087']['power']==3


def test_bow_deployment_and_bronze_round_condition_and_targets():
    assert CARDS['c082']['power']==2
    for count in (0,1):
        s=empty();s['players'][0]['instant_count']=count;bow=add(s,'c082')
        s=finish(play(s,bow,1));assert strength(s,bow)==(6 if count else 2)
    s=empty();ally=add(s,'c109',zone='rows');foe=add(s,'c109',seat=1,zone='rows');bow=add(s,'c083',zone='rows',row=2)
    assert fx.menu(s,0,bow)==[]
    s['players'][0]['instant_count']=1
    assert {o['card']['id'] for o in fx.menu(s,0,bow)}=={ally['id'],foe['id'],bow['id']}
    assert all(o['ops'][0]['amount']==3 for o in fx.menu(s,0,bow))
    taunt=add(s,'c102',seat=1,zone='rows')
    assert {o['card']['id'] for o in fx.menu(s,0,bow)}=={ally['id'],foe['id'],bow['id'],taunt['id']}
    game._begin_round(s,0,Random(0));assert fx.menu(s,0,bow)==[]


def test_blood_walker_later_friendly_persistents_boost_without_cap():
    s=empty();old=add(s,'c094',zone='spells');walker=add(s,'c088')
    s=finish(play(s,walker,0));assert strength(s,walker)==3
    s['turn']=1;s=finish(play(s,add(s,'c094',seat=1)));assert strength(s,walker)==3
    for expected in (6,9):
        s['turn']=0;s=finish(play(s,add(s,'c094')));assert strength(s,walker)==expected
    for spell in list(s['players'][0]['spells']):fx.execute(s,0,fx.op('destroy_spell',targets=[spell['id']]))
    assert strength(s,walker)==9
    s['turn']=0;s=finish(play(s,add(s,'c094')));assert strength(s,walker)==12
    fx.execute(s,0,fx.op('boost',targets=[walker['id']],amount=8))
    assert strength(s,walker)==20 and fx.entity(s,walker['id'])['boost']==8
    ally=add(s,'c101',zone='rows',row=2)
    fx.execute(s,0,fx.op('boost',targets=[ally['id']],amount=8))
    assert strength(s,ally)==10
    fx.remove_unit(s,walker['id']);s['turn']=0;s=finish(play(s,fx.entity(s,walker['id']),0))
    assert strength(s,walker)==3
    fx.entity(s,walker['id'])['sealed']=True;s['turn']=0;s=finish(play(s,add(s,'c094')))
    assert strength(s,walker)==3


def test_evening_swaps_only_nonheroes_and_entity_limit_survives_bounce_and_round():
    s=empty();hand=add(s,'c111');grave=add(s,'c093',zone='discard')
    add(s,'c095');add(s,'c096',zone='discard');dusk=add(s,'c085')
    s=play(s,dusk,0)
    assert len(s['pending']['options'])==1
    s=finish(s)
    assert any(c['id']==grave['id'] for c in s['players'][0]['hand'])
    assert any(c['id']==hand['id'] for c in s['players'][0]['discard'])
    assert fx.entity(s,dusk['id'])['exchange_used']
    fx.remove_unit(s,dusk['id']);s['turn']=0;s=finish(play(s,fx.entity(s,dusk['id']),0))
    assert fx.menu(s,0,fx.entity(s,dusk['id']))==[]
    game._begin_round(s,0,Random(0))
    assert fx.entity(s,dusk['id'])['exchange_used']
    assert fx.menu(s,0,fx.entity(s,dusk['id']))==[]


def test_ritualist_recasts_discard_instant_with_choices_and_spell_synergies_once():
    s=empty();sage=add(s,'c097',zone='rows',row=1);ally=add(s,'c081',zone='rows',row=1)
    echo=add(s,'c094',zone='spells');target=add(s,'c109',seat=1,zone='rows')
    add(s,'c081',seat=1,zone='rows');spell=add(s,'c111',zone='discard')
    add(s,'c094',zone='discard');add(s,'c101',zone='discard');ritualist=add(s,'c090')
    s=play(s,ritualist,0);action=s['action_id']
    assert {o['card']['id'] for o in s['pending']['options']}=={spell['id']}
    s=game.apply_action(s,0,'choose',{'option':'0'},0,Random(0))
    assert {o['card']['card'] for o in s['pending']['options']}=={'c109','c081'}
    s=finish(s)
    assert s['action_id']==action and s['turn']==1 and s['players'][0]['instant_count']==1
    assert not s['players'][0]['resolving'] and any(c['id']==spell['id'] for c in s['players'][0]['discard'])
    assert strength(s,sage)==6 and not fx.entity(s,ally['id']).get('boost')
    assert fx.entity(s,ritualist['id'])['boost']==3 and CARDS['c090']['power']==2
    assert fx.entity(s,target['id'])['damage']==4 and fx.entity(s,echo['id'])['healed_round']==1


def test_recast_does_not_double_end_action_damage_or_allow_unplayable_spell():
    s=empty();spell=add(s,'c111',zone='discard');ritualist=add(s,'c090')
    assert fx.menu(s,0,ritualist)==[]
    target=add(s,'c109',seat=1,zone='rows');moss=add(s,'c072',zone='rows',row=2,boost=4)
    gray=add(s,'c114',seat=1,zone='spells',targets=[moss['id']])
    s=finish(play(s,ritualist,0))
    assert fx.entity(s,gray['id'])['ticks']==1
    assert fx.entity(s,moss['id'])['damage']==2


def test_summoner_sacrifices_only_other_normal_then_recovers_any_discard():
    s=empty();hero=add(s,'c095',zone='rows',row=2);victim=add(s,'c071',zone='rows')
    recovered=add(s,'c096',zone='discard');summoner=add(s,'c092')
    s=play(s,summoner,1)
    assert {o['card']['id'] for o in s['pending']['options']}=={victim['id']}
    s=game.apply_action(s,0,'choose',{'option':'0'},0,Random(0))
    assert s['pending']['title']=='阵亡：选择强化目标'
    s=game.apply_action(s,0,'choose',{'option':'0'},0,Random(0))
    assert {o['card']['id'] for o in s['pending']['options']}=={recovered['id'],victim['id']}
    s=finish(s)
    assert any(c['id']==recovered['id'] for c in s['players'][0]['hand'])
    assert fx.entity(s,summoner['id'])['boost']==3
    assert any(c['id']==victim['id'] for c in s['players'][0]['discard'])


def test_judge_destroys_both_sides_persistents_and_boosts_without_cap():
    s=empty();spells=[add(s,'c094',seat=seat,zone='spells') for seat in (0,0,0,1,1,1)]
    judge=add(s,'c095');s=finish(play(s,judge,2))
    assert strength(s,judge)==17 and fx.entity(s,judge['id'])['uncapped_boost']==12
    assert all(not p['spells'] for p in s['players'])
    assert {c['id'] for p in s['players'] for c in p['discard']}=={c['id'] for c in spells}
    s=empty();judge=add(s,'c095');s=finish(play(s,judge,2));assert strength(s,judge)==5


def test_young_walker_draws_two_for_any_friendly_discard_entry_even_after_recovery():
    for event in ('death','discard_hand','instant','persistent','deck_discard'):
        s=empty()
        if event=='death':
            c=add(s,'c101',zone='rows');fx.damage(s,0,[c['id']],2);fx.settle(s)
        elif event=='discard_hand':
            c=add(s,'c111');fx.execute(s,0,fx.op('discard_hand',targets=[c['id']]))
        elif event=='instant':
            c=add(s,'c093');add(s,'c101',zone='deck');s=finish(play(s,c))
        elif event=='persistent':
            c=add(s,'c094',zone='spells');fx.execute(s,0,fx.op('destroy_spell',targets=[c['id']]))
        else:
            c=add(s,'c101',zone='deck');chosen=add(s,'c007',zone='deck')
            fx.execute(s,0,fx.op('top',targets=[chosen['id']]))
        fx.execute(s,0,fx.op('recover',targets=[c['id']]))
        assert not s['players'][0]['discard']
        cards=[add(s,'c007',zone='deck'),add(s,'c008',zone='deck')]
        walker=add(s,'c089');before=len(s['players'][0]['hand']);s['turn']=0
        s=finish(play(s,walker,1))
        assert CARDS['c089']['power']==2 and len(s['players'][0]['hand'])==before+1
        assert all(any(x['id']==c['id'] for x in s['players'][0]['hand']) for c in cards)


def test_young_walker_ignores_enemy_discard_and_old_round_cleanup():
    for reset in (False,True):
        s=empty();c=add(s,'c101',seat=0 if reset else 1,zone='rows')
        fx.damage(s,0,[c['id']],2);fx.settle(s)
        if reset:
            add(s,'c101',zone='rows');add(s,'c094',zone='spells')
            game._begin_round(s,0,Random(0))
        drawn=add(s,'c007',zone='deck');walker=add(s,'c089');s['turn']=0
        s=finish(play(s,walker,1))
        assert any(c['id']==drawn['id'] for c in s['players'][0]['deck'])
        assert not s['players'][0]['hand']


def test_statue_empty_hand_aura_is_friendly_melee_only_and_tracks_hand_changes():
    s=empty();ally=add(s,'c081',zone='rows');ranged=add(s,'c081',zone='rows',row=1)
    foe=add(s,'c081',seat=1,zone='rows');statue=add(s,'c098')
    s=finish(play(s,statue,0))
    assert strength(s,statue)==8 and strength(s,ally)==CARDS['c081']['power']+3
    assert strength(s,ranged)==strength(s,foe)==CARDS['c081']['power']
    drawn=add(s,'c111',zone='deck');fx.draw(s['players'][0],1)
    assert strength(s,statue)==5 and strength(s,ally)==CARDS['c081']['power']
    fx.execute(s,0,fx.op('discard_hand',targets=[drawn['id']]))
    assert strength(s,statue)==8
    # Moving the aura source does not change which row is supported.
    fx.execute(s,0,fx.op('move',targets=[statue['id']],row=2))
    assert strength(s,statue)==5 and strength(s,ally)==CARDS['c081']['power']+3


def test_statue_seal_and_departure_remove_aura_and_can_cause_conditional_death():
    for removal in ('seal','bounce','death'):
        s=empty();statue=add(s,'c098',zone='rows');ally=add(s,'c081',zone='rows',damage=CARDS['c081']['power'])
        fx.settle(s);assert fx.location(s,ally['id'])
        if removal=='seal':fx.execute(s,1,fx.op('seal',targets=[statue['id']]))
        elif removal=='bounce':fx.remove_unit(s,statue['id'])
        else:fx.damage(s,1,[statue['id']],8)
        fx.settle(s)
        assert not fx.location(s,ally['id'])
        assert any(c['id']==ally['id'] for c in s['players'][0]['discard'])


def test_statue_external_bonus_survives_recipient_seal_and_does_not_use_boost_cap():
    s=empty();statue=add(s,'c098',zone='rows');ally=add(s,'c081',zone='rows',boost=4,sealed=True)
    assert strength(s,ally)==CARDS['c081']['power']+7
    fx.execute(s,1,fx.op('seal',targets=[statue['id']]))
    assert strength(s,ally)==CARDS['c081']['power']+4 and strength(s,statue)==5
    fx.execute(s,0,fx.op('unseal',targets=[statue['id']]))
    assert strength(s,ally)==CARDS['c081']['power']+7


def test_mirror_guard_four_power_no_bond_and_no_delayed_trigger():
    s=empty();first=add(s,'c081');s=finish(play(s,first,0))
    s['turn']=0;second=add(s,'c081');s=finish(play(s,second,0))
    assert CARDS['c081']['power']==4 and CARDS['c081']['abilities']==[]
    assert strength(s,first)==strength(s,second)==4
    victim=add(s,'c101',zone='rows',row=1)
    fx.damage(s,1,[victim['id']],2);fx.settle(s);fx.drain(s)
    assert s['players'][0]['discarded_this_round']
    assert strength(s,first)==strength(s,second)==4
    fx.deployment(s,0,fx.entity(s,first['id']));fx.drain(s)
    assert strength(s,first)==6 and strength(s,second)==4


def test_mirror_guard_uses_only_current_round_friendly_discard_and_keeps_boost():
    from dzmm_bot.core.mistrealm_v3_hints import card_status
    for side in (0,1):
        s=empty();victim=add(s,'c101',seat=side)
        fx.execute(s,side,fx.op('discard_hand',targets=[victim['id']]))
        fx.execute(s,side,fx.op('recover',targets=[victim['id']]))
        guard=add(s,'c081')
        status=card_status(s,0,guard,'hand')
        assert any(t['short']==('条件已满足' if side==0 else '条件未满足') for t in status)
        s=finish(play(s,guard,0));assert strength(s,guard)==(6 if side==0 else 4)
        fx.entity(s,guard['id'])['sealed']=True
        assert strength(s,guard)==(6 if side==0 else 4)
        game._begin_round(s,0,Random(0))
        fx.execute(s,0,fx.op('recover',targets=[guard['id']]))
        s['turn']=0;s=finish(play(s,fx.entity(s,guard['id']),0))
        assert strength(s,guard)==4


def test_mirror_guard_revive_deploys_but_summon_does_not():
    s=empty();guard=add(s,'c081',zone='rows')
    fx.remove_unit(s,guard['id'],True);fx.settle(s);fx.drain(s)
    s=finish(play(s,add(s,'c051'),1))
    assert strength(s,guard)==6
    summoned=add(s,'c081',zone='deck')
    fx.execute(s,0,fx.op('summon',targets=[summoned['id']],row=0));fx.drain(s)
    assert strength(s,summoned)==4


def test_ritualist_target_limit_is_shared_across_casters_but_not_spell_copies():
    s=empty();spell=add(s,'c013',zone='discard');ritualist=add(s,'c090')
    s=finish(play(s,ritualist,0))
    assert s['players'][0]['instant_count']==1
    caster=fx.entity(s,ritualist['id'])
    assert fx.menu(s,0,caster)==[]
    fx.deployment(s,0,caster);fx.drain(s)
    other=add(s,'c090');s['turn']=0;s=finish(play(s,other,0))
    assert s['players'][0]['instant_count']==1
    # A saved/repeated effect cannot bypass the target's used flag.
    fx.execute(s,0,fx.op('recast',targets=[spell['id']]));fx.drain(s)
    assert s['players'][0]['instant_count']==1
    copy=add(s,'c013',zone='discard')
    assert {o['card']['id'] for o in fx.menu(s,0,fx.entity(s,other['id']))}=={copy['id']}
    fx.deployment(s,0,fx.entity(s,other['id']));fx.drain(s);s=finish(s)
    assert s['players'][0]['instant_count']==2


def test_ritualist_target_limit_survives_recovery_recycling_rounds_and_reconnect():
    import json
    from dzmm_bot.core.mistrealm_v3_hints import card_status
    s=empty();spell=add(s,'c013',zone='discard');ritualist=add(s,'c090')
    s=finish(play(s,ritualist,0))
    fx.execute(s,0,fx.op('recover',targets=[spell['id']]))
    s['turn']=0;s=finish(play(s,fx.entity(s,spell['id'])))
    assert s['players'][0]['instant_count']==2  # Normal hand play is unchanged.
    fx.execute(s,0,fx.op('return_deck',targets=[spell['id']]),Random(0))
    game._begin_round(s,0,Random(0))
    spell=fx.entity(s,spell['id']);s['players'][0]['hand'].remove(spell);fx.discard(s,spell)
    s=json.loads(json.dumps(s))
    caster=add(s,'c090',zone='rows')
    assert fx.menu(s,0,caster)==[]
    assert any('湖心仪师' in h['text'] and '整场已使用' in h['text']
               for h in card_status(s,0,fx.entity(s,spell['id']),'discard'))


def test_ritualist_unplayable_target_does_not_consume_its_use():
    s=empty();spell=add(s,'c111',zone='discard')
    fx.execute(s,0,fx.op('recast',targets=[spell['id']]))
    assert not s['players'][0]['instant_count']
    add(s,'c109',seat=1,zone='rows');caster=add(s,'c090')
    assert {o['card']['id'] for o in fx.menu(s,0,caster)}=={spell['id']}
    s=finish(play(s,caster,0))
    assert s['players'][0]['instant_count']==1
    assert fx.menu(s,0,fx.entity(s,caster['id']))==[]
