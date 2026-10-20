"""Queen moves either side without transferring units or sharing row capacity."""
import json
import pytest

from dzmm_bot.core import mistrealm_v3_effects as fx
from dzmm_bot.core import mistrealm_v3_state as game
from tests.core.test_mistrealm_v3 import empty,add,finish


def choose_move(s,c,row):
    s=json.loads(json.dumps(s))
    token=next(o['token'] for o in s['pending']['options']
               if o.get('card',{}).get('id')==c['id'] and o['row']==row)
    return game.apply_action(s,0,'choose',{'option':token},0)


@pytest.mark.parametrize('sides',[(0,1),(1,0),(1,1)])
def test_queen_moves_two_different_units_on_either_side_and_applies_friendly_boost_or_enemy_damage(sides):
    s=empty();s['players'][0]['leader']='c059'
    a=add(s,'c081',seat=sides[0],zone='rows')
    b=add(s,'c081',seat=sides[1],zone='rows')
    s=game.apply_action(s,0,'leader',{},0)
    s=choose_move(s,a,1)
    assert all(o.get('card',{}).get('id')!=a['id'] for o in s['pending']['options'])
    s=choose_move(s,b,2)
    assert not s['pending'] and s['turn']==1 and s['action_id']==1
    for c,side,row in ((a,sides[0],1),(b,sides[1],2)):
        found=fx.location(s,c['id'])
        assert found[:2]==(side,row) and found[2]['owner']==side
        assert found[2].get('boost',0)==(2 if side==0 else 0)
        assert found[2].get('damage',0)==(2 if side==1 else 0)


def test_queen_enemy_move_uses_enemy_capacity_draws_for_whitebranch_and_can_stop():
    s=empty();s['players'][0]['leader']='c059'
    a=add(s,'c043',seat=1,zone='rows',row=1)
    b=add(s,'c101',seat=1,zone='rows',row=1)
    drawn=add(s,'c081',seat=1,zone='deck')
    for _ in range(4):
        add(s,'c101',zone='rows',row=0)
        add(s,'c101',seat=1,zone='rows',row=2)
    s=game.apply_action(s,0,'leader',{},0)
    assert {o['row'] for o in s['pending']['options'] if o.get('card',{}).get('id')==a['id']}=={0}
    s=choose_move(s,a,0)
    assert s['players'][1]['hand']==[drawn] and not s['players'][0]['hand']
    assert {o['row'] for o in s['pending']['options'] if o.get('card',{}).get('id')==b['id']}=={0}
    stop=next(i for i,o in enumerate(s['pending']['options']) if o['label']=='结束转阵')
    s=finish(s,pick=stop)
    assert fx.location(s,a['id']) is None
    assert any(c['id']==a['id'] for c in s['players'][1]['discard'])
    assert fx.location(s,b['id'])[:2]==(1,1) and s['action_id']==1
