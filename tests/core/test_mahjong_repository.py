from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, UserRecord


NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


@pytest.fixture
def mahjong(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'mahjong.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repo = CoreRepository(factory)
    for uid in ("host", "alice", "bob", "carol", "viewer"):
        repo.create_user(uid, uid, NOW, 1000)
    return repo, factory


def balance(factory, uid):
    with factory() as session:
        return session.scalar(select(UserRecord.balance).where(UserRecord.platform_id == uid))


def create(repo, room_type="coin", request_id=None):
    return repo.create_mahjong_room(
        "host", NOW, room_type=room_type, match_mode="east",
        request_id=request_id or uuid4(),
    )


def act(repo, room, uid, action, payload=None, now=NOW, request_id=None):
    return repo.mahjong_action(
        UUID(room["id"]), uid, room["version"], request_id or uuid4(),
        action, payload or {}, now,
    )


def seated(mahjong, room_type="coin"):
    repo, _ = mahjong
    room = create(repo, room_type)
    for uid in ("alice", "bob", "carol"):
        room = act(repo, room, uid, "claim")
    for uid in ("host", "alice", "bob", "carol"):
        room = act(repo, room, uid, "ready")
    room = act(repo, room, "host", "start")
    return room


def test_coin_room_escrows_exactly_once_and_hides_private_hands(mahjong):
    repo, factory = mahjong
    request_id = uuid4()
    room = create(repo, request_id=request_id)
    duplicate = create(repo, request_id=request_id)
    assert duplicate["id"] == room["id"]
    assert balance(factory, "host") == 990
    claim_id = uuid4()
    room = act(repo, room, "alice", "claim", request_id=claim_id)
    repeated = repo.mahjong_action(
        UUID(room["id"]), "alice", 0, claim_id, "claim", {}, NOW,
    )
    assert repeated["seat"] == 1
    assert balance(factory, "alice") == 990
    viewer = repo.mahjong_view(UUID(room["id"]), "viewer", NOW)
    assert viewer["seat"] is None
    assert "code" not in viewer


def test_waiting_leave_and_expiry_refund_coin_escrow(mahjong):
    repo, factory = mahjong
    room = create(repo)
    room = act(repo, room, "alice", "claim")
    assert balance(factory, "alice") == 990
    room = act(repo, room, "alice", "leave")
    assert balance(factory, "alice") == 1000
    assert room["players"][1] is None
    repo.advance_mahjong_deadlines(NOW + timedelta(minutes=11))
    assert balance(factory, "host") == 1000


def test_four_ready_players_start_authoritative_match(mahjong):
    room = seated(mahjong)
    assert room["phase"] == "playing"
    assert room["game"]["turn"] == 0
    assert len(room["game"]["hand"]) == 14
    viewer = mahjong[0].mahjong_view(UUID(room["id"]), "viewer", NOW)
    assert viewer["game"]["hints"] == {}
    assert set(room["game"]["hints"]) == {"current", "discards"}
    assert viewer["game"]["hand"] == []
    assert viewer["game"]["hand_counts"] == [14, 13, 13, 13]


def test_reaction_deadline_is_advanced_by_room_refresh(mahjong, monkeypatch):
    repo, factory = mahjong
    room = seated(mahjong)
    from dzmm_bot.core import mahjong_repository
    from dzmm_bot.core.schema import MahjongRoomRecord

    with factory.begin() as session:
        record = session.get(MahjongRoomRecord, UUID(room["id"]))
        record.state = {
            **record.state,
            "phase": "reaction",
            "deadline": (NOW - timedelta(seconds=1)).isoformat(),
        }
        record.phase = "reaction"
        record.deadline = NOW - timedelta(seconds=1)

    def advance(state, now, wall_factory):
        return {
            **state,
            "phase": "playing",
            "version": state["version"] + 1,
            "deadline": (now + timedelta(seconds=10)).isoformat(),
        }

    monkeypatch.setattr(mahjong_repository, "apply_timeout", advance)
    refreshed = repo.mahjong_view(UUID(room["id"]), "host", NOW)

    assert refreshed["phase"] == "playing"


def test_reaction_action_is_accepted_by_repository(mahjong, monkeypatch):
    repo, _ = mahjong
    monkeypatch.setattr(repo, "_mahjong_wall", lambda: list(range(136)))
    room = seated(mahjong)

    room = act(repo, room, "host", "discard", {"tile": room["game"]["hand"][-1]})
    assert room["phase"] == "reaction"
    room = act(repo, room, "carol", "pass")

    assert room["phase"] == "playing"


def test_two_players_can_respond_to_same_discard_snapshot(mahjong):
    from dzmm_bot.core.schema import MahjongRoomRecord

    repo, factory = mahjong
    room = seated(mahjong)
    with factory.begin() as session:
        row = session.get(MahjongRoomRecord, UUID(room["id"]))
        row.state = {**row.state, "hands": [[8], [0, 4, 12, 16], [9, 10], []]}
    room = act(repo, room, "host", "discard", {"tile": 8})
    reaction_version = room["game"]["reaction_version"]
    assert reaction_version == room["version"]
    payload = {"tiles": [4, 12], "reaction_version": reaction_version}
    request_id = uuid4()
    answered = act(repo, room, "alice", "chi", payload, request_id=request_id)
    assert answered["game"]["actions"] == {}
    assert answered["game"]["reaction_action"] == "chi"
    assert repo.mahjong_view(UUID(room["id"]), "bob", NOW)["game"]["reaction_action"] is None
    assert repo.mahjong_view(UUID(room["id"]), "viewer", NOW)["game"]["reaction_action"] is None
    duplicate = act(repo, room, "alice", "chi", payload, request_id=request_id)
    assert duplicate["version"] == answered["version"]
    with pytest.raises(ValueError):
        act(repo, room, "alice", "chi", payload)
    with pytest.raises(ValueError):
        act(repo, room, "bob", "pass")
    result = act(
        repo,
        room,
        "bob",
        "pass",
        {"reaction_version": reaction_version},
        now=NOW + timedelta(seconds=10),
    )
    assert result["phase"] == "playing"
    assert result["game"]["turn"] == 1
    assert result["game"]["melds"][1][0]["tiles"] == [4, 8, 12]


def finish_hand(factory, room, *, payments=(), kind="ron", winners=(2,), points=None, extra=None):
    from dzmm_bot.core.schema import MahjongRoomRecord

    with factory.begin() as session:
        row = session.get(MahjongRoomRecord, UUID(room["id"]))
        deltas = [0] * 4
        for payment in payments:
            deltas[payment["from"]] -= payment["points"]
            deltas[payment["to"]] += payment["points"]
        result = {
            "kind": kind,
            "winners": list(winners),
            "payments": list(payments),
            "deltas": deltas,
            "dealer_continues": 0 in winners,
        }
        row.state = {
            **row.state,
            "phase": "hand_finished",
            "deadline": None,
            "points": points or [25000 + delta for delta in deltas],
            "history": [result],
            "result": result,
            "next": {"dealer_continues": 0 in winners},
            **(extra or {}),
        }
        row.phase = "hand_finished"
        row.deadline = None


@pytest.mark.parametrize(
    "stake,points,coins",
    [(5, 2900, 8), (5, 3900, 10), (5, 1000, 3), (10, 2900, 15), (20, 2000, 20), (20, 2900, 29)],
)
def test_coin_conversion_rounds_final_payment(stake, points, coins):
    from dzmm_bot.core.mahjong_repository import mahjong_coins

    assert mahjong_coins(points, stake) == coins


def test_per_hand_settlement_refunds_buy_in_and_rakes_positive_net_once(mahjong, monkeypatch):
    repo, factory = mahjong
    room = seated(mahjong)
    monkeypatch.setattr(
        repo,
        "get_club_game_economy_settings",
        lambda game: type("Settings", (), {"coin_stakes": (10,), "rake_percent": 0})(),
    )
    finish_hand(factory, room, payments=[{"from": 1, "to": 2, "points": 2900}])
    settled = repo.mahjong_view(UUID(room["id"]), "host", NOW)
    assert settled["phase"] == "hand_finished"
    assert settled["settlement"]["gross_net"] == [0, -15, 15, 0]
    assert settled["settlement"]["net"] == [0, -15, 12, 0]
    assert settled["settlement"]["refunds"] == [10] * 4
    assert settled["settlement"]["rake_percent"] == 20
    assert settled["settlement"]["rake_amount"] == 3
    assert settled["settlement"]["outcomes"] == ["draw", "loss", "win", "draw"]
    assert [balance(factory, uid) for uid in ("host", "alice", "bob", "carol")] == [1000, 985, 1012, 1000]
    repo.mahjong_view(UUID(room["id"]), "host", NOW + timedelta(minutes=1))
    assert [balance(factory, uid) for uid in ("host", "alice", "bob", "carol")] == [1000, 985, 1012, 1000]

    for uid in ("host", "alice", "bob", "carol"):
        settled = act(repo, settled, uid, "ready")
    settled = act(repo, settled, "host", "start")
    assert settled["phase"] == "playing"
    assert settled["settlement"] is None
    assert settled["rake_percent"] == 0


@pytest.mark.parametrize(
    "payments,gross_net,net,rake",
    [
        (
            [
                {"from": 0, "to": 2, "points": 2000},
                {"from": 1, "to": 2, "points": 1000},
                {"from": 3, "to": 2, "points": 1000},
            ],
            [-10, -5, 20, -5],
            [-10, -5, 16, -5],
            4,
        ),
        (
            [
                {"from": 1, "to": 0, "points": 2900},
                {"from": 1, "to": 2, "points": 3900},
            ],
            [15, -35, 20, 0],
            [12, -35, 16, 0],
            7,
        ),
        ([], [0, 0, 0, 0], [0, 0, 0, 0], 0),
    ],
)
def test_rake_is_distributed_only_across_positive_hand_net(mahjong, payments, gross_net, net, rake):
    repo, factory = mahjong
    room = seated(mahjong)
    finish_hand(factory, room, payments=payments)
    room = repo.mahjong_view(UUID(room["id"]), "host", NOW)
    assert room["settlement"]["gross_net"] == gross_net
    assert room["settlement"]["net"] == net
    assert room["settlement"]["rake_amount"] == rake
    assert sum(gross_net) == 0
    assert sum(net) == -rake


def test_negative_balance_is_allowed_for_payment_not_new_entry(mahjong):
    repo, factory = mahjong
    room = seated(mahjong)
    with factory.begin() as session:
        user = session.scalar(select(UserRecord).where(UserRecord.platform_id == "alice"))
        user.balance = 0
    finish_hand(factory, room, payments=[{"from": 1, "to": 2, "points": 8000}])
    room = repo.mahjong_view(UUID(room["id"]), "host", NOW)
    assert balance(factory, "alice") == -30
    assert room["settlement"]["gross_net"] == [0, -40, 40, 0]
    assert room["settlement"]["net"] == [0, -40, 32, 0]
    for uid in ("host", "alice", "bob", "carol"):
        room = act(repo, room, uid, "ready")
    with pytest.raises(ValueError, match="余额不足"):
        act(repo, room, "host", "start")
    assert balance(factory, "host") == 1000


def test_riichi_coins_are_charged_once_and_rake_uses_true_net_win(mahjong):
    from dzmm_bot.core.schema import MahjongRoomRecord
    from mahjong.tile import TilesConverter

    repo, factory = mahjong
    room = seated(mahjong)
    with factory.begin() as session:
        row = session.get(MahjongRoomRecord, UUID(room["id"]))
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="123", sou="11")
        row.state = {**row.state, "hands": [tiles, [], [], []], "turn_counts": [1, 0, 0, 0]}
    tile = tiles[-1]
    request_id = uuid4()
    previous = room
    room = act(repo, room, "host", "riichi", {"tile": tile}, request_id=request_id)
    act(repo, previous, "host", "riichi", {"tile": tile}, request_id=request_id)
    assert balance(factory, "host") == 985
    finish_hand(
        factory,
        room,
        payments=[{"from": 1, "to": 0, "points": 2000}],
        winners=(0,),
        extra={"riichi_sticks": 0},
    )
    room = repo.mahjong_view(UUID(room["id"]), "host", NOW)
    assert room["settlement"]["riichi_paid"] == [5, 0, 0, 0]
    assert room["settlement"]["riichi_award"] == 5
    assert room["settlement"]["gross_net"] == [10, -10, 0, 0]
    assert room["settlement"]["net"] == [8, -10, 0, 0]
    assert room["settlement"]["rake_amount"] == 2
    assert [balance(factory, uid) for uid in ("host", "alice", "bob", "carol")] == [1008, 990, 1000, 1000]


def test_finished_leave_dissolves_fixed_seat_room(mahjong):
    repo, factory = mahjong
    room = seated(mahjong)
    finish_hand(factory, room, kind="荒牌流局", winners=())
    room = repo.mahjong_view(UUID(room["id"]), "host", NOW)
    assert repo.list_mahjong_rooms("viewer", NOW) == []
    assert repo.club_active_room("alice", NOW)["room_id"] == room["id"]
    room = act(repo, room, "host", "ready")
    room = act(repo, room, "host", "leave")
    assert not room["players"][0]["ready"]
    assert room["phase"] == "cancelled"
    assert repo.list_mahjong_rooms("viewer", NOW) == []
    assert repo.club_active_room("alice", NOW) is None
    replacement = create(repo, room_type="casual")
    assert replacement["phase"] == "waiting"


def test_riichi_pool_carries_then_final_award_is_raked_as_positive_net(mahjong):
    from dzmm_bot.core.schema import MahjongRoomRecord

    repo, factory = mahjong
    room = seated(mahjong)
    with repo.transaction(), repo._session() as session:
        user = session.scalar(select(UserRecord).where(UserRecord.platform_id == "alice"))
        repo._apply_balance_change(user, -5, "mahjong_riichi", NOW)
    finish_hand(
        factory,
        room,
        kind="荒牌流局",
        winners=(),
        extra={
            "coin_riichi_deposits": [{"seat": 1, "coins": 5}],
            "hand_riichi_paid": [0, 5, 0, 0],
            "riichi_sticks": 1,
        },
    )
    room = repo.mahjong_view(UUID(room["id"]), "host", NOW)
    assert room["settlement"]["riichi_carried"] == 5
    assert room["settlement"]["gross_net"] == [0, -5, 0, 0]
    assert room["settlement"]["net"] == [0, -5, 0, 0]
    assert room["settlement"]["rake_amount"] == 0
    for uid in ("host", "alice", "bob", "carol"):
        room = act(repo, room, uid, "ready")
    room = act(repo, room, "host", "start")
    with factory() as session:
        row = session.get(MahjongRoomRecord, UUID(room["id"]))
        assert row.state["coin_riichi_deposits"] == [{"seat": 1, "coins": 5}]
        assert row.state["hand_riichi_paid"] == [0] * 4
    finish_hand(factory, room, kind="荒牌流局", winners=(), extra={"riichi_sticks": 0})
    with factory.begin() as session:
        row = session.get(MahjongRoomRecord, UUID(room["id"]))
        row.phase = "match_finished"
        row.state = {
            **row.state,
            "phase": "match_finished",
            "result": {"kind": "match", "riichi_recipient": 0},
        }
    room = repo.mahjong_view(UUID(room["id"]), "host", NOW)
    assert room["settlement"]["riichi_award"] == 5
    assert room["settlement"]["gross_net"] == [5, 0, 0, 0]
    assert room["settlement"]["net"] == [4, 0, 0, 0]
    assert room["settlement"]["rake_amount"] == 1
    assert [balance(factory, uid) for uid in ("host", "alice", "bob", "carol")] == [1004, 995, 1000, 1000]


def test_casual_room_never_moves_balance(mahjong):
    room = seated(mahjong, "casual")
    assert room["buy_in"] == 0
    assert [balance(mahjong[1], uid) for uid in ("host", "alice", "bob", "carol")] == [1000] * 4


def test_coin_room_uses_configured_stakes(mahjong, monkeypatch):
    repo, _ = mahjong
    monkeypatch.setattr(
        repo,
        "get_club_game_economy_settings",
        lambda game: type("Settings", (), {"coin_stakes": (7, 21), "rake_percent": 20})(),
    )

    with pytest.raises(ValueError, match="7、21"):
        create(repo)
    room = repo.create_mahjong_room(
        "host", NOW, room_type="coin", stake=7, match_mode="east", request_id=uuid4(),
    )

    assert room["buy_in"] == 7
