from datetime import datetime, timedelta, timezone

import pytest

from dzmm_bot.core.mahjong_state import (
    advance_after_result,
    apply_action,
    new_match,
)

NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def ordered_wall():
    # The reducer accepts a deterministic wall for tests; production shuffles it.
    return list(range(136))


def test_new_match_deals_four_private_hands_and_draws_for_dealer():
    state = new_match(ordered_wall(), NOW, mode="east")
    assert state["phase"] == "playing"
    assert [len(hand) for hand in state["hands"]] == [14, 13, 13, 13]
    assert state["turn"] == 0
    assert state["drawn_tile"] in state["hands"][0]
    assert len(set(sum(state["hands"], []) + state["wall"] + state["dead_wall"])) == 136


def test_discard_rejects_wrong_player_and_stale_version():
    state = new_match(ordered_wall(), NOW, mode="east")
    with pytest.raises(ValueError, match="轮到"):
        apply_action(
            state, 1, "discard",
            {"tile": state["hands"][1][0], "version": 0}, NOW,
        )
    with pytest.raises(ValueError, match="版本"):
        apply_action(
            state, 0, "discard",
            {"tile": state["hands"][0][0], "version": 99}, NOW,
        )


def test_unclaimed_discard_advances_turn_and_draws():
    state = new_match(ordered_wall(), NOW, mode="east")
    before = len(state["wall"])
    discarded = state["hands"][0][-1]
    result = apply_action(
        state, 0, "discard", {"tile": discarded, "version": 0}, NOW,
    )
    # Deterministic wall may offer calls. Everyone passing resolves it.
    if result["phase"] == "reaction":
        for seat in sorted(result["pending"]["eligible"], key=int):
            result = apply_action(
                result, int(seat), "pass", {"version": result["version"]}, NOW,
            )
    assert result["phase"] == "playing"
    assert result["turn"] == 1
    assert len(result["hands"][1]) == 14
    assert len(result["wall"]) == before - 1


def reaction_with_chi_and_pon():
    state = new_match(ordered_wall(), NOW, mode="east")
    state["hands"] = [[8], [0, 4, 12, 16], [9, 10], []]
    return apply_action(state, 0, "discard", {"tile": 8, "version": 0}, NOW)


def test_reaction_keeps_full_fifteen_seconds_and_resolves_after_all_answers():
    from dzmm_bot.core.mahjong_state import apply_timeout

    state = reaction_with_chi_and_pon()
    assert datetime.fromisoformat(state["deadline"]) == NOW + timedelta(seconds=15)
    assert apply_timeout(state, NOW + timedelta(seconds=6), ordered_wall) == state
    original_version = state["version"]
    state = apply_action(state, 2, "pass", {"version": original_version}, NOW)
    assert datetime.fromisoformat(state["deadline"]) == NOW + timedelta(seconds=15)
    expired = apply_timeout(state, NOW + timedelta(seconds=15), ordered_wall)
    assert expired["phase"] == "playing" and expired["turn"] == 1
    assert expired["melds"][1] == []
    result = apply_action(state, 1, "chi", {
        "version": original_version, "reaction_version": original_version, "tiles": [4, 12],
    }, NOW + timedelta(seconds=10))
    assert result["phase"] == "playing"
    assert result["turn"] == 1
    assert result["melds"][1][0]["tiles"] == [4, 8, 12]


def test_reaction_token_does_not_allow_old_or_duplicate_responses():
    state = reaction_with_chi_and_pon()
    version = state["version"]
    state = apply_action(state, 2, "pass", {"version": version}, NOW)
    with pytest.raises(ValueError):
        apply_action(state, 1, "chi", {"version": version, "tiles": [4, 12]}, NOW)
    with pytest.raises(ValueError):
        apply_action(state, 1, "chi", {
            "version": state["version"], "reaction_version": version - 1, "tiles": [4, 12],
        }, NOW)
    with pytest.raises(ValueError):
        apply_action(state, 2, "pass", {"version": version, "reaction_version": version}, NOW)
    with pytest.raises(ValueError, match="超时"):
        apply_action(state, 1, "chi", {
            "version": version, "reaction_version": version, "tiles": [4, 12],
        }, NOW + timedelta(seconds=15))


def test_simultaneous_pon_still_takes_priority_over_chi():
    state = reaction_with_chi_and_pon()
    version = state["version"]
    state = apply_action(state, 1, "chi", {"version": version, "tiles": [4, 12]}, NOW)
    assert state["phase"] == "reaction"
    result = apply_action(state, 2, "pon", {
        "version": version, "reaction_version": version, "tiles": [9, 10],
    }, NOW)
    assert result["turn"] == 2
    assert result["melds"][2][0]["kind"] == "pon"
    assert result["melds"][1] == []
    with pytest.raises(ValueError):
        apply_action(result, 1, "pass", {
            "version": result["version"], "reaction_version": version,
        }, NOW)


def test_fixed_coin_prizes_are_zero_sum_against_escrow():
    state = new_match(ordered_wall(), NOW, mode="east")
    state["points"] = [42000, 28000, 19000, 11000]
    state["phase"] = "match_finished"
    state["result"] = {"kind": "match", "finished_at": NOW.isoformat()}
    advanced = advance_after_result(state, ordered_wall(), NOW + timedelta(seconds=8))
    assert advanced == state
    order = sorted(range(4), key=lambda seat: (-state["points"][seat], seat))
    prizes = dict(zip(order, (200, 120, 60, 20), strict=True))
    assert sum(prizes.values()) == 400


def open_wait_state():
    state = new_match(ordered_wall(), NOW)
    state["hands"][0] = [84, 88, 92, 96, 97, 100, 101]
    state["melds"][0] = [
        {"kind": "pon", "tiles": [93, 94, 95], "open": True, "called_tile": 95, "from": 3},
        {"kind": "pon", "tiles": [56, 57, 58], "open": True, "called_tile": 58, "from": 3},
    ]
    used = {*state["hands"][0], 93, 94, 95, 56, 57, 58, 102}
    remaining = [tile for tile in range(136) if tile not in used]
    state["hands"][1] = [102, *remaining[:13]]
    state["hands"][2] = remaining[13:26]
    state["hands"][3] = remaining[26:39]
    state["wall"] = remaining[39:-14]
    state["dead_wall"] = remaining[-14:]
    state.update(turn=1, drawn_tile=102, any_call=True, turn_counts=[1, 1, 1, 1])
    return state


def test_open_hand_offers_ron_alongside_pon_and_settles():
    state = open_wait_state()
    state = apply_action(state, 1, "discard", {"tile": 102, "version": state["version"]}, NOW)
    options = state["pending"]["eligible"]["0"]
    assert options["ron"] and options["pon"]
    eligible = list(state["pending"]["eligible"])
    for seat in eligible:
        state = apply_action(state, int(seat), "ron" if seat == "0" else "pass", {"version": state["version"]}, NOW)
    assert state["phase"] == "hand_finished"
    assert state["points"][0] > 25000
    assert sum(state["points"]) == 100000


@pytest.mark.parametrize("temporary", [False, True])
def test_open_hand_furiten_still_blocks_ron(temporary):
    state = open_wait_state()
    if temporary:
        state["temporary_furiten"][0] = True
    else:
        state["discards"][0] = [{"tile": 98, "called": False, "riichi": False}]
    state = apply_action(state, 1, "discard", {"tile": 102, "version": state["version"]}, NOW)
    assert "ron" not in state["pending"]["eligible"]["0"]
    assert state["pending"]["eligible"]["0"]["pon"]


def test_open_hand_offers_tsumo():
    from dzmm_bot.core.mahjong_state import action_options
    state = open_wait_state()
    state["hands"][1].remove(102)
    state["hands"][0].append(102)
    state["turn"] = 0
    assert action_options(state, 0)["tsumo"]
    state = apply_action(state, 0, "tsumo", {"version": state["version"]}, NOW)
    assert state["phase"] == "hand_finished"
    assert sum(state["points"]) == 100000


def test_ippatsu_expires_on_first_discard_after_riichi():
    state = open_wait_state()
    state['hands'][0].append(103)
    state.update(turn=0, drawn_tile=103)
    state['riichi'][0] = state['ippatsu'][0] = True
    result = apply_action(state,0,'discard',{'tile':103,'version':state['version']},NOW)
    assert not result['ippatsu'][0]


def test_choosing_pon_instead_of_available_ron_sets_furiten():
    state = open_wait_state()
    state = apply_action(state,1,'discard',{'tile':102,'version':state['version']},NOW)
    choice = state['pending']['eligible']['0']['pon'][0]
    result = apply_action(state,0,'pon',{'tiles':choice,'version':state['version']},NOW)
    assert result['temporary_furiten'][0]


@pytest.mark.parametrize('seed', range(3))
def test_complete_matches_accept_offered_actions_and_conserve_points(seed):
    from random import Random
    from dzmm_bot.core.mahjong_state import action_options
    rng = Random(seed)
    def wall():
        values = list(range(136)); rng.shuffle(values); return values
    now = NOW
    state = new_match(wall(), now)
    for _ in range(6000):
        assert sum(state['points']) + state['riichi_sticks'] * 1000 == 100000
        if state['phase'] == 'match_finished':
            break
        if state['phase'] == 'hand_finished':
            assert state['deadline'] is None
            now += timedelta(seconds=1)
            state = advance_after_result(state,wall(),now)
            continue
        if state['phase'] == 'reaction':
            seat = next(int(s) for s in state['pending']['eligible'] if action_options(state,int(s)))
        else:
            seat = state['turn']
        options = action_options(state,seat)
        action = 'ron' if options.get('ron') else 'tsumo' if options.get('tsumo') else rng.choice(list(options))
        payload = {'version':state['version']}
        if action in ('discard','riichi'):payload['tile'] = rng.choice(options[action])
        elif action in ('chi','pon','kan'):payload['tiles'] = rng.choice(options[action])
        elif action == 'ankan':payload['tile_type'] = rng.choice(options[action])
        elif action == 'kakan':payload['meld_index'] = rng.choice(options[action])['meld_index']
        state = apply_action(state,seat,action,payload,now)
    else:
        pytest.fail('Match did not reach settlement')


def test_result_timeout_never_deals_and_final_sticks_go_to_first():
    from dzmm_bot.core.mahjong_state import _finish_hand, apply_timeout
    state=new_match(ordered_wall(),NOW)
    _finish_hand(state,{'kind':'荒牌流局','deltas':[0]*4},False,NOW)
    assert state['deadline'] is None
    assert apply_timeout(state,NOW+timedelta(days=1),ordered_wall)==state
    state.update(hand_number=4,round_wind=27,points=[30000,24000,22000,23000],riichi_sticks=1)
    _finish_hand(state,{'kind':'荒牌流局','deltas':[0]*4},False,NOW)
    assert state['phase']=='match_finished'
    assert state['riichi_sticks']==0 and state['points'][0]==31000
    assert state['result']['riichi_recipient']==0
