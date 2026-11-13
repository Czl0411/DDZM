from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from dzmm_bot.core.schema import (
    ClubCardHandRecord,
    ClubCardRoomRecord,
    UserRecord,
)
from tests.core.test_mahjong_repository import NOW, mahjong


def balance(factory, uid):
    with factory() as session:
        return session.scalar(select(UserRecord.balance).where(UserRecord.platform_id == uid))


def act(repo, room, uid, action, payload=None, request_id=None):
    return repo.club_card_action(
        room["game"], UUID(room["id"]), uid, room["version"],
        request_id or uuid4(), action, payload or {}, NOW,
    )


def started_coin_room(repo, game):
    room = repo.create_club_card_room(
        game, "host", NOW, room_type="coin", stake=10, request_id=uuid4(),
    )
    room = act(repo, room, "alice", "claim")
    room = act(repo, room, "host", "ready")
    room = act(repo, room, "alice", "ready")
    return act(repo, room, "host", "start")


def test_texas_coin_hand_uses_floor_rake_and_requests_are_idempotent(mahjong):
    repo, factory = mahjong
    room = repo.create_club_card_room(
        "texas", "host", NOW, room_type="coin", stake=10, request_id=uuid4(),
    )
    room = act(repo, room, "alice", "claim")
    room = act(repo, room, "host", "ready")
    room = act(repo, room, "alice", "ready")
    start_id = uuid4()
    room = act(repo, room, "host", "start", request_id=start_id)
    repeated = repo.club_card_action(
        "texas", UUID(room["id"]), "host", room["version"] - 1,
        start_id, "start", {}, NOW,
    )
    assert repeated["hand_number"] == 1
    assert balance(factory, "host") == 990
    assert balance(factory, "alice") == 990

    room = act(repo, room, "host", "fold")

    assert room["phase"] == "hand_finished"
    assert room["state"]["rake_percent"] == 20
    assert room["state"]["rake_amount"] == 0
    assert sum(room["state"]["gross_payouts"].values()) == 20
    assert sum(room["state"]["payouts"].values()) == 20
    assert balance(factory, "host") + balance(factory, "alice") == 2000
    assert balance(factory, "host") == 999
    assert balance(factory, "alice") == 1001


@pytest.mark.parametrize("game", ["texas", "zhajinhua", "blackjack", "niuniu"])
def test_coin_room_uses_each_games_configured_stakes(mahjong, game):
    repo, _ = mahjong
    repo.set_club_game_economy_settings(
        game, coin_stakes=(7, 13), rake_percent=20,
    )

    with pytest.raises(ValueError, match="仅支持 7、13 币"):
        repo.create_club_card_room(
            game, "host", NOW, room_type="coin", stake=10,
            request_id=uuid4(),
        )

    room = repo.create_club_card_room(
        game, "host", NOW, room_type="coin", stake=13,
        request_id=uuid4(),
    )
    assert room["stake"] == 13


def test_texas_casual_hand_never_takes_rake(mahjong):
    repo, factory = mahjong
    room = repo.create_club_card_room(
        "texas", "host", NOW, room_type="casual", stake=0, request_id=uuid4(),
    )
    room = act(repo, room, "alice", "claim")
    room = act(repo, room, "host", "ready")
    room = act(repo, room, "alice", "ready")
    room = act(repo, room, "host", "start")
    room = act(repo, room, "host", "fold")

    assert room["state"]["rake_percent"] == 0
    assert room["state"]["rake_amount"] == 0
    assert room["state"]["payouts"] == room["state"]["gross_payouts"]
    with factory() as session:
        hand = session.scalar(select(ClubCardHandRecord))
        assert hand.rake_percent == 0
        assert hand.rake_amount == 0


def test_texas_rake_percent_is_snapshotted_when_hand_starts(mahjong):
    repo, factory = mahjong
    room = repo.create_club_card_room(
        "texas", "host", NOW, room_type="coin", stake=20, request_id=uuid4(),
    )
    room = act(repo, room, "alice", "claim")
    room = act(repo, room, "host", "ready")
    room = act(repo, room, "alice", "ready")
    room = act(repo, room, "host", "start")
    assert room["state"]["rake_percent"] == 20

    repo.set_club_game_economy_settings(
        "texas", coin_stakes=(5, 10, 20), rake_percent=100,
    )

    room = act(repo, room, "host", "fold")

    assert room["state"]["pot"] == 3
    assert room["state"]["rake_percent"] == 20
    assert room["state"]["rake_amount"] == 0


@pytest.mark.parametrize("game", ["texas", "zhajinhua", "blackjack", "niuniu"])
def test_each_card_game_snapshots_its_rake_when_the_hand_starts(mahjong, game):
    repo, _ = mahjong
    repo.set_club_game_economy_settings(
        game, coin_stakes=(5, 10, 20), rake_percent=35,
    )
    room = started_coin_room(repo, game)
    repo.set_club_game_economy_settings(
        game, coin_stakes=(5, 10, 20), rake_percent=0,
    )

    assert room["state"]["rake_percent"] == 35


@pytest.mark.parametrize("game", ["texas", "zhajinhua", "blackjack", "niuniu"])
def test_casual_card_game_never_snapshots_rake(mahjong, game):
    repo, _ = mahjong
    repo.set_club_game_economy_settings(
        game, coin_stakes=(5, 10, 20), rake_percent=100,
    )
    room = repo.create_club_card_room(
        game, "host", NOW, room_type="casual", stake=99,
        request_id=uuid4(),
    )
    room = act(repo, room, "alice", "claim")
    room = act(repo, room, "host", "ready")
    room = act(repo, room, "alice", "ready")
    room = act(repo, room, "host", "start")

    assert room["stake"] == 0
    assert room["state"]["rake_percent"] == 0


def test_texas_old_hand_without_rake_snapshot_does_not_take_rake(mahjong):
    repo, factory = mahjong
    room = repo.create_club_card_room(
        "texas", "host", NOW, room_type="coin", stake=10, request_id=uuid4(),
    )
    room = act(repo, room, "alice", "claim")
    room = act(repo, room, "host", "ready")
    room = act(repo, room, "alice", "ready")
    room = act(repo, room, "host", "start")
    with factory.begin() as session:
        record = session.get(ClubCardRoomRecord, UUID(room["id"]))
        record.state = {
            key: value for key, value in record.state.items() if key != "rake_percent"
        }

    room = act(repo, room, "host", "fold")

    assert room["state"]["rake_percent"] == 0
    assert room["state"]["rake_amount"] == 0
    assert balance(factory, "host") + balance(factory, "alice") == 2000


def test_texas_rake_uses_largest_remainders_and_settlement_is_idempotent(mahjong):
    repo, factory = mahjong
    room = repo.create_club_card_room(
        "texas", "host", NOW, room_type="coin", stake=10, request_id=uuid4(),
    )
    room = act(repo, room, "alice", "claim")
    room = act(repo, room, "bob", "claim")
    for uid in ("host", "alice", "bob"):
        room = act(repo, room, uid, "ready")
    room = act(repo, room, "host", "start")
    player_ids = {player["uid"]: player["id"] for player in room["players"]}
    gross_payouts = {
        player_ids["host"]: 10,
        player_ids["alice"]: 9,
        player_ids["bob"]: 11,
    }
    chips = {
        player_ids["host"]: 5,
        player_ids["alice"]: 2,
        player_ids["bob"]: 0,
    }
    with repo.transaction(), repo._session() as session:
        record = session.get(ClubCardRoomRecord, UUID(room["id"]))
        record.state = {
            **record.state,
            "phase": "hand_finished",
            "turn": None,
            "pot": 23,
            "chips": chips,
            "payouts": gross_payouts,
            "winners": [player_ids["bob"]],
        }
        record.phase = "hand_finished"
        repo._settle_club_card_hand(session, record, NOW)
        repo._settle_club_card_hand(session, record, NOW)

    with factory() as session:
        record = session.get(ClubCardRoomRecord, UUID(room["id"]))
        hands = session.scalars(select(ClubCardHandRecord)).all()
        assert record.state["gross_payouts"] == gross_payouts
        assert record.state["payouts"] == {
            player_ids["host"]: 9,
            player_ids["alice"]: 8,
            player_ids["bob"]: 9,
        }
        assert record.state["rake_amount"] == 4
        assert sum(record.state["payouts"].values()) + record.state["rake_amount"] == 30
        assert all(record.state["payouts"][raw] >= chips[raw] for raw in chips)
        assert len(hands) == 1
        assert hands[0].rake_percent == 20
        assert hands[0].rake_amount == 4
    assert balance(factory, "host") == 999
    assert balance(factory, "alice") == 998
    assert balance(factory, "bob") == 999


def test_texas_split_pot_uses_same_rake_rule_as_group_game(mahjong):
    repo, factory = mahjong
    room = started_coin_room(repo, "texas")
    player_ids = {player["uid"]: player["id"] for player in room["players"]}
    gross_payouts = {player_ids["host"]: 10, player_ids["alice"]: 10}

    with repo.transaction(), repo._session() as session:
        record = session.get(ClubCardRoomRecord, UUID(room["id"]))
        record.state = {
            **record.state,
            "phase": "hand_finished",
            "turn": None,
            "pot": 20,
            "chips": {raw: 0 for raw in gross_payouts},
            "payouts": gross_payouts,
            "winners": list(gross_payouts),
        }
        record.phase = "hand_finished"
        repo._settle_club_card_hand(session, record, NOW)

    with factory() as session:
        record = session.get(ClubCardRoomRecord, UUID(room["id"]))
        assert record.state["rake_amount"] == 4
        assert record.state["payouts"] == {
            player_ids["host"]: 8,
            player_ids["alice"]: 8,
        }
    assert balance(factory, "host") == 998
    assert balance(factory, "alice") == 998


def test_texas_rake_excludes_uncalled_excess(mahjong):
    repo, factory = mahjong
    room = started_coin_room(repo, "texas")
    player_ids = {player["uid"]: player["id"] for player in room["players"]}
    host = player_ids["host"]
    alice = player_ids["alice"]

    with repo.transaction(), repo._session() as session:
        record = session.get(ClubCardRoomRecord, UUID(room["id"]))
        record.state = {
            **record.state,
            "phase": "hand_finished",
            "turn": None,
            "pot": 14,
            "contributions": {host: 10, alice: 4},
            "chips": {host: 0, alice: 6},
            "payouts": {host: 6, alice: 14},
            "winners": [alice],
        }
        record.phase = "hand_finished"
        repo._settle_club_card_hand(session, record, NOW)

    with factory() as session:
        record = session.get(ClubCardRoomRecord, UUID(room["id"]))
        hand = session.scalar(select(ClubCardHandRecord))
        assert record.state["gross_payouts"] == {host: 6, alice: 14}
        assert record.state["payouts"] == {host: 6, alice: 13}
        assert record.state["rake_amount"] == 1
        assert hand.rake_amount == 1
    assert balance(factory, "host") == 996
    assert balance(factory, "alice") == 1003


def test_zhajinhua_rake_only_comes_from_the_winners_pot_award(mahjong):
    repo, factory = mahjong
    room = started_coin_room(repo, "zhajinhua")
    player_ids = {player["uid"]: player["id"] for player in room["players"]}
    with repo.transaction(), repo._session() as session:
        record = session.get(ClubCardRoomRecord, UUID(room["id"]))
        record.state = {
            **record.state,
            "phase": "hand_finished",
            "turn": None,
            "pot": 12,
            "chips": {
                player_ids["host"]: 8,
                player_ids["alice"]: 0,
            },
            "payouts": {
                player_ids["host"]: 20,
                player_ids["alice"]: 0,
            },
            "winners": [player_ids["host"]],
        }
        record.phase = "hand_finished"
        repo._settle_club_card_hand(session, record, NOW)

    with factory() as session:
        record = session.get(ClubCardRoomRecord, UUID(room["id"]))
        hand = session.scalar(select(ClubCardHandRecord))
        assert record.state["gross_payouts"][player_ids["host"]] == 20
        assert record.state["payouts"][player_ids["host"]] == 18
        assert record.state["payouts"][player_ids["host"]] >= 8
        assert record.state["rake_amount"] == 2
        assert hand.rake_percent == 20
        assert hand.rake_amount == 2
    assert balance(factory, "host") == 1008
    assert balance(factory, "alice") == 990


def test_blackjack_rake_comes_from_the_gross_winner(mahjong):
    repo, factory = mahjong
    room = started_coin_room(repo, "blackjack")
    player_ids = {player["uid"]: player["id"] for player in room["players"]}
    with repo.transaction(), repo._session() as session:
        record = session.get(ClubCardRoomRecord, UUID(room["id"]))
        record.state = {
            **record.state,
            "phase": "hand_finished",
            "turn": None,
            "pot": 20,
            "payouts": {
                player_ids["host"]: 20,
                player_ids["alice"]: 0,
            },
            "winners": [player_ids["host"]],
            "results": {
                player_ids["host"]: "胜",
                player_ids["alice"]: "负",
            },
        }
        record.phase = "hand_finished"
        repo._settle_club_card_hand(session, record, NOW)

    with factory() as session:
        record = session.get(ClubCardRoomRecord, UUID(room["id"]))
        assert record.state["gross_payouts"][player_ids["host"]] == 20
        assert record.state["payouts"][player_ids["host"]] == 16
        assert record.state["rake_amount"] == 4
    assert balance(factory, "host") == 1006
    assert balance(factory, "alice") == 990


def test_blackjack_all_busted_refund_never_takes_rake(mahjong):
    repo, factory = mahjong
    room = started_coin_room(repo, "blackjack")
    player_ids = {player["uid"]: player["id"] for player in room["players"]}
    refunds = {player_ids["host"]: 10, player_ids["alice"]: 10}
    with repo.transaction(), repo._session() as session:
        record = session.get(ClubCardRoomRecord, UUID(room["id"]))
        record.state = {
            **record.state,
            "phase": "hand_finished",
            "turn": None,
            "pot": 20,
            "payouts": refunds,
            "winners": [],
            "results": {
                player_ids["host"]: "爆牌·退还",
                player_ids["alice"]: "爆牌·退还",
            },
        }
        record.phase = "hand_finished"
        repo._settle_club_card_hand(session, record, NOW)

    with factory() as session:
        record = session.get(ClubCardRoomRecord, UUID(room["id"]))
        assert record.state["gross_payouts"] == refunds
        assert record.state["payouts"] == refunds
        assert record.state["rake_amount"] == 0
    assert balance(factory, "host") == 1000
    assert balance(factory, "alice") == 1000


def test_blackjack_pvp_requires_two_players_and_settles_without_a_dealer(mahjong):
    repo, factory = mahjong
    room = repo.create_club_card_room(
        "blackjack", "host", NOW, room_type="coin", stake=10, request_id=uuid4(),
    )
    with pytest.raises(ValueError, match="至少需要 2 人"):
        room = act(repo, room, "host", "ready")
        act(repo, room, "host", "start")
    room = repo.club_card_view("blackjack", UUID(room["id"]), "host", NOW)
    room = act(repo, room, "alice", "claim")
    room = act(repo, room, "alice", "ready")
    if room["me"]["uid"] != "host":
        room = repo.club_card_view("blackjack", UUID(room["id"]), "host", NOW)
    room = act(repo, room, "host", "ready")
    room = act(repo, room, "host", "start")

    assert "dealer" not in room["state"]
    assert balance(factory, "host") == 990
    assert balance(factory, "alice") == 990


def test_finished_hand_stays_on_settlement_until_everyone_readies(mahjong):
    repo, _ = mahjong
    room = repo.create_club_card_room(
        "zhajinhua", "host", NOW, room_type="casual", stake=0, request_id=uuid4(),
    )
    room = act(repo, room, "alice", "claim")
    room = act(repo, room, "host", "ready")
    room = act(repo, room, "alice", "ready")
    room = act(repo, room, "host", "start")
    room = act(repo, room, "alice", "fold")
    assert room["phase"] == "hand_finished"

    assert all(cards and all(card is not None for card in cards)
               for cards in room["state"]["hands"].values())
    assert set(room["state"]["hand_ranks"]) == set(room["state"]["hands"])

    room = act(repo, room, "host", "ready")
    assert room["phase"] == "hand_finished"
    with pytest.raises(ValueError, match="所有玩家准备"):
        act(repo, room, "host", "start")
    room = act(repo, room, "alice", "ready")
    room = act(repo, room, "host", "start")

    assert room["phase"] == "playing"
    assert room["hand_number"] == 2
    assert room["players"][0]["name"] == "host"
    assert room["players"][1]["name"] == "alice"
    assert room["ready"] == []


@pytest.mark.parametrize("game", ["texas", "zhajinhua", "blackjack", "niuniu"])
def test_spectator_can_join_after_a_hand_for_the_next_hand(mahjong, game):
    repo, factory = mahjong
    room = repo.create_club_card_room(
        game, "host", NOW, room_type="casual", stake=0, request_id=uuid4(),
    )
    room = act(repo, room, "alice", "claim")
    with factory.begin() as session:
        record = session.get(ClubCardRoomRecord, UUID(room["id"]))
        record.phase = "hand_finished"
        record.state = {
            "phase": "hand_finished", "players": list(record.seats),
            "hands": {}, "winners": [], "payouts": {},
        }
        record.version += 1

    spectator = repo.club_card_view(game, UUID(room["id"]), "bob", NOW)
    joined = act(repo, spectator, "bob", "claim")

    assert joined["phase"] == "hand_finished"
    assert [player["uid"] for player in joined["players"]] == ["host", "alice", "bob"]
    assert joined["ready"] == []
    assert joined["state"]["players"] == spectator["state"]["players"]


def test_card_turn_times_out_and_auto_folds_when_a_call_is_required(mahjong):
    repo, _ = mahjong
    room = repo.create_club_card_room(
        "texas", "host", NOW, room_type="casual", stake=0, request_id=uuid4(),
    )
    room = act(repo, room, "alice", "claim")
    room = act(repo, room, "host", "ready")
    room = act(repo, room, "alice", "ready")
    room = act(repo, room, "host", "start")

    assert room["state"]["turn_deadline"] == (NOW + timedelta(seconds=30)).isoformat()

    assert repo.advance_club_card_deadlines(NOW + timedelta(seconds=31)) == 1
    timed_out = repo.club_card_view("texas", UUID(room["id"]), "host", NOW + timedelta(seconds=31))

    assert timed_out["phase"] == "hand_finished"
    assert timed_out["state"]["last_action"] == "玩家超时，自动弃牌"
    assert "turn_deadline" not in timed_out["state"]


def test_card_player_cannot_occupy_two_active_rooms(mahjong):
    repo, _ = mahjong
    first = repo.create_club_card_room(
        "texas", "host", NOW, room_type="casual", stake=0, request_id=uuid4(),
    )
    second = repo.create_club_card_room(
        "blackjack", "alice", NOW, room_type="casual", stake=0, request_id=uuid4(),
    )

    with pytest.raises(ValueError, match="已经在.+牌桌"):
        act(repo, second, "host", "claim")
    spectator_view = repo.club_card_view("blackjack", UUID(second["id"]), "host", NOW)
    assert all(player["uid"] != "host" for player in spectator_view["players"])
    with pytest.raises(ValueError, match="已经在.+牌桌"):
        repo.create_club_card_room(
            "zhajinhua", "host", NOW, room_type="casual", stake=0,
            request_id=uuid4(),
        )

    first = act(repo, first, "host", "leave")
    assert first["phase"] == "closed"
    joined = act(repo, second, "host", "claim")
    assert any(player["uid"] == "host" for player in joined["players"])


def test_card_player_cannot_create_or_join_another_club_module(mahjong):
    repo, _ = mahjong
    repo.create_club_card_room(
        "texas", "host", NOW, room_type="casual", stake=0, request_id=uuid4(),
    )

    with pytest.raises(ValueError, match="已经在德州扑克房间"):
        repo.create_mahjong_room(
            "host", NOW, room_type="casual", match_mode="east",
            request_id=uuid4(),
        )
    with pytest.raises(ValueError, match="已经在德州扑克房间"):
        repo.create_chess_game("host", now=NOW)
    with pytest.raises(ValueError, match="已经在德州扑克房间"):
        repo.create_doudizhu_room("host", now=NOW)
    with pytest.raises(ValueError, match="已经在德州扑克房间"):
        repo.create_drawguess_room("host", now=NOW)


def test_active_room_restores_the_players_card_table(mahjong):
    repo, _ = mahjong
    room = repo.create_club_card_room(
        "texas", "host", NOW, room_type="casual", stake=0,
        request_id=uuid4(),
    )

    assert repo.club_active_room("host", NOW) == {
        "game": "texas", "room_id": room["id"], "phase": "waiting",
    }
    assert repo.club_active_room("viewer", NOW) is None
