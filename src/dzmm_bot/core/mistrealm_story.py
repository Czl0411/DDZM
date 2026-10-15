"""Five deterministic single-player chapters built on the Classic rules engine."""
from copy import deepcopy

from . import mistrealm_classic_state as classic
from .mistrealm_classic_cards import CLASSIC_CARDS, STARTER_DECKS


CHAPTERS = (
    dict(id=1, title="雾门初启", summary="在边境哨站学会保存手牌。", enemy="守门人·洛恩", deck=0, difficulty=0),
    dict(id=2, title="群鸦来信", summary="识破间谍与医师组成的消耗战。", enemy="密令使·维鸦", deck=2, difficulty=1),
    dict(id=3, title="白枝伏雪", summary="面对召集军团与多排调度。", enemy="雪线猎手·芙蕾", deck=4, difficulty=1),
    dict(id=4, title="荒棘夜行", summary="阻止兽群在同一回合铺满战场。", enemy="群巢之母", deck=6, difficulty=2),
    dict(id=5, title="镜湖终局", summary="穿过仪式与蜕变，夺回最后的王冠。", enemy="镜湖女祭司", deck=8, difficulty=2),
)


def chapter(number):
    if type(number) is not int or not 1 <= number <= len(CHAPTERS):
        raise ValueError("剧情关卡不存在")
    return CHAPTERS[number - 1]


def public_chapters(completed):
    done = {int(value) for value in completed if type(value) is int}
    unlocked = min(len(CHAPTERS), max(done, default=0) + 1)
    return {
        "completed": sorted(done),
        "unlocked": unlocked,
        "chapters": [
            {key: value for key, value in item.items() if key not in ("deck", "difficulty")}
            | {"locked": item["id"] > unlocked, "completed": item["id"] in done}
            for item in CHAPTERS
        ],
    }


def new_story_state(uid, player_deck, chapter_number, now_ms, rng):
    item = chapter(chapter_number)
    enemy_deck = deepcopy(STARTER_DECKS[item["deck"]])
    state = classic.new_state(uid, player_deck, now_ms)
    state.update(
        mode="story",
        story={
            "chapter": item["id"],
            "title": item["title"],
            "summary": item["summary"],
            "enemy_name": item["enemy"],
        },
    )
    state = classic.apply_action(
        state,
        1,
        "join",
        {"uid": f"mistrealm-story-{chapter_number}", "deck": enemy_deck},
        now_ms,
        rng,
    )
    state = classic.apply_action(state, 0, "lock", {}, now_ms, rng)
    state = classic.apply_action(state, 1, "lock", {}, now_ms, rng)
    return drive(state, now_ms, rng, item["difficulty"])


def _card_value(card):
    definition = CLASSIC_CARDS[card["card"]]
    value = definition["power"]
    for ability in definition["abilities"]:
        value += {
            "spy": 8,
            "medic": 6,
            "muster": 5,
            "bond": 3,
            "morale": 3,
            "unit_horn": 4,
            "scorch": 7,
            "scorch_melee": 5,
            "scorch_siege": 5,
            "horn": 5,
            "weather_melee": 2,
            "weather_ranged": 2,
            "weather_siege": 2,
            "clear": 2,
            "decoy": 3,
            "ritual": 4,
        }.get(ability, 0)
    return value


def _pick_play(state, moves, difficulty):
    player = state["players"][1]
    by_id = {card["id"]: card for card in player["hand"]}
    candidates = [move for move in moves if move["action"] == "play"]
    candidates.sort(key=lambda move: (_card_value(by_id[move["payload"]["card"]]), move["payload"]["row"]))
    if difficulty == 0:
        return candidates[0]
    if difficulty == 1:
        return candidates[len(candidates) // 2]
    return candidates[-1]


def _waiting_for_player(state):
    if state["phase"] == "choose_first":
        return state["chooser"] == 0
    if state["phase"] == "mulligan":
        return not state["players"][0]["mulligan_done"]
    if state["phase"] == "playing":
        pending = state.get("pending")
        return (pending and pending["actor"] == 0) or (not pending and state["turn"] == 0)
    return False


def drive(state, now_ms, rng, difficulty=None):
    """Resolve AI-only decisions and stop as soon as the human can act."""
    if state.get("mode") != "story":
        return state
    level = chapter(state["story"]["chapter"])["difficulty"] if difficulty is None else difficulty
    result = deepcopy(state)
    for _ in range(80):
        if result["phase"] in ("finished", "closed", "round_result") or _waiting_for_player(result):
            break
        moves = classic.legal_moves(result, 1)
        if not moves:
            break
        action = payload = None
        if result["phase"] == "choose_first":
            action, payload = "first", {"seat": 1 if level == 0 else 0}
        elif result["phase"] == "mulligan":
            hand = sorted(result["players"][1]["hand"], key=_card_value)
            action, payload = "mulligan", {"cards": [card["id"] for card in hand[:level]]}
        elif result.get("pending"):
            choice = next(move for move in moves if move["action"] == "choose")
            action, payload = choice["action"], choice["payload"]
        else:
            scores = [sum(classic.score_rows(result, seat)) for seat in (0, 1)]
            human = result["players"][0]
            if human["passed"] and scores[1] > scores[0]:
                action, payload = "pass", {}
            elif level == 2 and scores[1] + 8 < scores[0] and any(move["action"] == "leader" for move in moves):
                action, payload = "leader", {}
            elif any(move["action"] == "play" for move in moves):
                picked = _pick_play(result, moves, level)
                action, payload = picked["action"], picked["payload"]
            else:
                action, payload = "pass", {}
        result = classic.apply_action(result, 1, action, payload, now_ms, rng)
    if _waiting_for_player(result):
        result["deadline_ms"] = None
        result["server_time_ms"] = now_ms
    return result
