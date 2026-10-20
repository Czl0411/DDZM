"""V3 capacity, resource conservation, conditional deaths and reconnect contracts."""
from copy import deepcopy
import json
from pathlib import Path
from random import Random
import pytest

from dzmm_bot.core import mistrealm_v3_state as game
from dzmm_bot.core import mistrealm_v3_effects as fx
from dzmm_bot.core.mistrealm_v3_cards import CARDS, STARTER_DECKS, validate_deck


def started(a=0, b=2, seed=0):
    rng=Random(seed)
    s=game.new_state('a', STARTER_DECKS[a], 0)
    for seat,kind,payload in [(1,'join',dict(uid='b',deck=STARTER_DECKS[b])),
                              (0,'lock',{}),(1,'lock',{}),
                              (0,'mulligan',dict(cards=[])),(1,'mulligan',dict(cards=[]))]:
        s=game.apply_action(s,seat,kind,payload,0,rng)
    return s


def empty():
    s=started();s['turn']=0
    for p in s['players']:
        for zone in ('hand','deck','discard'):p[zone]=[]
    return s


def add(s,cid,seat=0,zone='hand',row=0,**values):
    s['entry_id']+=1
    c=dict(id=f"test:{s['entry_id']}",card=cid,owner=seat,entered=s['entry_id'],**values)
    (s['players'][seat]['rows'][row] if zone=='rows' else s['players'][seat][zone]).append(c)
    return c


def finish(s, pick=0):
    for _ in range(30):
        if not s['pending']:return s
        s=json.loads(json.dumps(s))  # Persist/reconnect during every selection.
        p=s['pending'];view=game.project(s,p['actor'])
        assert all('ops' not in o for o in view['pending']['options'])
        assert 'options' not in game.project(s,1-p['actor'])['pending']
        s=game.apply_action(s,p['actor'],'choose',{'option':p['options'][pick]['token']},0,Random(0))
    raise AssertionError('Unbounded effect chain')


def play(s,c,row=-1):
    return game.apply_action(s,s['turn'],'play',dict(card=c['id'],row=row),0,Random(0))


def test_catalogue_and_twenty_card_starters():
    assert len(CARDS)==120 and len(STARTER_DECKS)==10
    assert sum(c['type']=='leader' for c in CARDS.values())==10
    for d in STARTER_DECKS:
        assert sum(validate_deck(d['faction'],d['leader'],d['counts'])['counts'].values())==20
    bad=deepcopy(STARTER_DECKS[0]);bad['counts']['c101']=10
    with pytest.raises(ValueError):validate_deck(bad['faction'],bad['leader'],bad['counts'])


def test_published_catalogue_and_original_art_match_engine():
    root=Path(__file__).resolve().parents[2]/'gamefy/mistrealm/publish/v3'
    data=json.loads((root/'cards.json').read_text())
    assert data['cards']==CARDS and data['starters']==STARTER_DECKS
    assert all((root/c['art']).is_file() for c in CARDS.values())


def test_full_row_rejects_without_consuming_card_turn_or_version():
    s=empty()
    for _ in range(4):add(s,'c101',zone='rows')
    c=add(s,'c101');before=deepcopy(s)
    with pytest.raises(ValueError,match='已满'):play(s,c,0)
    assert s==before
    assert not any(m['action']=='play' for m in game.legal_moves(s,0))


def test_spy_uses_enemy_slot_draws_once_and_returns_to_owner():
    s=empty();spy=add(s,'c108')
    for _ in range(4):add(s,'c101',seat=1,zone='rows')
    with pytest.raises(ValueError):play(s,spy,0)
    s['players'][1]['rows'][0].clear()
    for _ in range(4):add(s,'c101',zone='deck')
    s=finish(play(s,spy,0));assert len(s['players'][0]['hand'])==2
    assert len(s['players'][1]['rows'][0])==1
    fx.remove_unit(s,spy['id']);s['turn']=0
    s=finish(play(s,fx.entity(s,spy['id']),0))
    assert len(s['players'][0]['hand'])==2
    fx.damage(s,0,[spy['id']],3);fx.settle(s)
    assert any(c['id']==spy['id'] for c in s['players'][0]['discard'])


def test_condition_loss_death_is_immediate_and_frees_slot():
    s=empty();hero=add(s,'c015',zone='rows',damage=6)
    assert game.score_rows(s,0)[0]==3
    c=add(s,'c101');s=finish(play(s,c,0))
    assert [x['id'] for x in s['players'][0]['rows'][0]]==[c['id']]
    assert fx.entity(s,hero['id']) in s['players'][0]['discard']


def test_bond_death_cascades_and_shield_is_not_score():
    s=empty();a=add(s,'c001',zone='rows',damage=4);b=add(s,'c001',zone='rows',damage=4,shield=2)
    assert game.score_rows(s,0)[0]==2
    fx.damage(s,1,[a['id']],1);fx.settle(s)
    assert not s['players'][0]['rows'][0] and len(s['players'][0]['discard'])==2
    c=add(s,'c101',zone='rows')
    fx.execute(s,0,fx.op('boost',targets=[c['id']],amount=20))
    fx.execute(s,0,fx.op('shield',targets=[c['id']],amount=20))
    fx.damage(s,1,[c['id']],5)
    assert (c['boost'],c['shield'],c['damage'])==(20,0,2)
    assert game.score_rows(s,0)[0]==20


def test_spell_slots_and_marks_do_not_follow_a_returned_card():
    s=empty();c=add(s,'c109',seat=1,zone='rows');spell=add(s,'c113')
    s=finish(play(s,spell));assert game.score_rows(s,1)[0]==3
    fx.remove_unit(s,c['id']);fx.put(s,1,fx.entity(s,c['id']),0)
    s['players'][1]['hand'].remove(fx.entity(s,c['id']))
    assert game.score_rows(s,1)[0]==5
    for _ in range(2):add(s,'c094',zone='spells')
    persistent=add(s,'c114');instant=add(s,'c111');s['turn']=0
    assert not fx.can_play(s,0,persistent,-1)
    assert fx.can_play(s,0,instant,-1)
    s=finish(play(s,instant))
    assert len(s['players'][0]['spells'])==3 and not s['players'][0]['resolving']


def test_destroying_persistent_seal_restores_hero_condition():
    s=empty();c=add(s,'c015',zone='rows',row=1);add(s,'c120',seat=1,zone='spells',targets=[c['id']])
    assert game.score_rows(s,0)[1]==3
    spell=add(s,'c101');s=finish(play(s,spell,0))
    assert game.score_rows(s,0)[1]==9
    assert not s['players'][1]['spells']


def test_muster_partial_fill_no_hand_pull_or_recursive_deployment():
    s=empty()
    for _ in range(2):add(s,'c101',zone='rows')
    c=add(s,'c061');hand=add(s,'c062');add(s,'c062',zone='deck');add(s,'c063',zone='deck')
    s=finish(play(s,c,0))
    assert len(s['players'][0]['rows'][0])==4
    assert len(s['players'][0]['deck'])==1
    assert s['players'][0]['hand']==[hand]
    assert len(s['players'][0]['summoned'])==1


def test_revive_excludes_spies_and_heroes_and_never_redeploys():
    s=empty();c=add(s,'c105');revived=add(s,'c026',zone='discard')
    add(s,'c108',zone='discard');add(s,'c015',zone='discard');add(s,'c101',zone='deck')
    s=play(s,c,1)
    assert {o['card']['id'] for o in s['pending']['options']}=={revived['id']}
    s=finish(s);assert not s['players'][0]['hand'] and len(s['players'][0]['deck'])==1
    fx.damage(s,1,[revived['id']],3);fx.settle(s)
    assert not fx.revive_options(s,0)


def test_death_choice_of_passed_opponent_resumes_original_actor():
    s=empty();add(s,'c071',seat=1,zone='rows',damage=1);add(s,'c101',seat=1,zone='rows')
    s['players'][1]['passed']=True;spell=add(s,'c111')
    s=play(s,spell);s=game.apply_action(s,0,'choose',{'option':'0'},0)
    assert s['pending']['actor']==1
    s=finish(s)
    assert s['turn']==0 and s['players'][1]['rows'][0][0]['boost']==3


def test_leader_moves_two_different_units_but_counts_one_action():
    s=empty();s['players'][0]['leader']='c059'
    a=add(s,'c101',zone='rows');b=add(s,'c101',zone='rows')
    s=game.apply_action(s,0,'leader',{},0)
    s=game.apply_action(s,0,'choose',{'option':'0'},0)
    assert all(o.get('card',{}).get('id')!=a['id'] for o in s['pending']['options'])
    s=finish(s)
    assert len(s['players'][0]['moved_actions'])==1
    assert fx.entity(s,a['id'])['boost']==fx.entity(s,b['id'])['boost']==2


def test_opening_and_round_draw_cleanup_do_not_trigger_death():
    s=started();assert all(len(p['hand'])==7 for p in s['players'])
    add(s,'c067',zone='rows');add(s,'c014',zone='spells')
    for _ in range(2):s=game.apply_action(s,s['turn'],'pass',{},0)
    assert s['phase']=='round_result'
    s=game.advance(s,5000,Random(0))
    assert s['round']==2 and all(len(p['hand'])==9 for p in s['players'])
    assert not s['players'][0]['spells'] and not s['players'][0]['dead_normal']


def test_damage_death_does_not_trigger_sacrifice_sanctuary():
    s=empty();hurt=add(s,'c109',zone='rows',damage=2)
    add(s,'c074',zone='spells')['row']=0
    add(s,'c054',seat=1,zone='spells')['row']=1
    add(s,'c113',seat=1,zone='spells',targets=[])
    # A previously hurt mover enters the trapped row with 1 remaining strength.
    victim=add(s,'c109',zone='rows',row=2,damage=4)
    fx.start_action(s,0)
    fx.execute(s,0,fx.op('move',targets=[victim['id']],row=1))
    s['work']=[fx.op('end_triggers',seat=0)];fx.drain(s)
    assert fx.entity(s,victim['id']) in s['players'][0]['discard']
    assert fx.entity(s,hurt['id'])['damage']==2
    assert fx.entity(s,hurt['id']).get('boost',0)==0


def test_every_card_can_resolve_on_a_populated_board():
    for cid,d in CARDS.items():
        s=empty();s['players'][0].update(instant_count=2,spell_count=2)
        for side in (0,1):
            for row in range(3):add(s,'c101',side,'rows',row,damage=1,boost=3)
            add(s,'c094',side,'spells');add(s,'c002',side,'discard')
            add(s,'c111',side,'discard');add(s,'c101',side,'hand')
            for group in ('c045','c046','c048','c061','c062','c064','c065','c026'):
                add(s,group,side,'deck')
        add(s,'c015',zone='rows',row=0)
        if d['type']=='leader':
            s['players'][0]['leader']=cid
            if fx.can_lead(s,0):s=finish(game.apply_action(s,0,'leader',{},0))
        else:
            c=add(s,cid);row=d['rows'][0] if d['type']=='unit' else -1
            assert fx.can_play(s,0,c,row),cid
            s=finish(play(s,c,row))
        assert not s['pending'] and not s['work'],cid
        assert all(len(row)<=4 for p in s['players'] for row in p['rows']),cid


@pytest.mark.parametrize('seed', range(3))
def test_all_starter_pairings_finish_and_conserve_every_entity(seed):
    for a in range(10):
        for b in range(a,10):
            s=started(a,b,seed);rng=Random(seed+a*10+b)
            for step in range(200):
                cards=[c for p in s['players'] for zone in ('hand','deck','discard','spells','resolving') for c in p[zone]]
                cards += [c for p in s['players'] for row in p['rows'] for c in row]
                assert len(cards)==len({c['id'] for c in cards})==40
                assert all(len(row)<=4 for p in s['players'] for row in p['rows'])
                assert all(len(p['spells'])<=3 for p in s['players'])
                if s['phase']=='finished':break
                if s['phase']=='round_result':s=game.advance(s,s['deadline_ms'],rng);continue
                seat=s['pending']['actor'] if s['pending'] else s['turn']
                moves=[m for m in game.legal_moves(s,seat) if m['action']!='concede']
                # Mixed pacing, sometimes saving cards for later rounds.
                active=[m for m in moves if m['action']!='pass']
                move=rng.choice(active if active and rng.random()<0.92 else moves)
                s=game.apply_action(s,seat,move['action'],move['payload'],step,rng)
            assert s['phase']=='finished',(a,b,seed)
            assert 1<=len(s['history'])<=3


@pytest.mark.parametrize('cid', ['c013','c100'])
def test_boost_three_draw_one_does_not_require_damage_or_a_hero(cid):
    s=empty();target=add(s,'c101',zone='rows');drawn=add(s,'c007',zone='deck')
    if cid=='c100':
        s['players'][0]['leader']=cid;s=game.apply_action(s,0,'leader',{},0)
    else:s=play(s,add(s,cid))
    s=finish(s)
    assert fx.entity(s,target['id'])['boost']==3
    assert [c['id'] for c in s['players'][0]['hand']]==[drawn['id']]


@pytest.mark.parametrize('cid,row', [('c069',0),('c112',-1)])
def test_sacrifice_draws_two_and_triggers_sanctuary_only_for_survivors(cid,row):
    s=empty();victim=add(s,'c001',zone='rows');survivor=add(s,'c101',zone='rows')
    add(s,'c074',zone='spells',row=0)['row']=0
    for _ in range(3):add(s,'c101',zone='deck')
    spell=add(s,cid);s=finish(play(s,spell,row))
    assert fx.entity(s,victim['id']) in s['players'][0]['discard']
    assert fx.entity(s,survivor['id'])['boost']==2
    assert len(s['players'][0]['hand'])==2
    assert len(s['players'][0]['deck'])==1
    assert not s['pending']


def test_ice_medic_revives_four_or_less_and_deploys_after_reconnect():
    s=empty();revived=add(s,'c007',zone='discard');add(s,'c052',zone='discard')
    forbidden=[add(s,cid,zone='discard') for cid in ('c109','c015','c108')]
    foe=add(s,'c109',seat=1,zone='rows',row=1)
    s=play(s,add(s,'c051'),1)
    assert {o['card']['card'] for o in s['pending']['options']}=={'c007','c052'}
    s=finish(s)
    assert fx.entity(s,foe['id'])['damage']==3
    assert fx.location(s,revived['id'])
    assert all(fx.entity(s,c['id']) in s['players'][0]['discard'] for c in forbidden)
    fx.damage(s,1,[revived['id']],10);fx.settle(s)
    assert all(o['card']['id']!=revived['id'] for o in fx.revive_options(s,0,4,True))


def test_draw_two_spell_and_observer_draw_two_discard_one():
    for cid,row,expected in [('c093',-1,2),('c009',1,1)]:
        s=empty()
        for _ in range(4):add(s,'c101',zone='deck')
        s=finish(play(s,add(s,cid),row))
        assert len(s['players'][0]['hand'])==expected
        assert len(s['players'][0]['deck'])==2


def test_crown_draw_no_longer_forces_discard():
    for cid,row in [('c006',0)]:
        s=empty();add(s,'c101',zone='rows',row=row);add(s,'c101',zone='rows',row=row)
        s['players'][0]['spell_count']=1;drawn=add(s,'c007',zone='deck')
        s=finish(play(s,add(s,cid),row))
        assert s['players'][0]['hand']==[drawn]
        assert not s['players'][0]['discard']


def test_sunken_echo_boosts_lowest_power_instead_of_healing():
    s=empty();high=add(s,'c109',zone='rows');low=add(s,'c001',zone='rows',row=1,damage=1)
    add(s,'c094',zone='spells')
    for _ in range(6):add(s,'c109',zone='deck')
    s=finish(play(s,add(s,'c093')))
    assert fx.entity(s,low['id'])['boost']==3 and fx.entity(s,low['id'])['damage']==1
    assert fx.entity(s,high['id']).get('boost',0)==0
    # Both have 5 power now; the earlier entrant wins the tie.
    add(s,'c101',zone='discard');s['turn']=0;s=finish(play(s,add(s,'c116')))
    assert fx.entity(s,high['id'])['boost']==3
    add(s,'c101',zone='discard');s['turn']=0;s=finish(play(s,add(s,'c116')))
    assert fx.entity(s,low['id'])['boost']==3
    assert fx.entity(s,high['id'])['boost']==3


def test_brood_leader_recycles_three_real_entities_and_draws_once():
    s=empty();s['players'][0]['leader']='c079'
    ids={add(s,cid,zone='discard')['id'] for cid in ('c007','c015','c093','c108')}
    s=finish(game.apply_action(s,0,'leader',{},0,Random(4)))
    p=s['players'][0]
    assert (len(p['discard']),len(p['deck']),len(p['hand']))==(1,2,1)
    assert {c['id'] for zone in ('discard','deck','hand') for c in p[zone]}==ids
    assert p['leader_used']


def test_old_road_cannon_sacrifices_and_boosts_without_passive():
    s=empty();victim=add(s,'c001',zone='rows');cannon=add(s,'c104');add(s,'c094',seat=1,zone='spells')
    s=finish(play(s,cannon,2))
    assert fx.entity(s,victim['id']) in s['players'][0]['discard']
    assert fx.entity(s,cannon['id'])['boost']==2
    assert game.score_rows(s,0)[2]==5


def test_army_protection_gives_three_targets_two_conditional_power_each():
    s=empty();allies=[add(s,'c101',zone='rows') for _ in range(3)]
    s=play(s,add(s,'c118'))
    token=next(o['token'] for o in s['pending']['options'] if len(o['ops'][0]['targets'])==3)
    s=game.apply_action(s,0,'choose',{'option':token},0)
    assert game.score_rows(s,0)[0]==12
    assert all(fx.entity(s,c['id']).get('boost',0)==0 for c in allies)


def test_iron_rain_hits_two_distinct_units_for_two_damage():
    s=empty();foes=[add(s,'c109',seat=1,zone='rows') for _ in range(2)]
    s=play(s,add(s,'c115'))
    token=next(o['token'] for o in s['pending']['options'] if len(o['ops'][0]['targets'])==2)
    s=game.apply_action(s,0,'choose',{'option':token},0)
    assert all(fx.entity(s,c['id'])['damage']==2 for c in foes)


def test_global_aoe_kills_both_sides_simultaneously_and_runs_death_draws():
    s=empty();a=add(s,'c067',zone='rows');b=add(s,'c067',seat=1,zone='rows')
    for seat in (0,1):add(s,'c101',seat=seat,zone='deck')
    s=finish(play(s,add(s,'c119')))
    assert not s['players'][0]['rows'][0] and not s['players'][1]['rows'][0]
    for seat,c in enumerate((a,b)):
        assert fx.entity(s,c['id']) in s['players'][seat]['discard']
        assert len(s['players'][seat]['hand'])==1


def test_trap_hits_for_two_and_stops_after_three_across_bounce():
    s=empty();spell=add(s,'c054',seat=1,zone='spells');spell['row']=1
    for i in range(4):
        c=add(s,'c109',zone='rows',row=0);fx.start_action(s,0)
        fx.execute(s,0,fx.op('move',targets=[c['id']],row=1))
        s['work']=[fx.op('end_triggers',seat=0)];fx.drain(s)
        assert c.get('damage',0)==(2 if i<3 else 0)
        fx.remove_unit(s,c['id'])
    assert spell['trap_used']==3


def test_morning_mask_takes_chosen_top_card_and_discards_the_other():
    s=empty();bottom=add(s,'c101',zone='deck');chosen=add(s,'c007',zone='deck');other=add(s,'c008',zone='deck')
    s=finish(play(s,add(s,'c084'),0))
    assert [c['id'] for c in s['players'][0]['hand']]==[chosen['id']]
    assert [c['id'] for c in s['players'][0]['deck']]==[bottom['id']]
    assert [c['id'] for c in s['players'][0]['discard']]==[other['id']]


def test_leaf_no_longer_draws_after_friendly_hero_death():
    s=empty();hero=add(s,'c015',zone='rows');fx.damage(s,1,[hero['id']],20);fx.settle(s)
    add(s,'c101',zone='deck');s=finish(play(s,add(s,'c070'),1))
    assert not s['players'][0]['hand'] and len(s['players'][0]['deck'])==1


def test_wind_priest_can_move_either_side_but_never_into_full_row():
    s=empty();mediator=add(s,'c052');foe=add(s,'c101',seat=1,zone='rows')
    for _ in range(4):add(s,'c101',seat=1,zone='rows',row=1)
    s=play(s,mediator,1)
    options=s['pending']['options']
    assert any(o.get('card',{}).get('id')==mediator['id'] for o in options)
    assert not any(o.get('card',{}).get('id')==foe['id'] and o['row']==1 for o in options)
    choice=next(o for o in options if o.get('card',{}).get('id')==foe['id'])
    s=game.apply_action(s,0,'choose',{'option':choice['token']},0)
    assert fx.location(s,foe['id'])[:2]==(1,2)


def test_persistent_seal_debuff_can_kill_two_power_unit():
    s=empty();target=add(s,'c026',seat=1,zone='rows')
    s=finish(play(s,add(s,'c120')))
    assert fx.entity(s,target['id']) in s['players'][1]['discard']
    assert not s['players'][0]['spells'][0]['targets']


def test_young_walker_no_longer_grows_or_draws_when_later_instants_resolve():
    s=empty();walker=add(s,'c089',zone='rows',row=1)
    for _ in range(6):add(s,'c101',zone='deck')
    for i in range(3):
        add(s,'c101',zone='rows',row=2);s['turn']=0;s=finish(play(s,add(s,'c112')))
        assert not fx.entity(s,walker['id']).get('boost')
        assert len(s['players'][0]['hand'])==2*(i+1)


@pytest.mark.parametrize('leader,cid', [('c040','c007'),('c099','c111')])
def test_resource_leaders_recover_one_and_draw_one(leader,cid):
    s=empty();s['players'][0]['leader']=leader
    recovered=add(s,cid,zone='discard');drawn=add(s,'c101',zone='deck')
    s=finish(game.apply_action(s,0,'leader',{},0))
    assert {c['id'] for c in s['players'][0]['hand']}=={recovered['id'],drawn['id']}
    assert not s['players'][0]['discard']


def test_current_card_text_has_no_heal_or_shield_and_heroes_are_five_to_six():
    assert all('治疗' not in c['text'] and '护盾' not in c['text'] for c in CARDS.values())
    assert all(5<=c['power']<=6 for c in CARDS.values() if c['hero'])
    assert all(c['power']==(2 if cid in ('c064','c065','c066') else 3) for cid,c in CARDS.items() if c['type']=='unit' and not c['hero'] and ('bond' in c['abilities'] or 'muster' in c['abilities']))


def test_balance_release_keeps_original_room_engine_and_starts_new_revision():
    from dzmm_bot.core.mistrealm_repository import _engine
    from dzmm_bot.core.mistrealm_v3_original import mistrealm_v3_state as original
    from dzmm_bot.core.mistrealm_v3_original.mistrealm_v3_cards import CARDS as old_cards
    s=started()
    assert s['balance_revision']==2 and game.project(s,0)['balance_revision']==2
    assert _engine(s) is game
    from dzmm_bot.core.mistrealm_v3_r1 import mistrealm_v3_state as r1
    previous=deepcopy(s);previous['balance_revision']=1
    assert _engine(previous) is r1
    assert r1.definition(dict(card='c101'))['power']==5
    old=deepcopy(s);old.pop('balance_revision')
    assert _engine(old) is original
    assert _engine({'rules_version':3}) is game
    assert old_cards['c001']['power']==4 and CARDS['c001']['power']==3
    assert '护盾' in old_cards['c059']['text'] and '战力＋2' in CARDS['c059']['text']
    before=deepcopy(old)
    original.project(old,0)
    assert old==before


def test_original_story_uses_original_catalogue_and_engine():
    from dzmm_bot.core import mistrealm_story as story
    from dzmm_bot.core.mistrealm_v3_original import mistrealm_v3_state as original
    s=started();s.pop('balance_revision');s.update(mode='story',story={'chapter':1},turn=1)
    for p in s['players']:
        p['hand']=[];p['rows']=[[],[],[]]
    card=add(s,'c002',seat=1)
    result=story.drive(s,0,Random(0))
    unit=result['players'][1]['rows'][0][0]
    assert unit['id']==card['id'] and unit['shield']==1
    assert unit.get('boost',0)==0 and 'balance_revision' not in result


def test_match_log_survives_rounds_and_reconnect_without_private_cards():
    s=empty();c=add(s,'c101')
    s=finish(play(s,c,0))
    played=next(e for e in s['action_log'] if e['kind']=='play')
    assert played['card']=='c101' and played['seat']==0 and played['round']==1
    for seat in (1,0):s=game.apply_action(s,seat,'pass',{},0,Random(0))
    assert s['action_log'][-1]['kind']=='round_end'
    s=game.advance(s,5000,Random(0))
    assert s['round']==2 and s['action_log'][-1]['kind']=='round_start'
    log=json.loads(json.dumps(s))['action_log']
    assert played in log
    assert [e['id'] for e in log]==list(range(1,len(log)+1))
    assert game.project(s,0)['action_log']==game.project(s,1)['action_log']==log
    assert all(set(e)=={'id','round','kind','seat','card','text','details','effects'} for e in log)


def test_match_log_records_leader_once_and_does_not_reveal_draws():
    s=empty();s['players'][0]['leader']='c019'
    # Use the first legal leader for the supplied board, including pending choices.
    add(s,'c101',zone='rows');add(s,'c102',zone='deck');add(s,'c103',zone='deck')
    for cid,c in CARDS.items():
        if c['type']=='leader':
            s['players'][0]['leader']=cid
            if fx.can_lead(s,0):break
    s=game.apply_action(s,0,'leader',{},0,Random(0));s=finish(s)
    assert len([e for e in s['action_log'] if e['kind']=='leader'])==1
    assert all(e['card'] not in ('c102','c103') for e in s['action_log'])
    before=deepcopy(s['action_log'])
    with pytest.raises(ValueError):game.apply_action(s,0,'play',dict(card='missing',row=0),0,Random(0))
    assert s['action_log']==before


def test_match_log_old_rooms_and_rematches():
    s=empty();s.pop('action_log')
    s=game.apply_action(s,0,'pass',{},0,Random(0))
    assert s['action_log'][0]['kind']=='pass'
    s=game.apply_action(s,1,'concede',{},0,Random(0))
    for seat in (0,1):s=game.apply_action(s,seat,'rematch',{},0,Random(0))
    assert s['phase']=='waiting' and s['action_log']==[]


def test_public_match_log_never_contains_spy_draw_results():
    s=empty();spy=add(s,'c108')
    add(s,'c102',zone='deck');add(s,'c103',zone='deck')
    s=finish(play(s,spy,0))
    assert len(s['players'][0]['hand'])==2
    public=json.dumps(game.project(s,1)['action_log'])
    assert 'c108' in public and 'c102' not in public and 'c103' not in public
    assert CARDS['c102']['name'] not in public and CARDS['c103']['name'] not in public


def test_animation_frames_preserve_public_intermediate_boards_only():
    s=empty();a=add(s,'c101');b=add(s,'c101',seat=1)
    s=finish(play(s,a,0));first=game.project(s,0)['action_frames'][-1]
    assert first['landing']==dict(seat=0,row=0,slot=0)
    assert first['played']==a['id']
    assert len(first['state']['players'][0]['rows'][0])==1
    assert not first['state']['players'][1]['rows'][0]
    s=finish(play(s,b,0));second=game.project(s,0)['action_frames'][-1]
    assert len(second['state']['players'][1]['rows'][0])==1
    assert not first['state']['players'][1]['rows'][0]
    for frame in game.project(s,0)['action_frames']:
        assert 'action_frames' not in frame['state']
        for p in frame['state']['players']:
            assert 'hand' not in p and 'deck' not in p and 'selection' not in p
    assert game.project(s,0)['action_frames']==game.project(s,1)['action_frames']


def test_spy_landing_and_private_draws_in_animation_frames():
    s=empty();spy=add(s,'c108');hidden=add(s,'c102',zone='deck')
    s=finish(play(s,spy,0));frame=game.project(s,0)['action_frames'][-1]
    assert frame['landing']==dict(seat=1,row=0,slot=0)
    assert hidden['id'] not in json.dumps(s['action_frames'])
    assert frame['version']==s['version']


def test_persistent_spell_animation_lands_in_its_own_spell_slot():
    s=empty();add(s,'c101',seat=1,zone='rows');spell=add(s,'c113')
    s=play(s,spell)
    frame=game.project(s,0)['action_frames'][-1]
    assert frame['landing']==dict(seat=0,row=-1,slot=0)
    assert frame['state']['players'][0]['spells'][0]['id']==spell['id']
    assert 'pending' not in frame['state']
