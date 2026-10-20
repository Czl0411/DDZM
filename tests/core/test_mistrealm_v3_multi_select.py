from copy import deepcopy
import json
from dzmm_bot.core import mistrealm_v3_state as game, mistrealm_v3_effects as fx
from dzmm_bot.core.mistrealm_v3_cards import CARDS
from tests.core.test_mistrealm_v3 import empty,add,play,finish


def test_recycle_exposes_ten_individual_cards_not_the_hero_and_preserves_legal_sets():
    s=empty();hero=add(s,'c077')
    cards=[add(s,'c101',zone='discard') for _ in range(10)]
    s=play(s,hero,2);before=deepcopy(s)
    pending=game.project(s,0)['pending'];m=pending['multi_select']
    assert s==before
    assert m['minimum']==0 and m['maximum']==3 and not m['ordered']
    assert len(m['cards'])==10 and {c['id'] for c in m['cards']}=={c['id'] for c in cards}
    assert all(c['side']=='own' and c['zone']=='弃牌区' for c in m['cards'])
    assert all(hero['id'] not in o['select_ids'] and 'ops' not in o for o in pending['options'])
    ids=[c['id'] for c in cards[2:5]]
    option=next(o for o in pending['options'] if o['select_ids']==ids)
    s=game.apply_action(s,0,'choose',dict(option=option['token']),0)
    assert {c['id'] for c in s['players'][0]['deck']}==set(ids)
    assert fx.entity(s,hero['id'])['boost']==3
    assert 'options' not in (game.project(before,1)['pending'] or {})


def test_devour_multi_select_requires_two_and_preserves_both_sides():
    s=empty();hero=add(s,'c076');a=add(s,'c101',zone='rows');b=add(s,'c101',seat=1,zone='rows')
    s=play(s,hero,0);pending=game.project(s,0)['pending']
    assert pending['multi_select']['minimum']==pending['multi_select']['maximum']==2
    assert {c['side'] for c in pending['multi_select']['cards']}=={'own','enemy'}
    assert pending['options'][0]['select_ids']==[a['id'],b['id']]


def test_row_damage_and_exchange_keep_their_distinct_destination_semantics():
    s=empty();s=play(s,add(s,'c072'),2)
    assert 'multi_select' not in game.project(s,0)['pending']
    s=empty();add(s,'c101',zone='rows');s=play(s,add(s,'c050'),1)
    assert 'multi_select' not in game.project(s,0)['pending']


def test_same_row_spell_only_exposes_legal_sets_and_ordered_damage_retains_order():
    s=empty();a=add(s,'c081',seat=1,zone='rows');b=add(s,'c081',seat=1,zone='rows');c=add(s,'c081',seat=1,zone='rows',row=1)
    s=play(s,add(s,'c113'));p=game.project(s,0)['pending']
    assert p['multi_select']['maximum']==2
    assert not any(a['id'] in o['select_ids'] and c['id'] in o['select_ids'] for o in p['options'])
    s=empty();a=add(s,'c081',seat=1,zone='rows');b=add(s,'c081',seat=1,zone='rows')
    s=play(s,add(s,'c115'));p=game.project(s,0)['pending']
    assert p['multi_select']['ordered']
    assert any(o['select_ids']==[a['id'],b['id']] for o in p['options'])
    assert any(o['select_ids']==[b['id'],a['id']] for o in p['options'])


def test_sanctuary_keeps_adding_two_after_third_sacrifice_and_damage():
    s=empty();target=add(s,'c081',zone='rows');spell=add(s,'c074',zone='spells');spell['row']=0
    for i in range(3):
        victim=add(s,'c070',zone='rows',row=1)
        fx.execute(s,0,fx.op('sacrifice',targets=[victim['id']]))
        fx.settle(s);fx.drain(s)
        assert target['boost']==2*(i+1)
    fx.damage(s,1,[target['id']],3)
    victim=add(s,'c068',zone='rows',row=1)
    fx.execute(s,0,fx.op('sacrifice',targets=[victim['id']]))
    fx.settle(s);fx.drain(s)
    assert target['boost']==8 and target['damage']==3
    assert json.loads(json.dumps(s))['players'][0]['rows'][0][0]['boost']==8


def test_card_copy_does_not_advertise_removed_strength_caps():
    assert all('上限' not in c['text']+c['note'] for c in CARDS.values())
    assert '最多触发3次' in CARDS['c054']['text']
    assert '每小局最多触发一次' in CARDS['c067']['text']


def test_frost_preview_keeps_moved_siege_and_lethal_targets_in_unordered_options():
    s=empty()
    guard=add(s,'c081',seat=1,zone='rows',boost=4)
    spy=add(s,'c108',seat=1,zone='rows');spy['owner']=0
    siege=add(s,'c083',seat=1,zone='rows',row=2)
    night=add(s,'c086',seat=1,zone='rows')
    fx.execute(s,0,fx.op('move',targets=[siege['id']],row=0));fx.drain(s)
    s=play(s,add(s,'c113'));before=deepcopy(s)
    pending=game.project(s,0)['pending']
    assert s==before
    assert pending['multi_select']['minimum']==1
    assert not pending['multi_select']['ordered']
    assert {c['id'] for c in pending['multi_select']['cards']}=={guard['id'],spy['id'],siege['id'],night['id']}
    assert all(c['row']==0 for c in pending['multi_select']['cards'])
    for public,original in zip(pending['options'],s['pending']['options']):
        assert public['select_ids']==original['ops'][0]['targets']
    # Click order differs from board order; all three same-row targets remain legal.
    chosen=[night['id'],guard['id'],siege['id']]
    option=next(o for o in pending['options'] if set(o['select_ids'])==set(chosen))
    s=game.apply_action(s,0,'choose',dict(option=option['token']),0)
    assert set(next(c for c in s['players'][0]['spells'] if c['card']=='c113')['targets'])==set(chosen)
    powers={c['id']:d['power'] for c,d in zip(s['players'][1]['rows'][0],fx.row_power_details(s,1,0))}
    assert powers[siege['id']]==1 and powers[night['id']]==1


def test_lethal_mark_preview_never_edits_choice_operations():
    from dzmm_bot.core.mistrealm_v3_hints import choice_guidance
    for cid in ('c113','c120'):
        s=empty();victim=add(s,'c101',seat=1,zone='rows');s=play(s,add(s,cid))
        pending=deepcopy(s['pending']);original=deepcopy(pending['options'][0]['ops'])
        choice_guidance(s,0,pending)
        assert pending['options'][0]['ops']==original
        assert any('阵亡' in line for line in pending['options'][0]['preview'])
        s=game.apply_action(s,0,'choose',dict(option=pending['options'][0]['token']),0)
        assert victim['id'] in {c['id'] for c in s['players'][1]['discard']}
