from copy import deepcopy
from datetime import datetime, timezone

from mahjong.tile import TilesConverter

from dzmm_bot.core.mahjong_hints import hand_hints
from dzmm_bot.core.mahjong_state import action_options, new_match


def fixture():
    state = new_match(list(range(136)), datetime(2026, 10, 23, tzinfo=timezone.utc))
    state['hands'][0] = [84, 88, 92, 96, 97, 100, 101]
    state['melds'][0] = [
        {'kind': 'pon', 'tiles': [93,94,95], 'open': True},
        {'kind': 'pon', 'tiles': [56,57,58], 'open': True},
    ]
    state['turn'] = 1
    return state


def test_open_hand_waits_and_counts_only_publicly_unseen_tiles():
    state = fixture()
    state['discards'][3] = [{'tile':95}, {'tile':98}]
    result = hand_hints(state, 0, {})['current']
    assert result['waits'] == [
        {'type':24, 'unseen':1, 'ron_reason':None, 'tsumo_reason':None},
        {'type':25, 'unseen':2, 'ron_reason':None, 'tsumo_reason':None},
    ]
    # Changing hidden hands / wall / unrevealed dora must not disclose information.
    other = deepcopy(state)
    other['hands'][1:] = [[], [98,99,102,103], []]
    other['wall'].reverse()
    other['dead_wall'][5] = 103
    assert hand_hints(other, 0, {}) == hand_hints(state, 0, {})


def test_called_discard_is_counted_once_and_exhausted_wait_remains_visible():
    state = fixture()
    state['melds'][1] = [{'kind':'pon','tiles':[98,99,102], 'open':True}]
    state['discards'][1] = [{'tile':98, 'called':True}]
    # Count uses physical IDs, not duplicated river/meld appearances.
    waits = hand_hints(state, 0, {})['current']['waits']
    assert waits[0]['unseen'] == 0
    assert waits[1]['unseen'] == 1


def test_one_discarded_wait_causes_furiten_for_every_wait_but_not_tsumo():
    state = fixture()
    state['discards'][0] = [{'tile':98}]
    value = hand_hints(state,0,{})['current']
    assert value['furiten'] == 'discard'
    assert all(x['ron_reason'] == 'discard' and x['tsumo_reason'] is None for x in value['waits'])
    state['discards'][0] = []
    state['temporary_furiten'][0] = True
    assert hand_hints(state,0,{})['current']['furiten'] == 'temporary'
    state['riichi'][0] = True
    assert hand_hints(state,0,{})['current']['furiten'] == 'riichi_pass'


def test_discard_preview_counts_discard_as_known_and_furiten():
    state = fixture()
    state['hands'][0].append(102)
    value = hand_hints(state,0,{'discard':[102]})
    assert value['current'] is None
    assert set(value['discards']) == {'102'}
    assert value['discards']['102']['furiten'] == 'discard'
    assert value['discards']['102']['waits'][1]['unseen'] == 1


def test_no_yaku_is_distinguished_from_not_tenpai():
    state = fixture()
    state['hands'][0] = TilesConverter.string_to_136_array(man='456',pin='1235',sou='789')
    state['melds'][0] = [{'kind':'chi','tiles':TilesConverter.string_to_136_array(man='123'),'open':True}]
    value = hand_hints(state,0,{})['current']
    assert len(value['waits']) == 1
    assert value['waits'][0]['ron_reason'] == value['waits'][0]['tsumo_reason'] == 'no_yaku'


def test_spectators_and_finished_hands_do_not_get_hints():
    state = fixture()
    assert hand_hints(state,None,{}) == {}
    state['phase'] = 'hand_finished'
    assert hand_hints(state,0,{}) == {}


def test_riichi_only_offers_drawn_discard_and_no_wait_changing_kan():
    state = fixture()
    state['melds'][0] = []
    state['hands'][0] = TilesConverter.string_to_136_array(man='111123',pin='456',sou='789',honors='11')
    state['turn'] = 0
    state['riichi'][0] = True
    state['drawn_tile'] = state['hands'][0][-1]
    options = action_options(state,0)
    assert options['discard'] == [state['drawn_tile']]
    assert not options.get('ankan')


def test_already_answered_reaction_has_no_buttons():
    state = fixture()
    state['phase'] = 'reaction'
    state['pending'] = {'eligible':{'0':{'ron':True,'pass':True}},'decisions':{'0':{'action':'pass'}}}
    assert action_options(state,0) == {}


def test_screenshot_waits_are_no_yaku_but_last_discard_ron_is_shown():
    from dzmm_bot.core.mahjong_state import apply_action
    state = fixture()
    state['hands'][0] = TilesConverter.string_to_136_array(man='6799', pin='234')
    state['melds'][0] = [
        {'kind':'pon','tiles':TilesConverter.string_to_136_array(pin='999'),'open':True},
        {'kind':'chi','tiles':TilesConverter.string_to_136_array(man='123'),'open':True},
    ]
    value = hand_hints(state, 0, {})['current']
    assert [x['type'] for x in value['waits']] == [4,7]
    assert all(x['ron_reason'] == x['tsumo_reason'] == 'no_yaku' for x in value['waits'])
    # Real reducer: the final discard grants houtei even to this open no-yaku hand.
    state['wall'] = []
    state['hands'][1] = [28]
    state['hands'][2] = []
    state['hands'][3] = []
    state['drawn_tile'] = 28
    state = apply_action(state, 1, 'discard', {'tile':28,'version':state['version']}, datetime(2026,10,23,tzinfo=timezone.utc))
    actions = action_options(state, 0)
    assert actions['ron']
    value = hand_hints(state, 0, actions)['current']
    assert 'ron_now' not in value['waits'][0]
    assert value['waits'][1]['ron_now'] is True
    # No permission means no stale actionable ron indicator.
    assert all('ron_now' not in x for x in hand_hints(state, 0, {})['current']['waits'])
