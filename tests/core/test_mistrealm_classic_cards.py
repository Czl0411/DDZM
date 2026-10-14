"""Catalogue and server-owned deck validation contracts."""
from collections import Counter
from copy import deepcopy
import importlib
import importlib.util
import json
from pathlib import Path
import pytest

MODULE = 'dzmm_bot.core.mistrealm_classic_cards'

def api():
    assert importlib.util.find_spec(MODULE), 'Classic catalogue and validator must exist'
    return importlib.import_module(MODULE)

def test_catalogue_is_complete_and_has_resolvable_effect_references():
    m = api()
    cards = m.CLASSIC_CARDS
    assert set(cards) == {f'c{i:03d}' for i in range(1, 121)}
    assert len({c['name'] for c in cards.values()}) == 120
    assert Counter(c['type'] for c in cards.values()) == {'unit': 102, 'leader': 10, 'special': 8}
    assert set(c['faction'] for c in cards.values()) == {'crown', 'raven', 'frost', 'beast', 'mirror', 'neutral'}
    assert len(m.TRANSFORMS) == 2
    for c in cards.values():
        assert 1 <= c['copies'] <= 3
        assert set(c['rows']) <= {0, 1, 2}
        if c.get('transform'):
            assert c['transform'] in m.TRANSFORMS
        if 'muster' in c['abilities']:
            assert sum(x.get('group') == c['group'] for x in cards.values()) >= 3
        assert not set(c['abilities']) & {'damage', 'armor', 'lock', 'devour', 'doomed'}

def test_ten_starters_are_legal_and_snapshots_are_detached():
    m = api()
    assert len(m.STARTER_DECKS) == 10
    assert Counter(d['faction'] for d in m.STARTER_DECKS) == {f: 2 for f in m.FACTIONS}
    for d in m.STARTER_DECKS:
        original = deepcopy(d)
        snapshot = m.validate_deck(d['faction'], d['leader'], d['counts'])
        assert sum(n for cid,n in snapshot['counts'].items() if m.CLASSIC_CARDS[cid]['type']=='unit') >= 22
        assert sum(n for cid,n in snapshot['counts'].items() if m.CLASSIC_CARDS[cid]['type']=='special') <= 10
        snapshot['counts'].clear()
        assert d == original

@pytest.mark.parametrize('value', [-1, True, 1.5, '2', None, 4])
def test_invalid_counts_rejected(value):
    m = api(); d = deepcopy(m.STARTER_DECKS[0]); d['counts']['c001'] = value
    with pytest.raises(ValueError): m.validate_deck(d['faction'], d['leader'], d['counts'])

@pytest.mark.parametrize('change', ['21_units', '11_specials', 'enemy_card', 'enemy_leader', 'unknown', 'leader_in_deck', 'unknown_faction', 'null_counts'])
def test_invalid_deck_compositions_rejected(change):
    m=api(); d=deepcopy(m.STARTER_DECKS[0])
    if change=='21_units':
        d['counts']={k:v for k,v in d['counts'].items() if m.CLASSIC_CARDS[k]['type']=='unit'}
        while sum(d['counts'].values())>21:
            k=next(iter(d['counts'])); d['counts'][k]-=1
            if not d['counts'][k]: del d['counts'][k]
    elif change=='11_specials': d['counts'].update({'c113':3,'c114':3,'c115':3,'c116':2})
    elif change=='enemy_card': d['counts']['c021']=1
    elif change=='enemy_leader': d['leader']='c039'
    elif change=='unknown': d['counts']['nonexistent']=1
    elif change=='leader_in_deck': d['counts']['c019']=1
    elif change=='unknown_faction': d['faction']='unknown'
    elif change=='null_counts': d['counts']=None
    with pytest.raises(ValueError): m.validate_deck(d['faction'], d['leader'], d['counts'])

def test_export_matches_authoritative_catalogue():
    m=api()
    out=Path('gamefy/mistrealm/publish/classic/cards.json')
    assert out.exists()
    data=json.loads(out.read_text())
    assert data['cards']==m.CLASSIC_CARDS
    assert data['transforms']==m.TRANSFORMS
    assert data['starters']==m.STARTER_DECKS
