"""Pure strength calculation; all conditions are recomputed from the current board."""
from .mistrealm_v3_cards import CARDS


def definition(card):
    return CARDS[card['card']]


def sealed(state, card):
    return card.get('sealed', False) or any(
        s['card'] == 'c120' and card['id'] in s.get('targets', [])
        for p in state['players'] if p for s in p.get('spells', []))


def row_power_details(state, seat, row):
    p, enemy = state['players'][seat], state['players'][1-seat]
    cards = p['rows'][row]
    details = []
    for c in cards:
        d = definition(c); cid = c['card']; bonus = 0
        others = [x for x in cards if x['id'] != c['id']]
        if not sealed(state, c):
            if 'bond' in d['abilities'] and any(x['card'] == cid for x in others): bonus += 2
            if cid == 'c010' and others: bonus += 2
            if cid in ('c012', 'c088') and p['spells']: bonus += 1 if cid == 'c012' else 2
            if cid in ('c015','c057','c110') and not others: bonus += {'c015':4,'c057':3,'c110':2}[cid]
            if cid == 'c016': bonus += min(3,len(others))
            if cid in ('c017','c056') and all(p['rows']): bonus += 3 if cid == 'c017' else 4
            if cid == 'c018' and len(p['spells']) >= 2: bonus += 3
            if cid in ('c021','c037','c055') and not enemy['rows'][1 if cid == 'c037' else 0]: bonus += 1 if cid == 'c021' else 3
            if cid == 'c035' and len(p['hand']) < len(enemy['hand']): bonus += 3
            if cid == 'c036': bonus += min(3,sum(x.get('damage',0)>0 for r in enemy['rows'] for x in r))
            if cid == 'c038' and sum(definition(x)['type']=='unit' for x in p['discard']) >= 3: bonus += 3
            if cid == 'c043' and len(enemy['rows'][1]) > len(p['rows'][1]): bonus += 2
            if cid == 'c058' and len(p['moved_actions']) >= 2: bonus += 3
            if cid == 'c075': bonus += min(4,len(set(p['dead_normal'])-{c['id']}))
            if cid == 'c076': bonus += min(3,sum(not definition(x)['hero'] for x in others))
            if cid == 'c077' and len(p['summoned']) >= 3: bonus += 3
            if cid == 'c095' and len(enemy['spells']) > len(p['spells']): bonus += 3
            if cid == 'c096': bonus += min(3,len(p['spells']))
            if cid == 'c097' and p['instant_count'] >= 2: bonus += 3
            if cid == 'c098' and len(others) >= 2 and all(not definition(x)['hero'] for x in others): bonus += 3
            if cid == 'c104' and enemy['spells']: bonus += 1
            if cid == 'c109' and sum(x.get('boost',0)>0 for r in enemy['rows'] for x in r) >= 2: bonus += 3
        for owner in state['players']:
            for spell in owner['spells']:
                if c['id'] in spell.get('targets',[]):
                    if spell['card'] == 'c113': bonus -= 1
                    if spell['card'] == 'c118': bonus += 1
        power = d['power'] + c.get('boost',0) + bonus - c.get('damage',0)
        details.append(dict(base=d['power'],boost=c.get('boost',0),condition=bonus,
                            damage=c.get('damage',0),shield=c.get('shield',0),sealed=bool(sealed(state,c)),
                            raw=power,power=max(0,power),hero=d['hero']))
    return details


def score_rows(state, seat):
    return [sum(d['power'] for d in row_power_details(state,seat,r)) for r in range(3)]
