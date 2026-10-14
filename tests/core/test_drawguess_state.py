from copy import deepcopy

import pytest

from dzmm_bot.core.drawguess_state import advance, apply_action, guess_score, new_state
from dzmm_bot.core.drawguess_words import WORDS


IDS = [word.id for word in WORDS]


def act(state, actor, action, payload=None, now=0, candidates=None):
    return apply_action(state, actor, action, payload or {}, now, candidates or IDS[:3])


def ready_lobby(count):
    state = new_state("p0", 0)
    for number in range(1, count):
        state = act(state, f"p{number}", "claim")
    for number in range(count):
        state = act(state, f"p{number}", "ready")
    return state


def choose_and_finish_turn(state, now, candidates, next_candidates):
    drawer = state["seats"][state["turn_index"] % len(state["seats"])]
    state = act(state, drawer, "choose", {"word_id": candidates[0]}, now, candidates)
    for player in state["seats"]:
        if player != drawer:
            state = act(state, player, "guess", {"text": state["answer"]}, now + 1, candidates)
    assert state["phase"] == "revealing"
    return advance(state, now + 5001, next_candidates)


def test_score_boundaries():
    assert guess_score(90_000) == 100
    assert guess_score(45_000) == 75
    assert guess_score(0) == 50
    assert guess_score(120_000) == 100
    assert guess_score(-1) == 50


@pytest.mark.parametrize(("count", "turns"), [(3, 6), (8, 16)])
def test_three_and_eight_players_draw_twice(count, turns):
    state = ready_lobby(count)
    original = deepcopy(state)
    state = act(state, "p0", "start", now=100, candidates=IDS[:3])
    assert original["phase"] == "waiting"
    drawers = []
    for turn in range(turns):
        drawers.append(state["seats"][state["turn_index"] % count])
        choices = IDS[turn * 3: turn * 3 + 3]
        following = IDS[(turn + 1) * 3: (turn + 2) * 3]
        state = choose_and_finish_turn(state, 1_000 + turn * 10_000, choices, following)
    assert drawers == [f"p{i}" for i in range(count)] * 2
    assert state["phase"] == "finished"
    assert [entry["rank"] for entry in state["ranking"]] == [1] * count


def test_start_requires_three_ready_players():
    state = ready_lobby(2)
    with pytest.raises(ValueError, match="三人"):
        act(state, "p0", "start")
    state = new_state("p0", 0)
    state = act(state, "p1", "claim")
    state = act(state, "p2", "claim")
    state = act(state, "p0", "ready")
    state = act(state, "p1", "ready")
    with pytest.raises(ValueError, match="准备"):
        act(state, "p0", "start")


def test_selection_and_drawing_timeouts_do_not_pause():
    state = ready_lobby(3)
    state = act(state, "p0", "start", now=1_000, candidates=IDS[:3])
    assert state["deadline_ms"] == 16_000
    state = advance(state, 16_000, IDS[:3])
    assert state["phase"] == "drawing"
    assert state["word_id"] == IDS[0]
    assert state["deadline_ms"] == 106_000
    state = advance(state, 106_000, IDS[3:6])
    assert state["phase"] == "revealing"
    assert state["deadline_ms"] == 111_000


def test_guess_permissions_scoring_and_early_reveal():
    state = ready_lobby(3)
    state = act(state, "p0", "start", now=0, candidates=IDS[:3])
    state = act(state, "p0", "choose", {"word_id": IDS[0]}, now=1_000, candidates=IDS[:3])
    answer = state["answer"]
    with pytest.raises(ValueError, match="画手"):
        act(state, "p0", "guess", {"text": answer}, now=2_000)
    with pytest.raises(ValueError, match="观众"):
        act(state, "viewer", "guess", {"text": answer}, now=2_000)
    unchanged = act(state, "p1", "guess", {"text": "错误答案"}, now=2_000)
    assert unchanged["scores"] == state["scores"]
    state = act(state, "p1", "guess", {"text": answer}, now=46_000)
    assert state["scores"] == {"p0": 20, "p1": 75, "p2": 0}
    with pytest.raises(ValueError, match="已经猜中"):
        act(state, "p1", "guess", {"text": answer}, now=47_000)
    state = act(state, "p2", "guess", {"text": answer}, now=90_999)
    assert state["phase"] == "revealing"
    assert state["scores"] == {"p0": 40, "p1": 75, "p2": 50}


def test_deadline_is_exclusive_for_actions():
    state = ready_lobby(3)
    state = act(state, "p0", "start", now=0, candidates=IDS[:3])
    with pytest.raises(ValueError, match="超时"):
        act(state, "p0", "choose", {"word_id": IDS[0]}, now=15_000, candidates=IDS[:3])
