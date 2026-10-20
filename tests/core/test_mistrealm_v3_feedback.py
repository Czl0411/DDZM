"""Actual numerical feedback follows authoritative resolution and stays public."""
import json
from random import Random
from dzmm_bot.core import mistrealm_v3_state as game
from tests.core.test_mistrealm_v3 import empty,add,play,finish


def cues(s):return game.project(s,0)['action_frames'][-1]['effects']
def events(s):return [e for step in cues(s) for e in step['events']]


def test_repeated_boost_reports_full_three_each_time():
    s=empty();target=add(s,'c081',zone='rows',boost=3);c=add(s,'c004')
    s=finish(play(s,c,0))
    gains=[e for e in events(s) if e['kind']=='power' and e['unit']==target['id']]
    assert len(gains)==1 and gains[0]['amount']==3
    s['turn']=0;c=add(s,'c004');s=play(s,c,0)
    chosen=next(o for o in s['pending']['options'] if o['card']['id']==target['id'])
    s=game.apply_action(s,0,'choose',{'option':chosen['token']},0,Random(0))
    assert any(e['kind']=='power' and e['unit']==target['id'] and e['amount']==3 for e in events(s))


def test_moving_whitebranch_records_condition_gain_and_actual_draw_without_private_ids():
    s=empty();branch=add(s,'c043',zone='rows',row=1);watcher=add(s,'c058',zone='rows',row=2)
    secret=add(s,'c081',zone='deck');mover=add(s,'c052');s=play(s,mover,1)
    chosen=next(o for o in s['pending']['options'] if o.get('card',{}).get('id')==branch['id'])
    s=game.apply_action(s,0,'choose',{'option':chosen['token']},0,Random(0))
    sequence=cues(s);flat=events(s)
    assert any(e['kind']=='move' and e['unit']==branch['id'] for e in flat)
    assert any(e['kind']=='power' and e['unit']==watcher['id'] and e['amount']==2 for e in flat)
    draw=next(step for step in sequence if any(e['kind']=='draw' for e in step['events']))
    assert draw['source']=='c043' and draw['events'][0]['amount']==1
    assert secret['id'] not in json.dumps(sequence) and secret['card'] not in json.dumps(sequence)
    assert cues(s)==game.project(s,1)['action_frames'][-1]['effects']


def test_lethal_hit_reports_remaining_strength_and_death_not_overkill():
    s=empty();victim=add(s,'c050',seat=1,zone='rows');c=add(s,'c032')
    s=finish(play(s,c,2));flat=events(s)
    assert any(e['kind']=='death' and e['unit']==victim['id'] for e in flat)
    assert [e['amount'] for e in flat if e['kind']=='power' and e['unit']==victim['id']]==[-2]
    assert all(e.get('unit')!=victim['id'] or e['card']=='c050' for e in flat)


def test_normal_round_cleanup_does_not_replay_previous_damage():
    s=empty();add(s,'c050',seat=1,zone='rows');c=add(s,'c032');s=finish(play(s,c,2))
    s=game.apply_action(s,s['turn'],'pass',{},0,Random(0))
    assert cues(s)==[]
    s=game.apply_action(s,s['turn'],'pass',{},0,Random(0))
    assert cues(s)==[]
    s=game.advance(s,5001,Random(0))
    assert cues(s)==[]


def test_public_effect_history_survives_frame_expiry_without_draw_identities():
    s=empty();secret=add(s,'c081',zone='deck');c=add(s,'c089');s['players'][0]['discarded_this_round']=True
    s=play(s,c,1)
    draw_events=[e for step in s['action_log'][-1]['effects'] for e in step['events'] if e['kind']=='draw']
    assert draw_events==[dict(kind='draw',seat=0,amount=1)]
    s['action_frames']=[]
    public=game.project(s,1)['action_log'][-1]
    assert public['effects'] and secret['id'] not in json.dumps(public) and secret['card'] not in json.dumps(public)


def test_return_and_sacrifice_feedback_distinguish_departure_and_original_owner():
    s=empty();spy=add(s,'c108',seat=1,zone='rows');spy['owner']=0
    spell=add(s,'c033');s=play(s,spell)
    option=next(o for o in s['pending']['options'] if o.get('card',{}).get('id')==spy['id'])
    s=game.apply_action(s,0,'choose',{'option':option['token']},0,Random(0))
    e=next(e for e in events(s) if e['kind']=='return')
    assert e['destination']==0 and e['unit']==spy['id']
    s=empty();victim=add(s,'c081',zone='rows');c=add(s,'c069');s=play(s,c,0)
    s=finish(s)
    e=next(e for e in events(s) if e['unit']==victim['id'] and e['kind']=='death')
    assert e['reason']=='sacrifice'
