"""Authoritative four-player riichi match transitions.

The reducer is deliberately pure: callers persist the returned JSON snapshot and
provide a freshly shuffled wall when a completed hand advances.  That keeps
concurrency and retries in the repository layer while making every rule
transition independently testable.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Callable

from .mahjong_rules import (
    HandContext,
    chi_choices,
    concealed_kan_types,
    distinct_terminal_honors,
    hand_value,
    is_closed,
    is_terminal_or_honor,
    open_kan_choices,
    pon_choices,
    tile_sort_key,
    tile_type,
    waits,
)


TURN_SECONDS = 15
REACTION_SECONDS = 5
INITIAL_TIME_BANK_MS = 60_000
RESULT_SECONDS = 8
DEAD_WALL_SIZE = 14
RINSHAN_INDEXES = (0, 1, 2, 3)
DORA_INDEXES = (4, 6, 8, 10, 12)
URA_INDEXES = (5, 7, 9, 11, 13)


def _stamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("时间必须包含时区")
    return value.astimezone(timezone.utc).isoformat()


def _deadline(now: datetime, seconds: int) -> str:
    return _stamp(now + timedelta(seconds=seconds))


def _validate_wall(wall: list[int]) -> None:
    if len(wall) != 136 or set(wall) != set(range(136)):
        raise ValueError("牌山必须包含136张不同的麻将牌")


def new_match(wall: list[int], now: datetime, *, mode: str = "east") -> dict:
    if mode not in {"east", "south"}:
        raise ValueError("只支持东风战或半庄战")
    _validate_wall(wall)
    state = {
        "schema": 1,
        "mode": mode,
        "phase": "between_hands",
        "version": 0,
        "points": [25_000] * 4,
        "dealer": 0,
        "round_wind": 27,
        "hand_number": 1,
        "honba": 0,
        "riichi_sticks": 0,
        "initial_dealer": 0,
        "result": None,
        "history": [],
    }
    return _deal_hand(state, wall, now)


def _deal_hand(match: dict, wall: list[int], now: datetime) -> dict:
    _validate_wall(wall)
    result = deepcopy(match)
    live = list(wall[:-DEAD_WALL_SIZE])
    hands = [sorted(live[seat * 13:(seat + 1) * 13], key=tile_sort_key) for seat in range(4)]
    live = live[52:]
    dealer = result["dealer"]
    drawn = live.pop(0)
    hands[dealer].append(drawn)
    hands[dealer].sort(key=tile_sort_key)
    result.update(
        phase="playing",
        hands=hands,
        melds=[[], [], [], []],
        discards=[[], [], [], []],
        wall=live,
        dead_wall=list(wall[-DEAD_WALL_SIZE:]),
        live_trim=0,
        rinshan_draws=0,
        kan_count=0,
        kan_by_player=[0, 0, 0, 0],
        turn=dealer,
        drawn_tile=drawn,
        turn_started_at=_stamp(now),
        deadline=_deadline(now, TURN_SECONDS + INITIAL_TIME_BANK_MS // 1000),
        time_bank_ms=[INITIAL_TIME_BANK_MS] * 4,
        riichi=[False] * 4,
        double_riichi=[False] * 4,
        ippatsu=[False] * 4,
        temporary_furiten=[False] * 4,
        turn_counts=[0] * 4,
        any_call=False,
        pending=None,
        last_draw_rinshan=False,
        result=None,
    )
    return result


def _visible_dora(state: dict) -> tuple[int, ...]:
    return tuple(state["dead_wall"][index] for index in DORA_INDEXES[: state["kan_count"] + 1])


def _visible_ura(state: dict) -> tuple[int, ...]:
    return tuple(state["dead_wall"][index] for index in URA_INDEXES[: state["kan_count"] + 1])


def _seat_wind(state: dict, seat: int) -> int:
    return 27 + ((seat - state["dealer"]) % 4)


def _context(state: dict, seat: int, *, tsumo: bool, chankan: bool = False) -> HandContext:
    remaining = _remaining_draws(state)
    return HandContext(
        tsumo=tsumo,
        riichi=state["riichi"][seat],
        double_riichi=state["double_riichi"][seat],
        ippatsu=state["ippatsu"][seat],
        rinshan=tsumo and state.get("last_draw_rinshan", False),
        chankan=chankan,
        haitei=tsumo and remaining == 0,
        houtei=not tsumo and remaining == 0,
        tenhou=tsumo and seat == state["dealer"] and state["turn_counts"][seat] == 0 and not state["any_call"],
        chiihou=tsumo and seat != state["dealer"] and state["turn_counts"][seat] == 0 and not state["any_call"],
        player_wind=_seat_wind(state, seat),
        round_wind=state["round_wind"],
        honba=state["honba"],
        riichi_sticks=state["riichi_sticks"],
        dora_indicators=_visible_dora(state),
        ura_indicators=_visible_ura(state),
    )


def _value_for(state: dict, seat: int, win_tile: int, *, tsumo: bool, chankan: bool = False):
    concealed = list(state["hands"][seat])
    if not tsumo:
        concealed.append(win_tile)
        concealed.sort(key=tile_sort_key)
    return hand_value(concealed, win_tile, state["melds"][seat], _context(state, seat, tsumo=tsumo, chankan=chankan))


def _can_ron(state: dict, seat: int, tile: int, *, chankan: bool = False) -> bool:
    if state["temporary_furiten"][seat]:
        return False
    wanted = waits(state["hands"][seat], state["melds"][seat])
    if tile_type(tile) not in wanted:
        return False
    own_discards = {tile_type(item["tile"]) for item in state["discards"][seat]}
    if wanted & own_discards:
        return False
    return _value_for(state, seat, tile, tsumo=False, chankan=chankan).error is None


def _remaining_draws(state: dict) -> int:
    return max(0, len(state["wall"]) - state.get("live_trim", 0))


def action_options(state: dict, seat: int) -> dict:
    if seat not in range(4):
        return {}
    if state["phase"] == "reaction" and state["pending"]:
        return deepcopy(state["pending"]["eligible"].get(str(seat), {}))
    if state["phase"] != "playing" or state["turn"] != seat:
        return {}
    hand = state["hands"][seat]
    result: dict = {"discard": list(hand)}
    drawn = state.get("drawn_tile")
    if drawn is not None and _value_for(state, seat, drawn, tsumo=True).error is None:
        result["tsumo"] = True
    if not state["riichi"][seat] and is_closed(state["melds"][seat]) and state["points"][seat] >= 1000:
        candidates = []
        for tile in hand:
            reduced = list(hand)
            reduced.remove(tile)
            if waits(reduced, state["melds"][seat]):
                candidates.append(tile)
        if candidates:
            result["riichi"] = sorted(set(candidates), key=tile_sort_key)
    kans = sorted(concealed_kan_types(hand))
    if kans:
        result["ankan"] = kans
    kakan = []
    kinds = {tile_type(tile) for tile in hand}
    for index, meld in enumerate(state["melds"][seat]):
        if meld["kind"] == "pon" and tile_type(meld["tiles"][0]) in kinds:
            kakan.append({"meld_index": index, "tile_type": tile_type(meld["tiles"][0])})
    if kakan:
        result["kakan"] = kakan
    if (
        state["turn_counts"][seat] == 0
        and not state["any_call"]
        and distinct_terminal_honors(hand) >= 9
    ):
        result["kyuushu"] = True
    return result


def apply_action(state: dict, seat: int, action: str, payload: dict, now: datetime) -> dict:
    if seat not in range(4):
        raise ValueError("无效席位")
    if payload.get("version") != state.get("version"):
        raise ValueError("牌局版本已更新，请刷新")
    if state["phase"] not in {"playing", "reaction"}:
        raise ValueError("当前不能操作")
    if datetime.fromisoformat(state["deadline"]) <= now:
        raise ValueError("操作已超时，请刷新")
    result = deepcopy(state)
    if result["phase"] == "reaction":
        _reaction_action(result, seat, action, payload, now)
    else:
        _turn_action(result, seat, action, payload, now)
    result["version"] += 1
    return result


def _turn_action(state: dict, seat: int, action: str, payload: dict, now: datetime) -> None:
    if state["turn"] != seat:
        raise ValueError("还没有轮到你")
    _consume_time(state, seat, now)
    if action in {"discard", "riichi"}:
        _discard(state, seat, payload.get("tile"), action == "riichi", now)
    elif action == "tsumo":
        tile = state.get("drawn_tile")
        if tile is None:
            raise ValueError("当前不能自摸")
        value = _value_for(state, seat, tile, tsumo=True)
        if value.error:
            raise ValueError("当前不能和牌")
        _settle_win(state, [seat], None, tile, now, tsumo=True)
    elif action == "ankan":
        _ankan(state, seat, payload.get("tile_type"), now)
    elif action == "kakan":
        _kakan(state, seat, payload.get("meld_index"), now)
    elif action == "kyuushu":
        if not action_options(state, seat).get("kyuushu"):
            raise ValueError("当前不能九种九牌")
        _abortive_draw(state, "九种九牌", now)
    else:
        raise ValueError("无效操作")


def _consume_time(state: dict, seat: int, now: datetime) -> None:
    started = datetime.fromisoformat(state["turn_started_at"])
    elapsed_ms = max(0, int((now - started).total_seconds() * 1000))
    state["time_bank_ms"][seat] = max(0, state["time_bank_ms"][seat] - max(0, elapsed_ms - TURN_SECONDS * 1000))


def _discard(state: dict, seat: int, tile, declaring_riichi: bool, now: datetime) -> None:
    if type(tile) is not int or tile not in state["hands"][seat]:
        raise ValueError("只能打出自己的牌")
    if state["riichi"][seat] and tile != state.get("drawn_tile"):
        raise ValueError("立直后只能摸切")
    state["hands"][seat].remove(tile)
    if declaring_riichi:
        if state["riichi"][seat] or not is_closed(state["melds"][seat]) or state["points"][seat] < 1000:
            raise ValueError("当前不能立直")
        if not waits(state["hands"][seat], state["melds"][seat]):
            raise ValueError("打出这张牌后没有听牌")
        state["riichi"][seat] = True
        state["double_riichi"][seat] = state["turn_counts"][seat] == 0 and not state["any_call"]
        state["ippatsu"][seat] = True
        state["points"][seat] -= 1000
        state["riichi_sticks"] += 1
    state["discards"][seat].append({"tile": tile, "called": False, "riichi": declaring_riichi})
    state["turn_counts"][seat] += 1
    state["drawn_tile"] = None
    state["last_draw_rinshan"] = False
    pending = _discard_reactions(state, seat, tile, now)
    if pending:
        state.update(phase="reaction", pending=pending, deadline=_deadline(now, REACTION_SECONDS))
        return
    _after_unclaimed_discard(state, seat, tile, now)


def _discard_reactions(state: dict, source: int, tile: int, now: datetime) -> dict | None:
    eligible: dict[str, dict] = {}
    for seat in range(4):
        if seat == source:
            continue
        options: dict = {}
        if _can_ron(state, seat, tile):
            options["ron"] = True
        pon = pon_choices(state["hands"][seat], tile)
        if pon and not state["riichi"][seat]:
            options["pon"] = pon
        kan = open_kan_choices(state["hands"][seat], tile)
        if kan and not state["riichi"][seat] and _remaining_draws(state) > 0:
            options["kan"] = kan
        if seat == (source + 1) % 4 and not state["riichi"][seat]:
            chi = chi_choices(state["hands"][seat], tile)
            if chi:
                options["chi"] = chi
        if options:
            options["pass"] = True
            eligible[str(seat)] = options
    if not eligible:
        return None
    return {
        "kind": "discard",
        "source": source,
        "tile": tile,
        "eligible": eligible,
        "decisions": {},
        "at": _stamp(now),
    }


def _reaction_action(state: dict, seat: int, action: str, payload: dict, now: datetime) -> None:
    pending = state["pending"]
    options = pending["eligible"].get(str(seat))
    if not options or str(seat) in pending["decisions"]:
        raise ValueError("当前没有可响应的操作")
    if action not in options:
        raise ValueError("当前不能执行此操作")
    decision: dict = {"action": action}
    if action in {"chi", "pon", "kan"}:
        selected = payload.get("tiles")
        if not isinstance(selected, list) or selected not in options[action]:
            raise ValueError("副露选择无效")
        decision["tiles"] = selected
    if action == "pass" and options.get("ron"):
        state["temporary_furiten"][seat] = True
    pending["decisions"][str(seat)] = decision
    if len(pending["decisions"]) == len(pending["eligible"]):
        _resolve_reactions(state, now)


def _resolve_reactions(state: dict, now: datetime) -> None:
    pending = state["pending"]
    source = pending["source"]
    tile = pending["tile"]
    rons = [int(seat) for seat, value in pending["decisions"].items() if value["action"] == "ron"]
    rons.sort(key=lambda seat: (seat - source) % 4)
    if len(rons) >= 3:
        _abortive_draw(state, "三家和", now)
        return
    if rons:
        _settle_win(state, rons, source, tile, now, tsumo=False, chankan=pending["kind"] == "kakan")
        return
    if pending["kind"] == "kakan":
        _finish_kakan(state, now)
        return
    calls = []
    priority = {"kan": 2, "pon": 2, "chi": 1}
    for raw_seat, value in pending["decisions"].items():
        if value["action"] in priority:
            seat = int(raw_seat)
            calls.append((priority[value["action"]], -((seat - source) % 4), seat, value))
    if calls:
        _, _, caller, decision = max(calls)
        _apply_call(state, caller, source, tile, decision, now)
        return
    state["pending"] = None
    _after_unclaimed_discard(state, source, tile, now)


def _after_unclaimed_discard(state: dict, source: int, tile: int, now: datetime) -> None:
    if _four_winds(state):
        _abortive_draw(state, "四风连打", now)
        return
    if all(state["riichi"]):
        _abortive_draw(state, "四家立直", now)
        return
    _draw_for(state, (source + 1) % 4, now)


def _draw_for(state: dict, seat: int, now: datetime, *, rinshan: bool = False) -> None:
    if rinshan:
        index = state["rinshan_draws"]
        if index >= len(RINSHAN_INDEXES):
            _abortive_draw(state, "四杠散了", now)
            return
        tile = state["dead_wall"][RINSHAN_INDEXES[index]]
        state["rinshan_draws"] += 1
        state["live_trim"] += 1
    else:
        if _remaining_draws(state) <= 0:
            _exhaustive_draw(state, now)
            return
        tile = state["wall"].pop(0)
    state["hands"][seat].append(tile)
    state["hands"][seat].sort(key=tile_sort_key)
    state.update(
        phase="playing",
        pending=None,
        turn=seat,
        drawn_tile=tile,
        turn_started_at=_stamp(now),
        deadline=_deadline(now, TURN_SECONDS + state["time_bank_ms"][seat] // 1000),
        last_draw_rinshan=rinshan,
    )
    if not state["riichi"][seat]:
        state["temporary_furiten"][seat] = False


def _apply_call(state: dict, caller: int, source: int, tile: int, decision: dict, now: datetime) -> None:
    action = decision["action"]
    selected = decision["tiles"]
    for item in selected:
        state["hands"][caller].remove(item)
    state["discards"][source][-1]["called"] = True
    state["melds"][caller].append({
        "kind": action,
        "tiles": sorted([*selected, tile], key=tile_sort_key),
        "open": True,
        "called_tile": tile,
        "from": source,
    })
    state["any_call"] = True
    state["ippatsu"] = [False] * 4
    state["pending"] = None
    if action == "kan":
        state["kan_count"] += 1
        state["kan_by_player"][caller] += 1
        if _four_kans_abort(state):
            _abortive_draw(state, "四杠散了", now)
        else:
            _draw_for(state, caller, now, rinshan=True)
        return
    state.update(
        phase="playing",
        turn=caller,
        drawn_tile=None,
        turn_started_at=_stamp(now),
        deadline=_deadline(now, TURN_SECONDS + state["time_bank_ms"][caller] // 1000),
        last_draw_rinshan=False,
    )


def _ankan(state: dict, seat: int, kind, now: datetime) -> None:
    if type(kind) is not int or kind not in concealed_kan_types(state["hands"][seat]):
        raise ValueError("当前不能暗杠")
    matching = [tile for tile in state["hands"][seat] if tile_type(tile) == kind]
    if state["riichi"][seat]:
        before = waits([tile for tile in state["hands"][seat] if tile != state["drawn_tile"]], state["melds"][seat])
        after_hand = list(state["hands"][seat])
        for tile in matching:
            after_hand.remove(tile)
        after_melds = [*state["melds"][seat], {"kind": "ankan", "tiles": matching, "open": False}]
        if waits(after_hand, after_melds) != before:
            raise ValueError("立直后不能改变听牌暗杠")
    for tile in matching:
        state["hands"][seat].remove(tile)
    state["melds"][seat].append({"kind": "ankan", "tiles": matching, "open": False, "from": seat})
    state["kan_count"] += 1
    state["kan_by_player"][seat] += 1
    state["any_call"] = True
    state["ippatsu"] = [False] * 4
    if _four_kans_abort(state):
        _abortive_draw(state, "四杠散了", now)
    else:
        _draw_for(state, seat, now, rinshan=True)


def _kakan(state: dict, seat: int, meld_index, now: datetime) -> None:
    if type(meld_index) is not int or not 0 <= meld_index < len(state["melds"][seat]):
        raise ValueError("加杠选择无效")
    meld = state["melds"][seat][meld_index]
    if meld["kind"] != "pon":
        raise ValueError("只能对碰牌加杠")
    kind = tile_type(meld["tiles"][0])
    extra = next((tile for tile in state["hands"][seat] if tile_type(tile) == kind), None)
    if extra is None:
        raise ValueError("缺少加杠牌")
    eligible = {}
    for other in range(4):
        if other != seat and _can_ron(state, other, extra, chankan=True):
            eligible[str(other)] = {"ron": True, "pass": True}
    if not eligible:
        state["pending"] = {"kind": "kakan", "source": seat, "tile": extra, "meld_index": meld_index,
                            "eligible": {}, "decisions": {}, "at": _stamp(now)}
        _finish_kakan(state, now)
        return
    state.update(
        phase="reaction",
        pending={"kind": "kakan", "source": seat, "tile": extra, "meld_index": meld_index,
                 "eligible": eligible, "decisions": {}, "at": _stamp(now)},
        deadline=_deadline(now, REACTION_SECONDS),
    )


def _finish_kakan(state: dict, now: datetime) -> None:
    pending = state["pending"]
    seat = pending["source"]
    tile = pending["tile"]
    index = pending["meld_index"]
    state["hands"][seat].remove(tile)
    meld = state["melds"][seat][index]
    meld.update(kind="kakan", tiles=sorted([*meld["tiles"], tile], key=tile_sort_key))
    state["pending"] = None
    state["kan_count"] += 1
    state["kan_by_player"][seat] += 1
    state["any_call"] = True
    state["ippatsu"] = [False] * 4
    if _four_kans_abort(state):
        _abortive_draw(state, "四杠散了", now)
    else:
        _draw_for(state, seat, now, rinshan=True)


def _settle_win(
    state: dict,
    winners: list[int],
    loser: int | None,
    win_tile: int,
    now: datetime,
    *,
    tsumo: bool,
    chankan: bool = False,
) -> None:
    deltas = [0, 0, 0, 0]
    details = []
    for winner in winners:
        value = _value_for(state, winner, win_tile, tsumo=tsumo, chankan=chankan)
        if value.error:
            raise ValueError("当前不能和牌")
        if tsumo:
            for seat in range(4):
                if seat == winner:
                    continue
                amount = value.main if winner == state["dealer"] or seat == state["dealer"] else value.additional
                amount += state["honba"] * 100
                deltas[seat] -= amount
                deltas[winner] += amount
        else:
            assert loser is not None
            amount = value.main + state["honba"] * 300
            deltas[loser] -= amount
            deltas[winner] += amount
        details.append({
            "seat": winner,
            "han": value.han,
            "fu": value.fu,
            "yaku": list(value.yaku),
            "limit": value.limit,
        })
    if state["riichi_sticks"]:
        deltas[winners[0]] += state["riichi_sticks"] * 1000
        state["riichi_sticks"] = 0
    for seat, amount in enumerate(deltas):
        state["points"][seat] += amount
    _finish_hand(
        state,
        {
            "kind": "tsumo" if tsumo else "ron",
            "winners": winners,
            "loser": loser,
            "tile": win_tile,
            "deltas": deltas,
            "details": details,
        },
        state["dealer"] in winners,
        now,
    )


def _exhaustive_draw(state: dict, now: datetime) -> None:
    nagashi = [
        seat for seat in range(4)
        if state["discards"][seat]
        and all(is_terminal_or_honor(item["tile"]) and not item["called"] for item in state["discards"][seat])
    ]
    if nagashi:
        deltas = [0, 0, 0, 0]
        for winner in nagashi:
            for seat in range(4):
                if seat == winner:
                    continue
                amount = 4000 if winner == state["dealer"] or seat == state["dealer"] else 2000
                deltas[seat] -= amount
                deltas[winner] += amount
        for seat, amount in enumerate(deltas):
            state["points"][seat] += amount
        _finish_hand(state, {"kind": "流局满贯", "winners": nagashi, "deltas": deltas}, state["dealer"] in nagashi, now)
        return
    tenpai = [seat for seat in range(4) if waits(state["hands"][seat], state["melds"][seat])]
    deltas = [0, 0, 0, 0]
    if 0 < len(tenpai) < 4:
        gain = 3000 // len(tenpai)
        loss = 3000 // (4 - len(tenpai))
        for seat in range(4):
            deltas[seat] = gain if seat in tenpai else -loss
            state["points"][seat] += deltas[seat]
    _finish_hand(
        state,
        {"kind": "荒牌流局", "tenpai": tenpai, "deltas": deltas},
        state["dealer"] in tenpai,
        now,
    )


def _abortive_draw(state: dict, reason: str, now: datetime) -> None:
    _finish_hand(state, {"kind": "途中流局", "reason": reason, "deltas": [0, 0, 0, 0]}, True, now)


def _finish_hand(state: dict, result: dict, dealer_continues: bool, now: datetime) -> None:
    result = {**result, "dealer_continues": dealer_continues, "at": _stamp(now)}
    state["history"] = [*state.get("history", []), result][-32:]
    state.update(
        phase="hand_finished",
        pending=None,
        drawn_tile=None,
        deadline=_deadline(now, RESULT_SECONDS),
        result=result,
        next={"dealer_continues": dealer_continues},
    )
    if any(points < 0 for points in state["points"]):
        _finish_match(state, now, "击飞")


def _finish_match(state: dict, now: datetime, reason: str) -> None:
    order = sorted(range(4), key=lambda seat: (-state["points"][seat], (seat - state["initial_dealer"]) % 4))
    state.update(
        phase="match_finished",
        deadline=None,
        pending=None,
        result={"kind": "match", "reason": reason, "order": order, "points": list(state["points"]), "at": _stamp(now)},
    )


def advance_after_result(state: dict, wall: list[int], now: datetime) -> dict:
    if state["phase"] == "match_finished":
        return deepcopy(state)
    if state["phase"] != "hand_finished":
        raise ValueError("当前不在局间结算")
    if now < datetime.fromisoformat(state["deadline"]):
        return deepcopy(state)
    result = deepcopy(state)
    dealer_continues = result["next"]["dealer_continues"]
    if dealer_continues:
        result["honba"] += 1
    else:
        result["honba"] = 0
        result["dealer"] = (result["dealer"] + 1) % 4
        result["hand_number"] += 1
        if result["hand_number"] > 4:
            result["hand_number"] = 1
            result["round_wind"] += 1
    if _match_should_end(result):
        _finish_match(result, now, "终局")
        result["version"] += 1
        return result
    result.pop("next", None)
    return _deal_hand(result, wall, now) | {"version": result["version"] + 1}


def _match_should_end(state: dict) -> bool:
    target_wind = 27 if state["mode"] == "east" else 28
    if state["round_wind"] <= target_wind:
        return False
    if max(state["points"]) >= 30_000:
        return True
    return state["round_wind"] > target_wind + 1


def apply_timeout(state: dict, now: datetime, wall_factory: Callable[[], list[int]]) -> dict:
    if state.get("deadline") is None or now < datetime.fromisoformat(state["deadline"]):
        return deepcopy(state)
    if state["phase"] == "hand_finished":
        return advance_after_result(state, wall_factory(), now)
    result = deepcopy(state)
    if result["phase"] == "reaction":
        pending = result["pending"]
        for seat, options in pending["eligible"].items():
            if seat not in pending["decisions"]:
                if options.get("ron"):
                    result["temporary_furiten"][int(seat)] = True
                pending["decisions"][seat] = {"action": "pass"}
        _resolve_reactions(result, now)
    elif result["phase"] == "playing":
        seat = result["turn"]
        result["time_bank_ms"][seat] = 0
        tile = result.get("drawn_tile")
        if tile is None:
            tile = result["hands"][seat][-1]
        _discard(result, seat, tile, False, now)
    result["version"] += 1
    return result


def _four_winds(state: dict) -> bool:
    if state["any_call"] or any(len(items) != 1 for items in state["discards"]):
        return False
    kinds = [tile_type(items[0]["tile"]) for items in state["discards"]]
    return kinds[0] in range(27, 31) and len(set(kinds)) == 1


def _four_kans_abort(state: dict) -> bool:
    return state["kan_count"] >= 4 and sum(value > 0 for value in state["kan_by_player"]) > 1
