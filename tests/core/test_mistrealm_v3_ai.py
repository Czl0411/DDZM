from copy import deepcopy
from random import Random
from dzmm_bot.core.mistrealm_v3_ai import pick_move,visible_simulation
from dzmm_bot.core import mistrealm_v3_state as game
from tests.core.test_mistrealm_v3 import empty,add,play,started


def test_ai_passes_won_round_and_retains_cards():
    s=empty();s['turn']=1;s['players'][0]['passed']=True
    add(s,'c081',seat=1,zone='rows');card=add(s,'c015',seat=1)
    assert pick_move(s)['action']=='pass'
    assert card in s['players'][1]['hand']


def test_ai_prefers_moving_whitebranch_for_draw_synergy():
    s=empty();s['turn']=1
    add(s,'c081',seat=1,zone='rows');branch=add(s,'c043',seat=1,zone='rows',row=1)
    add(s,'c081',seat=1,zone='deck');add(s,'c015',zone='rows')
    s=play(s,add(s,'c053',seat=1))
    chosen=pick_move(s)
    option=next(o for o in s['pending']['options'] if o['token']==chosen['payload']['option'])
    assert branch['id'] in option['ops'][0]['targets']
    actual=game.apply_action(s,1,'choose',chosen['payload'],0,Random(0))
    assert len(actual['players'][1]['hand'])==1


def test_ai_uses_cheapest_winning_card_and_keeps_hero():
    s=empty();s['turn']=1;s['players'][0]['passed']=True
    weak=add(s,'c081',seat=1);hero=add(s,'c015',seat=1)
    move=pick_move(s)
    assert move['action']=='play' and move['payload']['card']==weak['id']


def test_ai_yields_only_when_it_can_afford_a_round_loss():
    s=empty();s['turn']=1
    for _ in range(4):add(s,'c015',zone='rows')
    for _ in range(3):add(s,'c081',seat=1);add(s,'c081')
    s['action_log']=[dict(kind='play',seat=1,round=1),dict(kind='play',seat=1,round=1)]
    assert pick_move(s)['action']=='pass'
    s['lives'][1]=1
    assert pick_move(s)['action']!='pass'


def test_ai_does_not_use_hidden_opponent_cards_or_actual_draw_order():
    s=empty();s['turn']=1
    add(s,'c081',seat=1);add(s,'c043',seat=1);add(s,'c001');add(s,'c015',zone='deck')
    for cid in ('c001','c015','c043'):add(s,cid,seat=1,zone='deck')
    other=deepcopy(s);other['players'][0]['hand'][0]['card']='c120';other['players'][0]['deck'][0]['card']='c119'
    other['players'][1]['deck'].reverse()
    before=deepcopy(s)
    assert pick_move(s)==pick_move(other)
    assert s==before
    assert all(c['card']=='c081' for c in visible_simulation(s,1)['players'][0]['hand'])


def test_ai_completes_whole_matches_across_factions_without_illegal_actions():
    # Both seats use the same policy; this exercises three-round resource retention and choices.
    for pair in ((0,2),(4,6),(6,8)):
        s=started(*pair);now=0
        for _ in range(180):
            if s['phase']=='finished':break
            if s['phase']=='round_result':now+=5001;s=game.advance(s,now,Random(4));continue
            seat=s['pending']['actor'] if s['pending'] else s['turn']
            move=pick_move(s,seat)
            assert move in game.legal_moves(s,seat)
            s=game.apply_action(s,seat,move['action'],move['payload'],now,Random(4))
        assert s['phase']=='finished' and 1<=s['round']<=3


def test_ai_sacrifices_death_trigger_instead_of_healthy_high_power_unit():
    s=empty();s['turn']=1
    death_draw=add(s,'c067',seat=1,zone='rows');strong=add(s,'c081',seat=1,zone='rows',boost=4)
    add(s,'c015',zone='rows');add(s,'c101',seat=1,zone='rows',row=1)
    add(s,'c081',seat=1,zone='deck')
    s=play(s,add(s,'c073',seat=1))
    move=pick_move(s)
    option=next(o for o in s['pending']['options'] if o['token']==move['payload']['option'])
    assert next(o for o in option['ops'] if o['kind']=='sacrifice')['targets']==[death_draw['id']]


def test_ai_revives_deployment_value_instead_of_first_discard_entry():
    s=empty();s['turn']=1
    add(s,'c101',seat=1,zone='discard')
    archer=add(s,'c028',seat=1,zone='discard')
    add(s,'c015',zone='rows')
    s=play(s,add(s,'c051',seat=1),1)
    move=pick_move(s)
    option=next(o for o in s['pending']['options'] if o['token']==move['payload']['option'])
    assert archer['id'] in option['ops'][0]['targets']
