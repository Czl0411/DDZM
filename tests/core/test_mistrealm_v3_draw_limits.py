"""Draw limits survive bounce, death, JSON persistence and later rounds."""
import json
from random import Random
import pytest
from dzmm_bot.core import mistrealm_v3_state as game,mistrealm_v3_effects as fx
from dzmm_bot.core.mistrealm_v3_hints import card_status,unavailable_reason
from tests.core.test_mistrealm_v3 import empty,add,play,finish


def refill(s,seat=0):
    for _ in range(12):add(s,'c101',seat=seat,zone='deck')


def test_whitebranch_limit_survives_bounce_revive_and_refreshes_next_round():
    s=empty();refill(s);c=add(s,'c043',zone='rows',row=1)
    fx.execute(s,1,fx.op('move',targets=[c['id']],row=0));fx.drain(s)
    assert len(s['players'][0]['hand'])==2
    s=json.loads(json.dumps(s));c=fx.entity(s,c['id'])
    fx.remove_unit(s,c['id']);s['turn']=0;s=finish(play(s,c,1))
    fx.execute(s,0,fx.op('move',targets=[c['id']],row=0));fx.drain(s)
    assert len(s['players'][0]['hand'])==2
    fx.remove_unit(s,c['id'],True)
    fx.execute(s,0,fx.op('revive',targets=[c['id']],row=1,deploy=True));fx.drain(s)
    fx.execute(s,1,fx.op('move',targets=[c['id']],row=2));fx.drain(s)
    assert len(s['players'][0]['hand'])==2
    assert any('本小局已使用' in t['text'] for t in card_status(s,0,fx.entity(s,c['id']),'rows'))
    game._begin_round(s,0,Random(0))
    fx.execute(s,0,fx.op('recover',targets=[c['id']]))
    s['turn']=0;s=finish(play(s,fx.entity(s,c['id']),1));before=len(s['players'][0]['hand'])
    fx.execute(s,1,fx.op('move',targets=[c['id']],row=0));fx.drain(s)
    assert len(s['players'][0]['hand'])==before+2


def test_young_walker_only_once_per_entity_and_failed_condition_does_not_consume():
    s=empty();refill(s);c=add(s,'c089');s=finish(play(s,c,1))
    assert not fx.entity(s,c['id']).get('young_draw_used')
    s['players'][0]['discarded_this_round']=True
    fx.deployment(s,0,fx.entity(s,c['id']));fx.drain(s)
    assert len(s['players'][0]['hand'])==2
    s=json.loads(json.dumps(s));c=fx.entity(s,c['id'])
    fx.deployment(s,0,c);fx.drain(s)
    fx.remove_unit(s,c['id']);s['turn']=0;s=finish(play(s,c,1))
    assert len(s['players'][0]['hand'])==2
    fx.remove_unit(s,c['id'],True)
    fx.execute(s,0,fx.op('revive',targets=[c['id']],row=1,deploy=True));fx.drain(s)
    assert len(s['players'][0]['hand'])==2
    game._begin_round(s,0,Random(0));fx.execute(s,0,fx.op('recover',targets=[c['id']]))
    s['players'][0]['discarded_this_round']=True;s['turn']=0;before=len(s['players'][0]['hand'])
    s=finish(play(s,fx.entity(s,c['id']),1));assert len(s['players'][0]['hand'])==before-1
    assert any('整场已使用' in t['text'] for t in card_status(s,0,fx.entity(s,c['id']),'rows'))
    other=add(s,'c089');s['turn']=0;before=len(s['players'][0]['hand'])
    s=finish(play(s,other,1));assert len(s['players'][0]['hand'])==before+1


@pytest.mark.parametrize('first_from_discard',[False,True])
def test_prayer_limit_is_per_player_includes_recast_and_resets_each_round(first_from_discard):
    s=empty();refill(s);refill(s,1)
    prayer=add(s,'c093',zone='discard' if first_from_discard else 'hand')
    if first_from_discard:
        fx.execute(s,0,fx.op('recast',targets=[prayer['id']]));fx.drain(s);s=finish(s)
    else:s=finish(play(s,prayer))
    assert len(s['players'][0]['hand'])==2
    s=json.loads(json.dumps(s));s['turn']=0
    assert not fx.menu(s,0,dict(card='c090',id='ritualist'))
    fx.execute(s,0,fx.op('recast',targets=[prayer['id']]));fx.drain(s)
    assert len(s['players'][0]['hand'])==2
    fx.execute(s,0,fx.op('recover',targets=[prayer['id']]))
    c=fx.entity(s,prayer['id']);assert not fx.can_play(s,0,c,-1)
    duplicate=add(s,'c093');assert not fx.can_play(s,0,duplicate,-1)
    assert '本小局已施放' in unavailable_reason(s,0,c)
    with pytest.raises(ValueError):play(s,c)
    s['turn']=1;s=finish(play(s,add(s,'c093',seat=1)))
    assert len(s['players'][1]['hand'])==2
    game._begin_round(s,0,Random(0));s['turn']=0
    before=len(s['players'][0]['hand']);s=finish(play(s,fx.entity(s,prayer['id'])))
    assert len(s['players'][0]['hand'])==before+1
