"""Hints must describe the rules without changing state or revealing private cards."""
from copy import deepcopy

from dzmm_bot.core import mistrealm_v3_state as game
from dzmm_bot.core import mistrealm_v3_effects as fx
from dzmm_bot.core.mistrealm_v3_hints import card_status, unavailable_reason
from tests.core.test_mistrealm_v3 import empty, add, play


def test_projection_is_read_only_and_private_choices_stay_private():
    s=empty();target=add(s,'c001',zone='rows');enemy_hand=add(s,'c082',seat=1)
    c=add(s,'c048');s=play(s,c,0);before=deepcopy(s)
    own=game.project(s,0);opponent=game.project(s,1)
    assert s==before
    assert own['pending']['prompt']=='逐张选择要强化的己方单位'
    assert all('ops' not in o for o in own['pending']['options'])
    pair=next(o for o in own['pending']['options'] if len(o['target_ids'])==2)
    assert target['id'] in pair['target_ids']
    assert pair['selection_hint']=='已选2张牌'
    assert pair['effect_hint']=='强化＋2'
    assert opponent['pending']=={'actor':0}
    assert 'hand' not in own['players'][1]
    assert enemy_hand['id'] not in str(own['pending'])


def test_once_per_round_and_once_per_match_remain_distinct_after_return():
    s=empty();c=add(s,'c050',bounce_round=s['round'])
    assert card_status(s,0,c,'hand')[0]['short']=='回手已用'
    assert '本小局已使用' in card_status(s,0,c,'hand')[0]['text']
    s['round']+=1
    assert card_status(s,0,c,'hand')[0]['short']=='回手1次'
    other=add(s,'c085',zone='discard',exchange_used=True)
    assert '整场已使用' in game.project(s,0)['players'][0]['discard'][0]['ui_status'][0]['text']
    s['round']+=1
    assert card_status(s,0,other,'discard')[0]['tone']=='off'


def test_persistent_remaining_count_and_stopped_target_are_read_only():
    s=empty();target=add(s,'c001',seat=1,zone='rows')
    spell=add(s,'c114',zone='spells',ticks=1,targets=[target['id']]);before=deepcopy(s)
    assert card_status(s,0,spell,'spells')[0]['text']=='灰幕伤害：剩余2/3次'
    assert s==before
    s['players'][1]['passed']=True
    assert card_status(s,0,spell,'spells')[-1]['short']=='已停止'
    s['players'][1]['passed']=False;s['players'][1]['rows'][0]=[]
    assert card_status(s,0,spell,'spells')[-1]['short']=='无目标'


def test_intrinsic_condition_excludes_external_spell_and_seal_disables_it():
    s=empty();c=add(s,'c001',zone='rows');add(s,'c118',zone='spells',targets=[c['id']])
    projected=game.project(s,0)['players'][0]['rows'][0][0]
    assert projected['power_detail']['condition']==2
    assert projected['power_detail']['intrinsic']==0
    assert projected['ui_status'][0]['short']=='条件未生效'
    add(s,'c101',zone='rows')
    assert game.project(s,0)['players'][0]['rows'][0][0]['ui_status'][0]['short']=='条件＋2'
    c['sealed']=True
    statuses=game.project(s,0)['players'][0]['rows'][0][0]['ui_status']
    assert statuses[0]['short']=='已封印'
    assert statuses[1]['short']=='条件未生效'


def test_hand_hints_match_turn_capacity_and_conditional_deploy_can_still_play():
    s=empty();c=add(s,'c082')
    assert unavailable_reason(s,0,c)==''
    assert card_status(s,0,c,'hand')[0]['short']=='条件未满足'
    assert any(m['action']=='play' and m['payload']['card']==c['id'] for m in game.legal_moves(s,0))
    for _ in range(4):add(s,'c001',zone='rows',row=fx.definition(c)['rows'][0])
    assert '战列已满' in unavailable_reason(s,0,c)
    s['turn']=1;assert unavailable_reason(s,0,c)=='等待对手行动'
    s['turn']=0;c=add(s,'c076');s['players'][0]['rows']=[[],[],[]]
    assert '双方场上合计需要两名普通单位' in unavailable_reason(s,0,c)
    spell=add(s,'c094')
    for _ in range(3):add(s,'c094',zone='spells')
    assert '持续术位已满' in unavailable_reason(s,0,spell)


def test_move_preview_includes_destination_and_enemy_damage():
    s=empty();enemy=add(s,'c001',seat=1,zone='rows');c=add(s,'c053')
    s=play(s,c);pending=game.project(s,0)['pending']
    choice=next(o for o in pending['options'] if enemy['id'] in o['target_ids'])
    assert '移至' in choice['effect_hint'] and '伤害4' in choice['effect_hint']
    assert '强化' not in choice['effect_hint']


def test_revived_entity_hint_survives_death_and_expires_next_round():
    s=empty();c=add(s,'c001',zone='discard',revived_round=s['round'])
    assert card_status(s,0,c,'discard')[0]['short']=='复活已用'
    s['round']+=1
    assert card_status(s,0,c,'discard')==[]


def test_choice_side_uses_current_board_for_spies_and_viewer_perspective():
    from dzmm_bot.core.mistrealm_v3_hints import choice_guidance
    s=empty();spy=add(s,'c108',seat=1,zone='rows');spy['owner']=0
    own=add(s,'c001',zone='rows')
    pending=dict(title='目标',options=[dict(ops=[dict(kind='move',targets=[spy['id'],own['id']],row=1)])])
    choice_guidance(s,0,pending)
    assert [t['side'] for t in pending['options'][0]['target_sides']]==['enemy','own']
    choice_guidance(s,1,pending)
    assert [t['side'] for t in pending['options'][0]['target_sides']]==['own','enemy']


def test_choice_sides_cover_private_zones_spells_rows_and_skip():
    from dzmm_bot.core.mistrealm_v3_hints import choice_guidance
    s=empty();cards=[add(s,'c001',zone=z) for z in ('hand','deck','discard')]
    enemy=add(s,'c094',seat=1,zone='spells');trap=add(s,'c054',zone='spells');own=add(s,'c014',zone='spells')
    ops=[dict(kind='recover',targets=[c['id']]) for c in cards]+[
        dict(kind='bounce_spell',targets=[enemy['id']]),dict(kind='mark_row',source=trap['id'],row=0),dict(kind='mark_row',source=own['id'],row=2)]
    pending=dict(title='目标',options=[dict(ops=[op]) for op in ops]+[dict(ops=[])])
    choice_guidance(s,0,pending)
    assert [[t['side'] for t in o['target_sides']] for o in pending['options']]==[['own'],['own'],['own'],['enemy'],['enemy'],['own'],[]]


def test_preview_uses_full_boost_shield_and_lethal_damage_without_mutating_state():
    from dzmm_bot.core.mistrealm_v3_hints import choice_preview
    s=empty();target=add(s,'c081',zone='rows',boost=3);before=deepcopy(s)
    choice=dict(ops=[dict(kind='boost',targets=[target['id']],amount=3)])
    lines,_=choice_preview(s,0,choice)
    assert '7 → 10' in lines[0]
    assert s==before
    target['shield']=2
    lines,_=choice_preview(s,0,dict(ops=[dict(kind='damage',targets=[target['id']],amount=3)]))
    assert '7 → 6' in lines[0]
    lines,_=choice_preview(s,0,dict(ops=[dict(kind='damage',targets=[target['id']],amount=20)]))
    assert '将阵亡' in lines[0]


def test_choice_preview_does_not_resolve_or_reveal_draws_after_move():
    from dzmm_bot.core.mistrealm_v3_hints import choice_preview
    s=empty();branch=add(s,'c043',zone='rows',row=1);secret=add(s,'c081',zone='deck')
    before=deepcopy(s)
    lines,note=choice_preview(s,0,dict(ops=[dict(kind='move',targets=[branch['id']],row=0)]))
    assert '移至近战' in lines[0] and '后续触发' in note
    assert secret['id'] not in str(lines) and secret['card'] not in str(lines)
    assert s==before


def test_restrictions_keep_guard_targets_and_explain_hero_full_rows_and_repeat_revive():
    from dzmm_bot.core.mistrealm_v3_hints import choice_guidance
    s=empty();taunt=add(s,'c102',seat=1,zone='rows');foe=add(s,'c081',seat=1,zone='rows')
    c=add(s,'c027');s=play(s,c,1)
    pending=game.project(s,0)['pending']
    assert foe['id'] not in pending['target_reasons']
    assert taunt['id'] not in pending['target_reasons']
    s=empty();hero=add(s,'c015',zone='rows');ordinary=add(s,'c081',zone='rows')
    source=add(s,'c050',zone='rows',row=1)
    options=fx.menu(s,0,source)
    pending=dict(title='移动',options=options)
    choice_guidance(s,0,pending)
    assert '英雄不可选' in pending['target_reasons'][hero['id']]
    for r in (1,2):
        while len(s['players'][0]['rows'][r])<4:add(s,'c081',zone='rows',row=r)
    pending=dict(title='移动',options=fx.menu(s,0,source));choice_guidance(s,0,pending)
    assert '已满' in pending['target_reasons'][ordinary['id']]
    s=empty();used=add(s,'c081',zone='discard',revived_round=s['round']);add(s,'c081',zone='discard')
    source=add(s,'c051',zone='rows',row=1)
    pending=dict(title='复活',options=fx.menu(s,0,source));choice_guidance(s,0,pending)
    assert '本小局已复活' in pending['target_reasons'][used['id']]
