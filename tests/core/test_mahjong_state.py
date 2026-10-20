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
