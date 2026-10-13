from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.chess_rules import IllegalChessMove
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, InboundRecord, OutboundRecord, PRIMARY_GROUP_CHAT_ID


NOW = datetime(2026, 10, 13, 12, tzinfo=ZoneInfo("Asia/Shanghai"))


@pytest.fixture
def active(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'game.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repo = CoreRepository(factory)
    repo.bootstrap_primary_group("https://www.aikda.com/chat?c=chess", NOW)
    for pid in ("creator", "opponent", "spectator"):
        repo.create_user(pid, pid, NOW, 0)
    inbound_id = uuid4()
    with factory.begin() as session:
        session.add(InboundRecord(id=inbound_id, platform_message_id="start", sender_platform_id="creator", content="/象棋", received_at=NOW, group_chat_id=PRIMARY_GROUP_CHAT_ID, chatroom_id="chess"))
        session.add(OutboundRecord(inbound_message_id=inbound_id, group_chat_id=PRIMARY_GROUP_CHAT_ID, text="link", status="sent"))
    game = repo.create_chess_game("creator", PRIMARY_GROUP_CHAT_ID, inbound_id, NOW)
    assert repo.claim_chess_seat(game.id, "opponent", game.code, NOW).status == "claimed"
    return repo, factory, repo.get_chess_game(game.id)


def test_turn_version_and_illegal_moves_are_authoritative(active):
    repo, _, game = active
    red = game.red_platform_id
    black = game.black_platform_id
    assert game.position is not None
    with pytest.raises(ValueError):
        repo.play_chess(game.id, black, (0, 3), (0, 4), 1, NOW)
    with pytest.raises(IllegalChessMove):
        repo.play_chess(game.id, red, (0, 9), (0, 5), 1, NOW)
    moved = repo.play_chess(game.id, red, (0, 6), (0, 5), 1, NOW + timedelta(seconds=5))
    assert moved.version == 2 and moved.red_remaining_ms == 895000
    with pytest.raises(ValueError):
        repo.play_chess(game.id, red, (2, 6), (2, 5), 1, NOW + timedelta(seconds=6))
    assert repo.get_chess_game(game.id).version == 2


def test_step_deadline_and_terminal_notice_are_once(active):
    repo, factory, game = active
    red = game.red_platform_id
    timed = repo.play_chess(game.id, red, (0, 6), (0, 5), 1, NOW + timedelta(seconds=60))
    assert timed.status == "finished" and timed.result == "black:step_timeout"
    assert repo.advance_chess_deadlines(NOW + timedelta(seconds=61)) == 0
    with factory() as session:
        notices = session.scalars(select(OutboundRecord).where(OutboundRecord.inbound_message_id.is_(None))).all()
    assert len(notices) == 1


def test_undo_draw_and_resignation(active):
    repo, _, game = active
    red, black = game.red_platform_id, game.black_platform_id
    moved = repo.play_chess(game.id, red, (0, 6), (0, 5), 1, NOW + timedelta(seconds=10))
    offered = repo.chess_action(game.id, red, "offer_undo", NOW + timedelta(seconds=11))
    assert offered.pending_offer == "undo"
    with pytest.raises(ValueError):
        repo.chess_action(game.id, red, "accept_undo", NOW + timedelta(seconds=12))
    undone = repo.chess_action(game.id, black, "accept_undo", NOW + timedelta(seconds=15))
    assert undone.position["board"][6][0] == "P"
    assert undone.red_remaining_ms == 890000
    assert undone.black_remaining_ms == 895000
    assert undone.position["turn"] == "red"
    repo.chess_action(game.id, black, "offer_draw", NOW + timedelta(seconds=16))
    drawn = repo.chess_action(game.id, red, "accept_draw", NOW + timedelta(seconds=17))
    assert drawn.status == "finished" and drawn.result == "draw:agreement"


def test_waiting_game_expires_once(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'wait.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repo = CoreRepository(factory)
    repo.bootstrap_primary_group("https://www.aikda.com/chat?c=chess", NOW)
    repo.create_user("creator", "creator", NOW, 0)
    inbound_id = uuid4()
    with factory.begin() as session:
        session.add(InboundRecord(id=inbound_id, platform_message_id="start", sender_platform_id="creator", content="/象棋", received_at=NOW, group_chat_id=PRIMARY_GROUP_CHAT_ID, chatroom_id="chess"))
    game = repo.create_chess_game("creator", PRIMARY_GROUP_CHAT_ID, inbound_id, NOW)
    assert repo.advance_chess_deadlines(NOW + timedelta(minutes=11)) == 1
    assert repo.advance_chess_deadlines(NOW + timedelta(minutes=12)) == 0
    assert repo.get_chess_game(game.id).status == "cancelled"


def test_restart_does_not_reset_clock_and_resign_is_terminal(active):
    repo, factory, game = active
    restarted = CoreRepository(factory)
    assert restarted.advance_chess_deadlines(NOW + timedelta(seconds=59)) == 0
    assert restarted.advance_chess_deadlines(NOW + timedelta(seconds=60)) == 1
    assert restarted.advance_chess_deadlines(NOW + timedelta(seconds=61)) == 0
    assert restarted.get_chess_game(game.id).status == "finished"
    with pytest.raises(ValueError):
        repo.chess_action(game.id, game.red_platform_id, "resign", NOW + timedelta(seconds=62))


def test_total_clock_precedes_step_clock(active):
    repo, factory, game = active
    from dzmm_bot.core.schema import ChessGameRecord

    with factory.begin() as session:
        row = session.get(ChessGameRecord, game.id)
        row.red_remaining_ms = 3000
    timed = repo.play_chess(game.id, game.red_platform_id, (0, 6), (0, 5), 1, NOW + timedelta(seconds=3))
    assert timed.result == "black:total_timeout"


def test_resignation_needs_no_opponent_approval(active):
    repo, _, game = active
    resigned = repo.chess_action(game.id, game.red_platform_id, "resign", NOW + timedelta(seconds=1))
    assert resigned.result == "black:resign"
