"""Pure, copy-on-write rules. All times are absolute milliseconds."""
from copy import deepcopy

from .mistrealm_cards import CARDS, deck

FIELDS = {
    "join": {"uid"}, "select_faction": {"faction"}, "ready": set(), "unready": set(),
    "start": set(), "mulligan": {"cards"}, "reserve": {"card"},
    "play": {"card", "row", "targets"}, "leader": {"targets"}, "pass": set(),
    "concede": set(), "leave": set(), "rematch": set(),
}


def player(uid):
    return dict(uid=uid, faction="raven", ready=False, hand=[], deck=[], reserve=None,
                rows=[[], []], discard=[], passed=False, leader_used=False,
                mulligan_done=False, reserve_done=False, rematch=False, timeouts=0)


def new_state(host, now_ms):
    return dict(phase="waiting", version=0, players=[player(host), None],
                deadline_ms=now_ms+1800000, round=0, scores=[0, 0], results=[],
                turn=0, first=0, first_bonus=False, winner=None, reason=None)


def units(p):
    return [c for row in p["rows"] for c in row]


def injured(c):
    return c["power"] < CARDS[c["key"]]["power"]


def score(p):
    return sum(c["power"] for c in units(p))


def finish(s, winner, reason, now):
    s.update(phase="finished", winner=winner, reason=reason, deadline_ms=now+1800000)


def round_end(s, now):
    powers = [score(p) for p in s["players"]]
    winner = None if powers[0] == powers[1] else int(powers[1] > powers[0])
    for i in range(2):
        s["scores"][i] += 1 if winner is None else (2 if i == winner else 0)
    s["results"].append({"round": s["round"], "powers": powers, "winner": winner})
    for p in s["players"]:
        p["discard"].extend({"id": c["id"], "key": c["key"]} for c in units(p))
        p["rows"] = [[], []]
    if s["round"] == 3 or abs(s["scores"][0]-s["scores"][1]) > (3-s["round"])*2:
        result = None if s["scores"][0] == s["scores"][1] else int(s["scores"][1] > s["scores"][0])
        finish(s, result, "score", now)
    else:
        s["first"] = 1-s["first"] if winner is None else winner
        s.update(phase="round_result", deadline_ms=now+5000)


def after_turn(s, seat, now):
    if all(p["passed"] for p in s["players"]):
        round_end(s, now)
    else:
        s["turn"] = seat if s["players"][1-seat]["passed"] else 1-seat
        s["deadline_ms"] = now+45000


def deal(p, count):
    p["hand"].extend(p["deck"][:count])
    del p["deck"][:count]


def begin_round(s, now):
    s["round"] += 1
    for p in s["players"]:
        p["passed"] = False
        if s["round"] > 1:
            deal(p, 3)
        if s["round"] == 3:
            p["hand"].append(p["reserve"])
            p["reserve"] = None
    s.update(phase="playing", turn=s["first"], deadline_ms=now+45000)


def targets_for(s, seat, key, row, source_id=None):
    """Public UI hint and server validation share these exact target rules."""
    effect = CARDS[key]["effect"]
    friend = [c for c in units(s["players"][seat]) if c["id"] != source_id]
    enemy = units(s["players"][1-seat])
    if effect in ("damage2", "damage3", "assassin", "pierce"):
        return enemy, 1, 1
    if effect in ("buff3", "protect", "regent"):
        return friend, 1, 1
    if effect in ("buff3two", "buff2two"):
        return friend, 1, 2
    if effect == "commander":
        friends = [c for c in s["players"][seat]["rows"][row] if c["id"] != source_id]
        return (friends, 2, 2) if len(friends) >= 2 else ([], 0, 0)
    return [], 0, 0


def effect(s, seat, key, row, target_ids, source=None):
    if not isinstance(target_ids, list) or any(not isinstance(t, str) for t in target_ids):
        raise ValueError("目标格式不正确")
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("不能重复选择目标")
    card = CARDS[key]
    options, lo, hi = targets_for(s, seat, key, row, source["id"] if source else None)
    if not options:
        lo = hi = 0
        if card["type"] != "unit":
            raise ValueError("没有合法目标")
    if not lo <= len(target_ids) <= hi or any(t not in {c["id"] for c in options} for t in target_ids):
        raise ValueError("请选择合法目标")
    e = card["effect"]
    for t in [c for c in options if c["id"] in target_ids]:
        if e in ("damage2", "damage3", "assassin", "pierce"):
            damage = {"damage2": 2, "damage3": 3, "assassin": 4 if injured(t) else 2, "pierce": 5}[e]
            if e == "pierce":
                t["armor"] = 0
            absorbed = min(damage, t["armor"])
            t["armor"] -= absorbed
            t["power"] -= damage-absorbed
        else:
            t["power"] += 3 if e in ("buff3", "buff3two", "regent") else 2
            if e in ("protect", "regent"):
                t["armor"] += 2
    if source:
        if e == "armor":
            source["armor"] += 3
        elif e in ("hunter", "guide"):
            count = sum(injured(c) for c in units(s["players"][1-seat]))
            source["power"] += (3 if count else 0) if e == "hunter" else min(count, 3)
        elif e == "infantry" and len(s["players"][seat]["rows"][row]) > 1:
            source["power"] += 3
    for p in s["players"]:
        for cards in p["rows"]:
            for c in list(cards):
                if c["power"] <= 0:
                    p["discard"].append({"id": c["id"], "key": c["key"]})
                    cards.remove(c)


def apply_action(state, seat, action, payload, now_ms, rng):
    if type(seat) is not int or seat not in (0, 1):
        raise ValueError("席位不正确")
    if action not in FIELDS or not isinstance(payload, dict) or set(payload) != FIELDS[action]:
        raise ValueError("操作参数不正确")
    s = deepcopy(state)
    p = s["players"][seat]
    phase = s["phase"]
    if phase == "closed":
        raise ValueError("房间已关闭")
    if action == "join":
        if seat != 1 or p or phase != "waiting" or payload["uid"] == s["players"][0]["uid"]:
            raise ValueError("无法加入房间")
        s["players"][1] = player(payload["uid"])
    elif p is None:
        raise ValueError("尚未入座")
    elif action == "leave":
        if phase == "waiting" and seat == 1:
            s["players"][1] = None
            s["players"][0]["ready"] = False
        elif phase in ("waiting", "finished"):
            s.update(phase="closed", deadline_ms=None)
        else:
            finish(s, 1-seat, "concede", now_ms)
    elif action == "concede" and phase not in ("waiting", "finished"):
        finish(s, 1-seat, "concede", now_ms)
    elif phase == "waiting":
        if action == "select_faction":
            if payload["faction"] not in ("raven", "crown"):
                raise ValueError("阵营不正确")
            p.update(faction=payload["faction"], ready=False)
        elif action in ("ready", "unready"):
            p["ready"] = action == "ready"
        elif action == "start":
            if seat != 0 or not all(x and x["ready"] for x in s["players"]):
                raise ValueError("需要房主在双方准备后开始")
            for i, pp in enumerate(s["players"]):
                pp["deck"] = deck(pp["faction"], i)
                rng.shuffle(pp["deck"])
                deal(pp, 9)
            s.update(phase="mulligan", first=rng.randrange(2), deadline_ms=now_ms+45000, first_bonus=True)
        else:
            raise ValueError("当前阶段不能执行该操作")
    elif phase == "mulligan" and action == "mulligan":
        ids = payload["cards"]
        if p["mulligan_done"] or not isinstance(ids, list) or any(not isinstance(x, str) for x in ids) or len(ids) > 2 or len(set(ids)) != len(ids):
            raise ValueError("只能换0至2张牌一次")
        if any(x not in {c["id"] for c in p["hand"]} for x in ids):
            raise ValueError("手牌不存在")
        removed = [c for c in p["hand"] if c["id"] in ids]
        p["hand"] = [c for c in p["hand"] if c["id"] not in ids]
        deal(p, len(removed))
        p["deck"].extend(removed)
        rng.shuffle(p["deck"])
        p["mulligan_done"] = True
        if all(x["mulligan_done"] for x in s["players"]):
            s.update(phase="reserve", deadline_ms=now_ms+30000)
    elif phase == "reserve" and action == "reserve":
        card = next((c for c in p["hand"] if c["id"] == payload["card"]), None)
        if p["reserve_done"] or not card:
            raise ValueError("请选择一张手牌")
        p["hand"].remove(card)
        p.update(reserve=card, reserve_done=True)
        if all(x["reserve_done"] for x in s["players"]):
            begin_round(s, now_ms)
    elif phase == "playing":
        if s["turn"] != seat or p["passed"]:
            raise ValueError("还未轮到你行动")
        if action == "pass":
            p["passed"] = True
        elif action == "leader":
            if p["leader_used"]:
                raise ValueError("领袖能力本场已使用")
            key = "raven_king" if p["faction"] == "raven" else "crown_regent"
            effect(s, seat, key, 0, payload["targets"])
            p["leader_used"] = True
        elif action == "play":
            c = next((c for c in p["hand"] if c["id"] == payload["card"]), None)
            row = payload["row"]
            if not c or type(row) is not int or row not in (0, 1):
                raise ValueError("手牌或战列不正确")
            info = CARDS[c["key"]]
            source = None
            if info["type"] == "unit":
                if (info["row"] == "front" and row != 0) or (info["row"] == "back" and row != 1) or len(p["rows"][row]) >= 6:
                    raise ValueError("无法放入该战列")
                source = {**c, "power": info["power"], "armor": 0}
                p["rows"][row].append(source)
            effect(s, seat, c["key"], row, payload["targets"], source)
            p["hand"].remove(c)
            if info["type"] == "tactic":
                p["discard"].append(c)
            elif s["first_bonus"] and s["round"] == 1 and seat == s["first"]:
                source["power"] += 2
                s["first_bonus"] = False
        else:
            raise ValueError("当前阶段不能执行该操作")
        p["timeouts"] = 0
        after_turn(s, seat, now_ms)
    elif phase == "finished" and action == "rematch":
        p["rematch"] = True
        if all(x["rematch"] for x in s["players"]):
            old_players = s["players"]
            fresh = new_state(old_players[0]["uid"], now_ms)
            fresh["players"] = [player(x["uid"]) for x in old_players]
            for i in range(2):
                fresh["players"][i]["faction"] = old_players[i]["faction"]
            fresh["version"] = s["version"]
            s = fresh
    else:
        raise ValueError("当前阶段不能执行该操作")
    if p is not None and action in ("mulligan", "reserve"):
        p["timeouts"] = 0
    if s["phase"] == "waiting":
        s["deadline_ms"] = now_ms+1800000
    s["version"] += 1
    return s


def advance(state, now_ms, rng):
    s = deepcopy(state)
    for _ in range(64):
        deadline = s["deadline_ms"]
        if deadline is None or now_ms < deadline:
            return s
        phase = s["phase"]
        if phase in ("waiting", "finished"):
            s.update(phase="closed", deadline_ms=None, version=s["version"]+1)
        elif phase in ("mulligan", "reserve"):
            pending = [i for i, p in enumerate(s["players"]) if not p[phase+"_done"]]
            for i in pending:
                p = s["players"][i]
                data = {"cards": []} if phase == "mulligan" else {"card": rng.choice(p["hand"])["id"]}
                misses = p["timeouts"]+1
                s = apply_action(s, i, phase, data, deadline, rng)
                s["players"][i]["timeouts"] = misses
            expired = [i for i, p in enumerate(s["players"]) if p["timeouts"] >= 2]
            if expired:
                finish(s, None if len(expired) == 2 else 1-expired[0],
                       "cancelled" if len(expired) == 2 else "timeout", deadline)
        elif phase == "playing":
            seat = s["turn"]
            misses = s["players"][seat]["timeouts"]+1
            s = apply_action(s, seat, "pass", {}, deadline, rng)
            s["players"][seat]["timeouts"] = misses
            if misses >= 2:
                finish(s, 1-seat, "timeout", deadline)
        elif phase == "round_result":
            begin_round(s, deadline)
            s["version"] += 1
    raise ValueError("状态推进超过上限")


def project(state, seat):
    s = deepcopy(state)
    for i, p in enumerate(s["players"]):
        if p is None:
            continue
        p["hand_count"], p["deck_count"] = len(p["hand"]), len(p["deck"])
        p["reserve_count"] = int(p["reserve"] is not None)
        p["power"] = score(p)
        del p["deck"]
        if i != seat:
            p.pop("hand")
            p.pop("reserve")
    s["seat"] = seat
    return s
