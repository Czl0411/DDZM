"""Whitebranch draws two on its first successful move each round."""
from dzmm_bot.core import mistrealm_v3_effects as fx
from dzmm_bot.core.mistrealm_v3_cards import CARDS
from tests.core.test_mistrealm_v3 import empty,add,play,finish
from tests.core.test_mistrealm_v3_revision2 import strength


def test_whitebranch_base_two_first_move_draws_two_for_its_side():
    s=empty();cards=[add(s,'c081',zone='deck') for _ in range(5)]
    add(s,'c081',seat=1,zone='rows',row=1);add(s,'c081',seat=1,zone='rows',row=1)
    c=add(s,'c043');s=finish(play(s,c,1))
    assert CARDS['c043']['power']==2 and strength(s,c)==2
    assert not s['players'][0]['hand']
    # Only the first successful move counts, regardless of which player moves it.
    for i,(actor,row) in enumerate(((0,0),(1,2),(0,1),(1,0)),1):
        fx.execute(s,actor,fx.op('move',targets=[c['id']],row=row));fx.drain(s)
        assert len(s['players'][0]['hand'])==2
        assert not s['players'][1]['hand']
    assert len(s['players'][0]['deck'])==3


def test_whitebranch_no_draw_for_same_row_full_destination_or_sealed_and_empty_deck_is_safe():
    s=empty();c=add(s,'c043',zone='rows',row=1);drawn=add(s,'c081',zone='deck')
    for _ in range(4):add(s,'c081',zone='rows')
    for row in (1,0):
        fx.execute(s,0,fx.op('move',targets=[c['id']],row=row));fx.drain(s)
        assert not s['players'][0]['hand']
    c['sealed']=True;fx.execute(s,1,fx.op('move',targets=[c['id']],row=2));fx.drain(s)
    assert not s['players'][0]['hand']
    c.pop('sealed');fx.execute(s,0,fx.op('move',targets=[c['id']],row=1));fx.drain(s)
    assert s['players'][0]['hand']==[drawn]
    fx.execute(s,1,fx.op('move',targets=[c['id']],row=2));fx.drain(s)
    assert s['players'][0]['hand']==[drawn]


def test_enemy_deployment_moves_whitebranch_and_draws_without_extra_action():
    s=empty();c=add(s,'c043',seat=1,zone='rows',row=1);drawn=add(s,'c081',seat=1,zone='deck')
    mover=add(s,'c107');s=finish(play(s,mover,CARDS['c107']['rows'][0]))
    assert fx.location(s,c['id'])[1]!=1
    assert s['players'][1]['hand']==[drawn] and not s['players'][0]['hand']
    assert s['action_id']==1 and s['turn']==1
