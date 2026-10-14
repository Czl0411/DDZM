"""Derived Classic power. The board never stores cumulative strength edits."""
from .mistrealm_classic_cards import CLASSIC_CARDS, TRANSFORMS


def definition(card):
    cid = card.get('form', card['card'])
    return TRANSFORMS[cid] if cid in TRANSFORMS else CLASSIC_CARDS[cid]


def row_power_details(state, seat, row):
    player = state['players'][seat]
    cards = player['rows'][row]
    definitions = [definition(c) for c in cards]
    weather = any(c['row'] == row for c in state['weather'])
    support_horn = any('horn' in definition(c)['abilities'] for c in player['supports'][row])
    horn = support_horn or player['leader_horns'][row]
    details = []
    for index, card in enumerate(definitions):
        power = card['power']
        detail = dict(base=power,weather=None,bond=1,morale=0,horn=1,power=power,hero=card['hero'])
        if card['hero'] or card['type'] != 'unit':
            details.append(detail)
            continue
        if weather:
            half = player.get('leader') == 'c100' and not player.get('leader_disabled',False)
            power = (power + 1) // 2 if half else 1
            detail['weather'] = power
        if 'bond' in card['abilities']:
            detail['bond'] = sum(c.get('form', c['card']) == cards[index].get('form', cards[index]['card']) for c in cards)
        power *= detail['bond']
        detail['morale'] = sum('morale' in c['abilities'] for i, c in enumerate(definitions) if i != index)
        power += detail['morale']
        if horn or any('unit_horn' in c['abilities'] for i, c in enumerate(definitions) if i != index):
            detail['horn'] = 2
            power *= 2
        detail['power'] = power
        details.append(detail)
    return details


def row_powers(state, seat, row):
    return [d['power'] for d in row_power_details(state, seat, row)]


def score_rows(state, seat):
    return [sum(row_powers(state, seat, row)) for row in range(3)]
