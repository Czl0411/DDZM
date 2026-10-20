"""Beast card updates: death, sacrifice, repeated actions and summon accounting."""
from random import Random
import pytest
from dzmm_bot.core import mistrealm_v3_state as game, mistrealm_v3_effects as fx
from dzmm_bot.core.mistrealm_v3_scoring import row_power_details
from tests.core.test_mistrealm_v3 import empty,add,play,finish


def strength(s,c):
    side,row,_=fx.location(s,c['id'])
    return row_power_details(s,side,row)[s['players'][side]['rows'][row].index(fx.entity(s,c['id']))]['power']


def test_lurker_has_three_power_and_death_boosts_survivor_by_three():
    s=empty();lurker=add(s,'c071',zone='rows');ally=add(s,'c101',zone='rows')
    assert strength(s,lurker)==3
    fx.damage(s,1,[lurker['id']],3);fx.settle(s);fx.drain(s)
    s=finish(s)
    assert fx.entity(s,ally['id'])['boost']==3
    assert fx.entity(s,lurker['id']) in s['players'][0]['discard']


def test_bone_sacrifice_deals_three_to_enemy_board_and_preserves_death_trigger():
    s=empty();victim=add(s,'c071',zone='rows');ally=add(s,'c101',zone='rows')
    enemies=[add(s,'c015',seat=1,zone='rows',row=r) for r in range(3)]
    ordinary=add(s,'c101',seat=1,zone='rows')
    s=finish(play(s,add(s,'c073')))
    assert fx.entity(s,victim['id']) in s['players'][0]['discard']
    assert fx.entity(s,ally['id'])['boost']==3
    assert all(fx.entity(s,c['id'])['damage']==3 for c in enemies)
    assert fx.entity(s,ordinary['id']) in s['players'][1]['discard']
    assert not fx.entity(s,ally['id']).get('damage')


def test_lizard_counts_more_than_four_distinct_normal_deaths():
    s=empty();hero=add(s,'c075',zone='rows')
    for _ in range(6):
        victim=add(s,'c101',zone='rows',row=1)
        fx.damage(s,1,[victim['id']],2);fx.settle(s);fx.drain(s)
    assert strength(s,hero)==11
    s['players'][0]['dead_normal'].append(victim['id'])
    assert strength(s,hero)==11
    hero['sealed']=True;assert strength(s,hero)==5


@pytest.mark.parametrize('count',[0,1,2,3])
def test_thorn_heart_deployment_returns_up_to_three_friendly_normals(count):
    s=empty();hero=add(s,'c077')
    eligible=[add(s,cid,zone='discard') for cid in ('c101','c101','c043','c108')]
    excluded=[add(s,'c075',zone='discard'),add(s,'c073',zone='discard'),add(s,'c101',seat=1,zone='discard')]
    assert not fx.can_play(s,0,hero,0) and fx.can_play(s,0,hero,2)
    s=play(s,hero,2)
    options=s['pending']['options']
    assert len(options)==15  # All groups of 1–3 among four entities, plus skip.
    for choice in options:
        returned=[op['targets'][0] for op in choice['ops'] if op['kind']=='return_deck']
        assert len(returned)<=3 and set(returned)<={c['id'] for c in eligible}
    pick=next(i for i,o in enumerate(options) if sum(op['kind']=='return_deck' for op in o['ops'])==count)
    selected={op['targets'][0] for op in options[pick]['ops'] if op['kind']=='return_deck'}
    s=finish(s,pick)
    assert {c['id'] for c in s['players'][0]['deck']}==selected
    assert strength(s,hero)==5+count and not s['players'][0]['hand']
    assert all(fx.entity(s,c['id']) in s['players'][c['owner']]['discard'] for c in excluded)
    assert len(s['players'][0]['discard'])==6-count
    # Subsequent summons do not supply the removed conditional bonus.
    unit=add(s,'c101',zone='deck')
    fx.execute(s,0,fx.op('summon',targets=[unit['id']],row=0));fx.drain(s)
    assert strength(s,hero)==5+count


def test_thorn_heart_empty_discard_and_sealed_deployment_do_not_recycle():
    s=empty();hero=add(s,'c077');s=play(s,hero,2)
    assert not s['pending'] and strength(s,hero)==5
    card=add(s,'c101',zone='discard')
    fx.entity(s,hero['id'])['sealed']=True
    fx.deployment(s,0,fx.entity(s,hero['id']));fx.drain(s)
    assert not s['pending'] and card in s['players'][0]['discard']


@pytest.mark.parametrize('cause',['damage','sacrifice','lost_bonus'])
def test_root_deployment_boosts_all_own_normals_and_death_does_not_repeat(cause):
    s=empty();allies=[add(s,'c101',zone='rows',row=r,boost=4) for r in range(3)]
    hero=add(s,'c056',zone='rows',row=1);enemy=add(s,'c101',seat=1,zone='rows')
    root=add(s,'c068');s=finish(play(s,root,0))
    assert strength(s,root)==3 and all(strength(s,c)==7 for c in allies)
    if cause=='damage':fx.damage(s,1,[root['id']],3)
    elif cause=='sacrifice':fx.execute(s,0,fx.op('sacrifice',targets=[root['id']]))
    else:
        fx.entity(s,root['id'])['damage']=3
        spell=add(s,'c118',zone='spells',targets=[root['id']])
        assert strength(s,root)==2
        fx.execute(s,0,fx.op('destroy_spell',targets=[spell['id']]))
    fx.settle(s);fx.drain(s)
    assert fx.entity(s,root['id']) in s['players'][0]['discard']
    assert all(strength(s,c)==7 for c in allies)
    assert not fx.entity(s,hero['id']).get('uncapped_boost') and strength(s,enemy)==2
    fx.settle(s);fx.drain(s)
    assert all(strength(s,c)==7 for c in allies)


@pytest.mark.parametrize('cause',['sealed_death','bounce','round_cleanup'])
def test_root_does_not_trigger_when_sealed_or_leaving_without_death(cause):
    s=empty();root=add(s,'c068',zone='rows');ally=add(s,'c101',zone='rows')
    if cause=='sealed_death':
        root['sealed']=True;fx.damage(s,1,[root['id']],2);fx.settle(s);fx.drain(s)
    elif cause=='bounce':fx.remove_unit(s,root['id'])
    else:game._begin_round(s,0,Random(0))
    assert not fx.entity(s,ally['id']).get('uncapped_boost')


def test_root_does_not_rescue_units_that_die_in_the_same_batch():
    s=empty();root=add(s,'c068',zone='rows');victim=add(s,'c101',zone='rows');survivor=add(s,'c081',zone='rows',row=1)
    fx.damage(s,1,[root['id'],victim['id']],2);fx.settle(s);fx.drain(s)
    assert fx.location(s,victim['id']) is None
    assert not fx.entity(s,survivor['id']).get('uncapped_boost')


@pytest.mark.parametrize('row',[0,1,2])
def test_moss_deployment_damages_both_sides_of_chosen_row_including_self(row):
    s=empty();allies=[add(s,'c081',zone='rows',row=r) for r in range(3)]
    enemies=[add(s,'c015',seat=1,zone='rows',row=r) for r in range(3)]
    moss=add(s,'c072')
    assert [fx.can_play(s,0,moss,r) for r in range(3)]==[False,False,True]
    s=play(s,moss,2)
    assert len(s['pending']['options'])==3
    s=finish(s,row)
    for r in range(3):
        assert fx.entity(s,allies[r]['id']).get('damage',0)==(2 if r==row else 0)
        assert fx.entity(s,enemies[r]['id']).get('damage',0)==(2 if r==row else 0)
    assert strength(s,moss)==(1 if row==2 else 3)
    s['turn']=0;s=play(s,add(s,'c081'),0)
    assert strength(s,moss)==(1 if row==2 else 3)
    assert all(not fx.entity(s,c['id']).get('boost') for c in allies)


def test_moss_sealed_deployment_does_nothing_and_empty_row_can_be_selected():
    s=empty();moss=add(s,'c072');s=play(s,moss,2);s=finish(s,0)
    assert strength(s,moss)==3
    fx.entity(s,moss['id'])['sealed']=True
    fx.deployment(s,0,fx.entity(s,moss['id']));fx.drain(s)
    assert not s['pending'] and strength(s,moss)==3


def test_devour_requires_two_other_normals_and_does_not_absorb_strength():
    s=empty();beast=add(s,'c076');a=add(s,'c001',zone='rows',boost=4,damage=1)
    add(s,'c015',zone='rows')
    assert not fx.can_play(s,0,beast,0)
    b=add(s,'c001',zone='rows',boost=2)
    assert strength(s,a)==8 and strength(s,b)==7
    assert fx.can_play(s,0,beast,0)
    s=play(s,beast,0)
    assert len(s['pending']['options'])==1
    s=finish(s) # Serializes pending effects before completing the choice.
    assert strength(s,beast)==11
    assert {c['id'] for c in s['players'][0]['discard']}=={a['id'],b['id']}
    assert len(s['players'][0]['dead_normal'])==2
    fx.execute(s,0,fx.op('boost',targets=[beast['id']],amount=3));assert strength(s,beast)==14
    fx.entity(s,beast['id'])['sealed']=True;assert strength(s,beast)==14
    fx.remove_unit(s,beast['id']);assert not fx.entity(s,beast['id']).get('uncapped_boost')


def test_devour_triggers_both_deaths_and_sanctuary():
    s=empty();a=add(s,'c071',zone='rows',row=1);b=add(s,'c064',zone='rows',row=2)
    beast=add(s,'c076');spell=add(s,'c074',zone='spells');spell['row']=0
    s=finish(play(s,beast,0))
    # Two friendly sacrifices add 6, sanctuary adds 4 and the lurker adds 3.
    assert strength(s,beast)==18
    assert fx.entity(s,a['id']) in s['players'][0]['discard']
    assert fx.entity(s,b['id']) in s['players'][0]['deck']


def test_uncapped_strength_cannot_prevent_sacrifice_and_is_cleared_on_death():
    s=empty();victim=add(s,'c101',zone='rows',uncapped_boost=2000)
    fx.execute(s,0,fx.op('sacrifice',targets=[victim['id']]))
    fx.settle(s);fx.drain(s)
    assert fx.entity(s,victim['id']) in s['players'][0]['discard']
    assert not victim.get('uncapped_boost')


def test_lizard_counts_both_sides_heroes_and_repeated_deaths_but_not_bounces():
    import json
    s=empty();lizard=add(s,'c075',zone='rows')
    ally=add(s,'c101',zone='rows',row=1);foe=add(s,'c101',seat=1,zone='rows')
    hero=add(s,'c015',seat=1,zone='rows',row=2)
    for c in (ally,foe,hero):
        fx.remove_unit(s,c['id'],True);fx.settle(s);fx.drain(s)
    assert strength(s,lizard)==8
    s=json.loads(json.dumps(s))
    fx.execute(s,1,fx.op('revive',targets=[foe['id']],row=1))
    fx.damage(s,0,[foe['id']],2);fx.settle(s);fx.drain(s)
    assert strength(s,lizard)==9
    assert s['players'][1]['death_counts'][foe['id']]==2
    other=add(s,'c101',seat=1,zone='rows');fx.remove_unit(s,other['id'])
    assert strength(s,lizard)==9
    fx.entity(s,lizard['id'])['sealed']=True;assert strength(s,lizard)==5
    fx.entity(s,lizard['id']).pop('sealed')
    # Its own earlier death never contributes if the same entity returns to play.
    fx.remove_unit(s,lizard['id'],True);fx.settle(s);fx.drain(s)
    fx.execute(s,0,fx.op('revive',targets=[lizard['id']],row=0))
    assert strength(s,lizard)==9
    game._begin_round(s,0,Random(0))
    assert all(p['death_counts']=={} for p in s['players'])
    fx.execute(s,0,fx.op('revive',targets=[lizard['id']],row=0))
    assert strength(s,lizard)==5


def test_bone_sacrifice_requires_normal_ally_and_guard_intercepts_board_damage():
    s=empty();hero=add(s,'c015',zone='rows');spell=add(s,'c073')
    taunt=add(s,'c102',seat=1,zone='rows');foe=add(s,'c101',seat=1,zone='rows',row=1)
    assert not fx.can_play(s,0,spell,-1)
    ally=add(s,'c101',zone='rows',row=1)
    options=fx.menu(s,0,spell)
    assert len(options)==1 and options[0]['card']['id']==ally['id']
    assert options[0]['ops'][1]['targets']==[taunt['id'],foe['id']]
    s=finish(play(s,spell))
    assert fx.entity(s,ally['id']) in s['players'][0]['discard']
    assert fx.entity(s,taunt['id']) in s['players'][1]['discard']
    assert fx.location(s,foe['id']) and not fx.entity(s,foe['id']).get('damage')
    assert not fx.entity(s,hero['id']).get('damage')


def test_root_deploy_repeat_revive_and_summon_follow_deployment_rules():
    s=empty();ally=add(s,'c101',zone='rows',row=1);root=add(s,'c068')
    s=finish(play(s,root,0));assert strength(s,ally)==3 and strength(s,root)==3
    # A sealed root cannot repeat its deployment.
    fx.entity(s,root['id'])['sealed']=True
    fx.deployment(s,0,fx.entity(s,root['id']));fx.drain(s)
    assert strength(s,ally)==3
    fx.entity(s,root['id']).pop('sealed')
    fx.deployment(s,0,fx.entity(s,root['id']));fx.drain(s)
    assert strength(s,ally)==4 and strength(s,root)==4
    fx.remove_unit(s,root['id'],True);fx.settle(s);fx.drain(s)
    assert strength(s,ally)==4
    s['turn']=0;s=finish(play(s,add(s,'c051'),1))
    assert strength(s,ally)==5 and strength(s,root)==3
    # Ordinary summoning does not run deployment.
    another=add(s,'c068',zone='deck')
    fx.execute(s,0,fx.op('summon',targets=[another['id']],row=0));fx.drain(s)
    assert strength(s,ally)==5 and strength(s,another)==2


@pytest.mark.parametrize('allies',[0,1,2])
def test_devour_only_friendly_victims_grant_three_and_enemies_grant_nothing(allies):
    s=empty();beast=add(s,'c076')
    victims=[add(s,'c101',seat=0 if i<allies else 1,zone='rows',row=1,boost=i) for i in range(2)]
    add(s,'c015',seat=1,zone='rows')
    assert fx.can_play(s,0,beast,0)
    s=play(s,beast,0)
    assert len(s['pending']['options'])==1
    preview=game.project(s,0)['pending']
    assert '双方' in preview['prompt']
    s=finish(s)
    assert strength(s,beast)==5+3*allies
    for c in victims:assert fx.entity(s,c['id']) in s['players'][c['owner']]['discard']


def test_brood_mother_death_draw_once_per_entity_per_round_survives_reentry():
    import json
    from dzmm_bot.core.mistrealm_v3_hints import card_status
    s=empty();mother=add(s,'c067',zone='rows')
    for _ in range(8):add(s,'c101',zone='deck')
    fx.damage(s,1,[mother['id']],2);fx.settle(s);fx.drain(s)
    assert len(s['players'][0]['hand'])==2
    s=json.loads(json.dumps(s))
    c=fx.entity(s,mother['id'])
    assert card_status(s,0,c,'discard')[0]['text']=='阵亡抽牌：本小局已使用'
    fx.execute(s,0,fx.op('revive',targets=[c['id']],row=2));fx.drain(s)
    fx.execute(s,0,fx.op('sacrifice',targets=[c['id']]));fx.settle(s);fx.drain(s)
    assert len(s['players'][0]['hand'])==2
    # Another physical copy has its own allowance.
    other=add(s,'c067',zone='rows');fx.damage(s,1,[other['id']],2);fx.settle(s);fx.drain(s)
    assert len(s['players'][0]['hand'])==4
    game._begin_round(s,0,Random(0))
    assert card_status(s,0,c,'discard')[0]['text']=='阵亡抽牌：本小局剩余1次'
    before=len(s['players'][0]['hand'])
    fx.execute(s,0,fx.op('revive',targets=[c['id']],row=2));fx.drain(s)
    fx.damage(s,1,[c['id']],2);fx.settle(s);fx.drain(s)
    assert len(s['players'][0]['hand'])==before+2


def test_leaf_ranged_deployment_revives_low_power_unit_without_deployment_or_draw():
    s=empty();leaf=add(s,'c070',resource_used=True)
    target=add(s,'c068',zone='discard')
    add(s,'c081',zone='discard');add(s,'c015',zone='discard');add(s,'c108',zone='discard')
    add(s,'c101',zone='discard',revived_round=s['round'])
    add(s,'c101',seat=1,zone='discard');add(s,'c101',zone='deck')
    assert not fx.can_play(s,0,leaf,0) and fx.can_play(s,0,leaf,1)
    s=play(s,leaf,1)
    assert {o['card']['id'] for o in s['pending']['options']}=={target['id']}
    s=finish(s)
    assert strength(s,target)==2 and strength(s,leaf)==2
    assert fx.location(s,target['id'])[:2]==(0,0)
    assert not s['players'][0]['hand'] and len(s['players'][0]['deck'])==1
    # No old per-match resource limit remains; a later deployment can revive another entity.
    next_target=add(s,'c101',zone='discard')
    fx.deployment(s,0,fx.entity(s,leaf['id']));fx.drain(s)
    assert {o['card']['id'] for o in s['pending']['options']}=={next_target['id']}
    s=finish(s);assert fx.location(s,next_target['id'])


def test_leaf_cannot_revive_into_full_row_and_round_cleanup_does_not_draw():
    s=empty();leaf=add(s,'c070');add(s,'c068',zone='discard')
    for _ in range(4):add(s,'c101',zone='rows')
    s=play(s,leaf,1);assert not s['pending']
    mother=add(s,'c067',zone='rows',row=2)
    for _ in range(4):add(s,'c101',zone='deck')
    game._begin_round(s,0,Random(0))
    assert len(s['players'][0]['hand'])==2  # Round draw only, no death trigger.
    assert not mother.get('death_round')


def test_lurker_repeated_deaths_in_same_round_trigger_after_revive_and_replay():
    from dzmm_bot.core.mistrealm_v3_hints import card_status
    s=empty();lurker=add(s,'c071',zone='rows',death_round=s['round'])
    allies=[add(s,'c101',zone='rows',row=1) for _ in range(3)]
    assert not any('阵亡强化' in hint['text'] for hint in card_status(s,0,lurker,'rows'))
    for i in range(3):
        if i==1:
            fx.execute(s,0,fx.op('revive',targets=[lurker['id']],row=0));fx.drain(s)
        elif i==2:
            fx.execute(s,0,fx.op('recover',targets=[lurker['id']]))
            s['turn']=0;s=play(s,fx.entity(s,lurker['id']),0)
        if i==1:fx.execute(s,0,fx.op('sacrifice',targets=[lurker['id']]))
        else:fx.damage(s,1,[lurker['id']],3)
        fx.settle(s);fx.drain(s)
        assert s['pending'] and s['pending']['title']=='阵亡：选择强化目标'
        s=finish(s,i)  # Serialize the pending choice, then boost a fresh target.
        assert strength(s,allies[i])==5
        fx.settle(s);fx.drain(s)
        assert not s['pending']  # A resolved death is not repeated by another settlement.
    assert all(strength(s,c)==5 for c in allies)


@pytest.mark.parametrize('cause',['sealed','bounce','cleanup'])
def test_lurker_still_requires_unsealed_death(cause):
    s=empty();lurker=add(s,'c071',zone='rows');ally=add(s,'c101',zone='rows',row=1)
    if cause=='sealed':
        lurker['sealed']=True;fx.damage(s,1,[lurker['id']],3);fx.settle(s);fx.drain(s)
    elif cause=='bounce':fx.remove_unit(s,lurker['id'])
    else:game._begin_round(s,0,Random(0))
    assert not s['pending'] and not fx.entity(s,ally['id']).get('boost')
