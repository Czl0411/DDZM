from copy import deepcopy
from datetime import timedelta
from random import Random
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from dzmm_bot.core.club_card_games import apply_action, evaluate_niuniu, new_hand, public_view
from dzmm_bot.core.schema import ClubCardRoomRecord, ClubCardHandRecord, UserRecord
from tests.core.test_mahjong_repository import NOW, mahjong
from tests.core.test_club_card_repository import act, balance


def cards(*ranks, suit="clubs"):
    return [[suit, rank] for rank in ranks]


@pytest.mark.parametrize("ranks,bull", [
    ([14, 2, 7, 10, 13], 10), ([14, 2, 7, 4, 5], 9),
    ([14, 2, 7, 3, 4], 7), ([14, 2, 7, 10, 6], 6),
    ([14, 2, 7, 10, 11], 10), ([14, 2, 3, 4, 5], 5),
    ([14, 2, 3, 4, 6], 6), ([14, 2, 3, 4, 8], 0),
])
def test_classic_evaluation(ranks, bull):
    result = evaluate_niuniu(cards(*ranks))
    assert result["bull"] == bull
    assert result["multiplier"] == (3 if bull == 10 else 2 if bull >= 7 else 1)


def test_tie_uses_king_high_and_suit_not_ace_high():
    king = evaluate_niuniu(cards(14, 2, 7, 10, 13))
    queen = evaluate_niuniu(cards(14, 2, 7, 10, 12))
    spade = evaluate_niuniu(cards(14, 2, 7, 10, 13, suit="spades"))
    assert spade["rank"] > king["rank"] > queen["rank"]


def test_banker_payments_and_only_winning_bull_takes_over():
    state = new_hand("niuniu", ["bank", "low", "high", "none"], 10, Random(4), banker="bank")
    state["hands"] = {"bank": cards(14, 2, 7, 10, 12), "low": cards(14, 2, 7, 10, 11),
                      "high": cards(14, 2, 7, 10, 13), "none": cards(14, 2, 3, 4, 8)}
    for player in ["none", "high", "bank", "low"]:
        apply_action("niuniu", state, player, "reveal", {})
    assert state["next_banker"] == "high"
    assert state["net"] == {"bank": 30, "low": -30, "high": 30, "none": -30}
    assert len(state["payments"]) == 3
    assert sum(state["payouts"].values()) == sum(state["buy_ins"].values())
    state2 = new_hand("niuniu", ["bank", "low"], 10, Random(1), banker="bank")
    state2["hands"] = {p: state["hands"][p] for p in state2["players"]}
    for p in state2["players"]:
        apply_action("niuniu", state2, p, "reveal", {})
    assert state2["next_banker"] == "bank"


def test_private_cards_and_manual_group_validation():
    state = new_hand("niuniu", ["a", "b"], 10, Random(1))
    state["hands"]["a"] = cards(14, 2, 7, 10, 13)
    viewer = public_view("niuniu", state, "b")
    assert viewer["hands"]["a"] == [None] * 5
    assert "a" not in viewer["evaluations"]
    assert "deck" not in viewer
    assert "own_evaluation" not in public_view("niuniu", state, "spectator")
    for group in ([0, 0, 2], [0, 1, 3], [True, 1, 2], [0, 1, 7], "012"):
        with pytest.raises(ValueError):
            apply_action("niuniu", deepcopy(state), "a", "reveal", {"cards": group})
    apply_action("niuniu", state, "a", "reveal", {"cards": [0, 1, 2]})
    assert public_view("niuniu", state, "b")["hands"]["a"] == state["hands"]["a"]
    with pytest.raises(ValueError, match="已亮牌"):
        apply_action("niuniu", state, "a", "reveal", {})
    with pytest.raises(ValueError, match="不在"):
        apply_action("niuniu", state, "outsider", "reveal", {})


def test_six_players_random_hands_conserve_coins():
    for seed in range(100):
        state = new_hand("niuniu", list("abcdef"), 20, Random(seed))
        assert len({tuple(c) for hand in state["hands"].values() for c in hand}) == 30
        for player in reversed(state["players"]):
            apply_action("niuniu", state, player, "reveal", {})
        assert sum(state["net"].values()) == 0
        assert sum(state["payouts"].values()) == 600
        assert min(state["payouts"].values()) >= 0
        assert len(state["payments"]) == 5


def start_room(repo, users=("host", "alice", "bob")):
    room = repo.create_club_card_room("niuniu", users[0], NOW, room_type="coin", stake=10, request_id=uuid4())
    for user in users[1:]:
        room = act(repo, room, user, "claim")
    for user in users:
        room = act(repo, room, user, "ready")
    return act(repo, room, users[0], "start")


def test_simultaneous_reveal_escrow_timeout_and_no_auto_restart(mahjong):
    repo, factory = mahjong
    room = start_room(repo)
    ids = {p["uid"]: p["id"] for p in room["players"]}
    for uid, raw in ids.items():
        assert balance(factory, uid) == 1000 - room["state"]["buy_ins"][raw]
    original = deepcopy(room)
    rid = uuid4()
    room = act(repo, original, "alice", "reveal", {"hand_number": 1, "cards": None}, rid)
    room = act(repo, original, "host", "reveal", {"hand_number": 1, "cards": None})
    assert room["state"]["turn_deadline"] == original["state"]["turn_deadline"]
    assert repo.advance_club_card_deadlines(NOW + timedelta(seconds=31)) == 1
    room = repo.club_card_view("niuniu", UUID(room["id"]), "host", NOW + timedelta(seconds=32))
    assert room["phase"] == "hand_finished"
    assert room["ready"] == []
    assert "turn_deadline" not in room["state"]
    assert room["state"]["action_history"][-1]["automatic"]
    state = room["state"]
    gross_winnings = sum(max(0, value) for value in state["gross_net"].values())
    assert state["rake_percent"] == 20
    assert state["rake_amount"] == gross_winnings * 20 // 100
    for uid, raw in ids.items():
        assert balance(factory, uid) == 1000 + state["net"][raw]
        assert state["payouts"][raw] == state["buy_ins"][raw] + state["net"][raw]
        if state["gross_net"][raw] <= 0:
            assert state["net"][raw] == state["gross_net"][raw]
    assert sum(balance(factory, uid) for uid in ids) + state["rake_amount"] == 3000
    act(repo, original, "alice", "reveal", {"hand_number": 1, "cards": None}, rid)
    assert repo.advance_club_card_deadlines(NOW + timedelta(minutes=5)) == 0
    with factory() as session:
        hands = session.scalars(select(ClubCardHandRecord)).all()
        assert len(hands) == 1
        assert hands[0].rake_amount == state["rake_amount"]
        assert hands[0].payouts == state["payouts"]
        assert sum(hands[0].payouts.values()) + hands[0].rake_amount == sum(
            state["buy_ins"].values()
        )
    with pytest.raises(ValueError, match="所有玩家准备"):
        act(repo, room, "host", "start")
    banker = room["state"]["next_banker"]
    for uid in ids:
        room = act(repo, room, uid, "ready")
    room = act(repo, room, "host", "start")
    assert room["state"]["banker"] == banker
    with pytest.raises(ValueError, match="已更换"):
        act(repo, room, "host", "reveal", {"hand_number": 1, "cards": None})
    with pytest.raises(ValueError, match="状态已更新"):
        act(repo, original, "host", "reveal", {"hand_number": 2, "cards": None})


def test_insufficient_escrow_rolls_back_entire_start(mahjong):
    repo, factory = mahjong
    room = repo.create_club_card_room("niuniu", "host", NOW, room_type="coin", stake=20, request_id=uuid4())
    room = act(repo, room, "alice", "claim")
    for uid in ("host", "alice"):
        room = act(repo, room, uid, "ready")
    with factory() as session:
        account = session.scalar(select(UserRecord).where(UserRecord.platform_id == "alice"))
        account.balance = 59
        session.commit()
    with pytest.raises(ValueError, match="需托管 60"):
        act(repo, room, "host", "start")
    assert balance(factory, "host") == 1000
    assert balance(factory, "alice") == 59
    assert repo.club_card_view("niuniu", UUID(room["id"]), "host", NOW)["phase"] == "waiting"


def test_banker_preview_is_stable_and_seat_changes_reset_consent(mahjong):
    repo, _ = mahjong
    room = start_room(repo)
    for user in ("host", "alice", "bob"):
        room = act(repo, room, user, "reveal", {"hand_number": 1, "cards": None})
    banker = room["scheduled_banker"]
    banker_uid = next(p["uid"] for p in room["players"] if p["id"] == banker)
    room = act(repo, room, "host", "ready")
    room = act(repo, room, banker_uid, "leave")
    assert room["ready"] == []
    assert room["scheduled_banker"] in [p["id"] for p in room["players"]]
    assert room["scheduled_banker"] != banker
    for user in [p["uid"] for p in room["players"]]:
        room = act(repo, room, user, "ready")
    host = next(p["uid"] for p in room["players"] if p["id"] == room["creator_id"])
    expected = room["scheduled_banker"]
    room = act(repo, room, host, "start")
    assert room["state"]["banker"] == expected


def test_niuniu_http_lobby_reveal_profile_and_active_room(mahjong):
    from fastapi.testclient import TestClient
    from dzmm_bot.core.app import create_app
    repo, _ = mahjong
    client = TestClient(create_app(repo, "internal", clock=lambda: NOW, club_game_id="club"))
    headers = lambda uid: {"Authorization": f"ClubUid {uid}"}
    response = client.post("/api/club/cards/niuniu/rooms", headers=headers("host"), json={
        "request_id": str(uuid4()), "room_type": "coin", "stake": 10,
    })
    assert response.status_code == 200, response.text
    room = response.json()
    path = f"/api/club/cards/niuniu/rooms/{room['id']}"
    for uid, action in [("alice", "claim"), ("host", "ready"), ("alice", "ready"), ("host", "start"),
                        ("alice", "reveal"), ("host", "reveal")]:
        response = client.post(path + "/actions", headers=headers(uid), json={
            "version": room["version"], "request_id": str(uuid4()), "action": action,
            "payload": {"hand_number": 1, "cards": None} if action == "reveal" else {},
        })
        assert response.status_code == 200, response.text
        room = response.json()
    assert room["phase"] == "hand_finished"
    assert client.get("/api/club/profile", headers=headers("host")).json()["stats"]["games"]["niuniu"]["played"] == 1
    assert client.get("/api/club/active-room", headers=headers("host")).json()["game"] == "niuniu"
    assert client.get(f"/api/club/room-status/niuniu/{room['id']}", headers=headers("alice")).status_code == 200
