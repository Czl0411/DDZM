"""Pure state transitions for the group draw-and-guess game."""

from copy import deepcopy
from math import floor

from .drawguess_words import validate_candidates, word_by_id, word_matches


def guess_score(remaining_ms: int) -> int:
    remaining = max(0, min(90_000, int(remaining_ms)))
    return 50 + floor(50 * remaining / 90_000)


def new_state(host: str, now_ms: int) -> dict:
    if not isinstance(host, str) or not host:
        raise ValueError("房主不能为空")
    return {
        "phase": "waiting", "seats": [host], "ready": [False], "host": host,
        "scores": {host: 0}, "match_id": 0, "turn_id": 0, "turn_index": 0,
        "candidates": [], "word_id": None, "answer": None, "guessed": [],
        "used_words": [], "deadline_ms": int(now_ms) + 600_000, "version": 0,
        "chat_version": 0,
        "ranking": [], "turn_points": {},
    }


def _drawer(state: dict) -> str:
    return state["seats"][state["turn_index"] % len(state["seats"])]


def _timed_out(state: dict, now_ms: int) -> bool:
    return state["phase"] in {"selecting", "drawing", "revealing"} and now_ms >= state["deadline_ms"]


def apply_action(state: dict, actor: str, action: str, payload: dict,
                 now_ms: int, candidates: list[str]) -> dict:
    if _timed_out(state, now_ms):
        raise ValueError("操作已超时，请刷新")
    result = deepcopy(state)
    if state["phase"] == "waiting":
        _waiting_action(result, actor, action, candidates, now_ms)
    elif state["phase"] == "selecting":
        if action != "choose" or actor != _drawer(state):
            raise ValueError("只有画手可以选词")
        word_id = payload.get("word_id")
        if word_id not in state["candidates"]:
            raise ValueError("请选择候选词")
        _begin_drawing(result, word_id, now_ms)
    elif state["phase"] == "drawing":
        if action != "guess":
            raise ValueError("当前只能猜词")
        _guess(result, actor, payload.get("text"), now_ms)
    else:
        raise ValueError("本局当前不能操作")
    result["version"] += 1
    return result


def _waiting_action(state: dict, actor: str, action: str,
                    candidates: list[str], now_ms: int) -> None:
    if action == "claim":
        if actor in state["seats"]:
            return
        if len(state["seats"]) >= 8:
            raise ValueError("房间已经坐满")
        state["seats"].append(actor)
        state["ready"].append(False)
        state["scores"][actor] = 0
        return
    if actor not in state["seats"]:
        raise ValueError("观众不能操作")
    seat = state["seats"].index(actor)
    if action in {"ready", "unready"}:
        state["ready"][seat] = action == "ready"
        return
    if action == "leave":
        state["seats"].pop(seat)
        state["ready"].pop(seat)
        state["scores"].pop(actor, None)
        if actor == state["host"] and state["seats"]:
            state["host"] = state["seats"][0]
        if not state["seats"]:
            state["phase"] = "closed"
        return
    if action != "start" or actor != state["host"]:
        raise ValueError("只有房主可以开始")
    if len(state["seats"]) < 3:
        raise ValueError("至少需要三人")
    if not all(state["ready"]):
        raise ValueError("所有玩家准备后才能开始")
    state["scores"] = {player: 0 for player in state["seats"]}
    state["match_id"] += 1
    state["turn_index"] = 0
    state["used_words"] = []
    _begin_selecting(state, candidates, now_ms)


def _begin_selecting(state: dict, candidates: list[str], now_ms: int) -> None:
    state["candidates"] = validate_candidates(candidates, set(state["used_words"]))
    state["turn_id"] += 1
    state["phase"] = "selecting"
    state["word_id"] = None
    state["answer"] = None
    state["guessed"] = []
    state["turn_points"] = {}
    state["deadline_ms"] = int(now_ms) + 15_000


def _begin_drawing(state: dict, word_id: str, now_ms: int) -> None:
    word = word_by_id(word_id)
    state["phase"] = "drawing"
    state["word_id"] = word_id
    state["answer"] = word.answer
    state["used_words"].append(word_id)
    state["deadline_ms"] = int(now_ms) + 90_000


def _guess(state: dict, actor: str, text: object, now_ms: int) -> None:
    if actor not in state["seats"]:
        raise ValueError("观众不能猜词")
    if actor == _drawer(state):
        raise ValueError("画手不能猜词")
    if actor in state["guessed"]:
        raise ValueError("你已经猜中")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("请输入答案")
    if not word_matches(state["word_id"], text):
        return
    points = guess_score(state["deadline_ms"] - int(now_ms))
    drawer = _drawer(state)
    state["guessed"].append(actor)
    state["scores"][actor] += points
    state["scores"][drawer] += 20
    state["turn_points"][actor] = points
    state["turn_points"][drawer] = state["turn_points"].get(drawer, 0) + 20
    if len(state["guessed"]) == len(state["seats"]) - 1:
        state["phase"] = "revealing"
        state["deadline_ms"] = int(now_ms) + 5_000


def advance(state: dict, now_ms: int, candidates: list[str]) -> dict:
    result = deepcopy(state)
    if result["phase"] == "waiting" and now_ms >= result["deadline_ms"]:
        result["phase"] = "closed"
    elif result["phase"] == "selecting" and now_ms >= result["deadline_ms"]:
        _begin_drawing(result, result["candidates"][0], result["deadline_ms"])
    elif result["phase"] == "drawing" and now_ms >= result["deadline_ms"]:
        result["phase"] = "revealing"
        result["deadline_ms"] += 5_000
    elif result["phase"] == "revealing" and now_ms >= result["deadline_ms"]:
        result["turn_index"] += 1
        if result["turn_index"] >= len(result["seats"]) * 2:
            result["phase"] = "finished"
            result["deadline_ms"] = None
            result["ranking"] = _ranking(result)
        else:
            _begin_selecting(result, candidates, result["deadline_ms"])
    if result != state:
        result["version"] += 1
    return result


def _ranking(state: dict) -> list[dict]:
    ordered = sorted(state["seats"], key=lambda player: (-state["scores"][player], state["seats"].index(player)))
    ranking = []
    previous_score = None
    rank = 0
    for position, player in enumerate(ordered, 1):
        score = state["scores"][player]
        if score != previous_score:
            rank = position
            previous_score = score
        ranking.append({"player": player, "score": score, "rank": rank})
    return ranking
