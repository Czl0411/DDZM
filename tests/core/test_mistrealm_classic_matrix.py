"""Deterministic full matches through public legal moves, including every starter pair."""
import json
import random
import pytest
from dzmm_bot.core import mistrealm_classic_state as game
from dzmm_bot.core.mistrealm_classic_cards import STARTER_DECKS


def inventory(s):
    cards=[c['id'] for p in s['players'] for zone in [p['hand'],p['deck'],p['discard'],*p['rows'],*p['supports']] for c in zone]
    cards += [c['id'] for c in s['weather']]
    cards += [e['card']['id'] for e in s.get('opening',[])]
    if s['pending'] and s['pending'].get('source'): cards.append(s['pending']['source']['id'])
    return sorted(cards)


@pytest.mark.parametrize('left',range(10))
@pytest.mark.parametrize('right',range(10))
def test_every_starter_pair_finishes_conserves_cards_and_rematches(left,right):
    rng=random.Random(left*100+right);now=1000
    s=game.new_state('a',STARTER_DECKS[left],now)
    def act(seat,kind,payload=None):
        nonlocal s,now
        now+=1;s=game.apply_action(s,seat,kind,payload or {},now,rng)
    act(1,'join',{'uid':'b','deck':STARTER_DECKS[right]})
    act(0,'lock');act(1,'lock')
    expected=inventory(s)
    assert len(expected)==len(set(expected))
    if s['phase']=='choose_first':act(s['chooser'],'first',{'seat':rng.randrange(2)})
    for seat in (0,1):act(seat,'mulligan',{'cards':[c['id'] for c in s['players'][seat]['hand'][:2]]})
    for _ in range(300):
        assert inventory(s)==expected
        # Round-trip through JSON reproduces reconnect persistence on every action.
        s=json.loads(json.dumps(s))
        for seat in (0,1):
            view=game.project(s,seat)
            assert 'hand' not in view['players'][1-seat]
            assert 'deck' not in view['players'][seat]
            if s['pending'] and s['pending']['actor']!=seat:assert set(view['pending'])=={'actor'}
        if s['phase']=='finished':break
        if s['phase']=='round_result':
            now=s['deadline_ms'];s=game.advance(s,now,rng);continue
        seat=s['pending']['actor'] if s['pending'] else s['turn']
        moves=[m for m in game.legal_moves(s,seat) if m['action']!='concede']
        assert moves
        # Save resources on some rounds and play combinations on others.
        if not s['pending'] and rng.random()>.1:
            moves=[m for m in moves if m['action']!='pass'] or moves
        move=rng.choice(moves);act(seat,move['action'],move['payload'])
    else:pytest.fail('match failed to terminate within 300 legal actions')
    assert 1<=s['round']<=3 and min(s['lives'])==0
    act(0,'rematch');act(1,'rematch')
    assert s['phase']=='waiting' and s['lives']==[2,2]
    assert all(not p['hand'] and not p['locked'] for p in s['players'])
