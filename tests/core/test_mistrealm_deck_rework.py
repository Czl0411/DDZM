from copy import deepcopy

import pytest

from dzmm_bot.core.mistrealm_state import targets_for
from tests.core.test_mistrealm_state import act, playing, unit


def setup_card(key, row=1):
    s = playing()
    s['turn'] = 0
    s['first_bonus'] = False
    s['players'][0]['hand'] = [{'id': 'played', 'key': key}]
    return s, {'card': 'played', 'row': row, 'targets': []}


def test_medic_revives_without_deployment_and_consumes_discard():
    s, payload = setup_card('neutral_medic')
    s['players'][0]['discard'] = [{'id': 'bow', 'key': 'neutral_crossbow'}]
    s['players'][1]['rows'][0] = [unit('neutral_mercenary')]
    payload['targets'] = ['bow']
    result = act(s, 0, 'play', payload)
    p = result['players'][0]
    assert not p['discard']
    assert p['rows'][1] == [unit('neutral_medic', 'played'), unit('neutral_crossbow', 'bow')]
    assert result['players'][1]['rows'][0][0]['power'] == 7


def test_revive_excludes_medics_high_power_tactics_and_full_destination():
    s, payload = setup_card('neutral_medic')
    p = s['players'][0]
    p['discard'] = [{'id': key, 'key': key} for key in
                    ['neutral_medic', 'neutral_mercenary', 'neutral_pierce', 'neutral_crossbow', 'neutral_guard']]
    p['rows'][1] = [unit('neutral_crossbow', str(i)) for i in range(5)]
    # The medic itself will occupy the final rear slot.
    options, _, _ = targets_for(s, 0, 'neutral_medic', 1)
    assert [c['key'] for c in options] == ['neutral_guard']
    payload['targets'] = ['neutral_crossbow']
    original = deepcopy(s)
    with pytest.raises(ValueError): act(s, 0, 'play', payload)
    assert s == original


def test_recall_resets_stats_and_can_redeploy_effect():
    s, payload = setup_card('raven_guide')
    s['players'][0]['rows'][0] = [unit('raven_knight', 'knight', power=1, armor=4)]
    payload['targets'] = ['knight']
    s = act(s, 0, 'play', payload)
    assert not s['players'][0]['rows'][0]
    assert s['players'][0]['hand'] == [{'id': 'knight', 'key': 'raven_knight'}]
    s['turn'] = 0
    s['players'][1]['rows'][0] = [unit('neutral_mercenary')]
    s = act(s, 0, 'play', {'card': 'knight', 'row': 0, 'targets': ['target']})
    assert s['players'][0]['rows'][0][0] == unit('raven_knight', 'knight')
    assert s['players'][1]['rows'][0][0]['power'] == 5


def test_recall_is_optional_and_cannot_recall_itself_or_enemy():
    s, payload = setup_card('raven_guide')
    s['players'][0]['rows'][0] = [unit('neutral_guard', 'friend')]
    s['players'][1]['rows'][0] = [unit('neutral_guard', 'enemy')]
    assert act(s, 0, 'play', payload)['players'][0]['rows'][0]
    for target in ['played', 'enemy']:
        with pytest.raises(ValueError): act(s, 0, 'play', {**payload, 'targets': [target]})


def test_banner_boosts_new_same_row_units_only():
    s, payload = setup_card('neutral_crossbow')
    s['players'][0]['rows'][1] = [unit('crown_banner', 'flag')]
    s = act(s, 0, 'play', payload)
    assert s['players'][0]['rows'][1][-1]['power'] == 5
    s['turn'] = 0
    s['players'][0]['hand'] = [{'id': 'guard', 'key': 'neutral_guard'}]
    s = act(s, 0, 'play', {'card': 'guard', 'row': 0, 'targets': []})
    assert s['players'][0]['rows'][0][0]['power'] == 5


def test_banner_any_row_no_self_trigger_and_revive_does_not_trigger_banner():
    s, payload = setup_card('crown_banner', 0)
    s = act(s, 0, 'play', payload)
    assert s['players'][0]['rows'][0][0]['power'] == 3
    s['turn'] = 0
    s['players'][0]['hand'] = [{'id': 'medic', 'key': 'neutral_medic'}]
    s['players'][0]['discard'] = [{'id': 'guard', 'key': 'neutral_guard'}]
    s = act(s, 0, 'play', {'card': 'medic', 'row': 1, 'targets': ['guard']})
    assert s['players'][0]['rows'][0][-1]['power'] == 5


def test_pierce_removes_boosts_and_armor_without_healing_injured_units():
    for power, expected in [(14, 4), (5, 2)]:
        s, payload = setup_card('neutral_pierce', 0)
        s['players'][1]['rows'][0] = [unit('neutral_mercenary', power=power, armor=10)]
        payload['targets'] = ['target']
        s = act(s, 0, 'play', payload)
        target = s['players'][1]['rows'][0][0]
        assert (target['power'], target['armor']) == (expected, 0)


def test_revived_banner_is_active_on_later_deployment_and_stacks():
    s, payload = setup_card('neutral_medic')
    p = s['players'][0]
    p['rows'][0] = [unit('crown_banner', 'old-flag')]
    p['discard'] = [{'id': 'revived-flag', 'key': 'crown_banner'}]
    payload['targets'] = ['revived-flag']
    s = act(s, 0, 'play', payload)
    assert s['players'][0]['rows'][0][-1]['power'] == 3
    s['turn'] = 0
    s['players'][0]['hand'] = [{'id': 'infantry', 'key': 'crown_infantry'}]
    s = act(s, 0, 'play', {'card': 'infantry', 'row': 0, 'targets': []})
    assert s['players'][0]['rows'][0][-1]['power'] == 10


def test_removing_banner_stops_its_future_bonus():
    s, payload = setup_card('raven_guide')
    s['players'][0]['rows'][0] = [unit('crown_banner', 'flag')]
    payload['targets'] = ['flag']
    s = act(s, 0, 'play', payload)
    s['turn'] = 0
    s['players'][0]['hand'].append({'id': 'guard', 'key': 'neutral_guard'})
    s = act(s, 0, 'play', {'card': 'guard', 'row': 0, 'targets': []})
    assert s['players'][0]['rows'][0][0]['power'] == 5


def test_any_row_revive_falls_back_to_rear_and_never_exceeds_capacity():
    s, payload = setup_card('neutral_medic')
    p = s['players'][0]
    p['rows'][0] = [unit('neutral_guard', str(i)) for i in range(6)]
    p['discard'] = [{'id': 'flag', 'key': 'crown_banner'}]
    payload['targets'] = ['flag']
    result = act(s, 0, 'play', payload)
    assert result['players'][0]['rows'][1][-1]['id'] == 'flag'
    p['rows'][1] = [unit('neutral_crossbow', str(i+6)) for i in range(5)]
    with pytest.raises(ValueError): act(s, 0, 'play', payload)
