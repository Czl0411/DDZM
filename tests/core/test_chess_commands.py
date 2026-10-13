from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.commands import GroupCommandHandler
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, ChessGameRecord, OutboundRecord
from dzmm_bot.core.service import CoreService
from dzmm_bot.runtime.contracts import InboundMessage


NOW = datetime(2026, 10, 13, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
GAME_URL = "https://www.aikda.com/chat?card=chess-card"
API_URL = "https://chess.example.com"


def setup(tmp_path, enabled=True):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'commands.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repo = CoreRepository(factory)
    repo.bootstrap_primary_group("https://www.aikda.com/chat?c=chess", NOW)
    repo.create_user("creator", "发起人", NOW, 0)
    handler = GroupCommandHandler(repo, chess_game_url=GAME_URL if enabled else None, chess_public_api_url=API_URL if enabled else None, chess_game_id="game-id" if enabled else None)
    return CoreService(repo, handler), repo, factory


def send(service, suffix, sender="creator", source="group"):
    return service.receive_inbound(InboundMessage(
        f"chess-{suffix}", sender, "/象棋", NOW + timedelta(seconds=int(suffix)),
        source_type=source, chatroom_id="chess" if source == "group" else "direct",
    ))


def test_chess_command_creates_parallel_links_without_game_slot(tmp_path):
    service, repo, factory = setup(tmp_path)
    send(service, "1")
    send(service, "2")
    with factory() as session:
        games = session.scalars(select(ChessGameRecord).order_by(ChessGameRecord.created_at)).all()
        replies = session.scalars(select(OutboundRecord).order_by(OutboundRecord.created_at)).all()
    assert len(games) == 2 and games[0].id != games[1].id
    assert len(replies) == 4
    assert [item.content_type for item in replies] == ["character", "text", "character", "text"]
    assert all(item.text == "game-id" for item in replies[::2])
    assert all("先输入先得" in item.text and "https://" not in item.text for item in replies[1::2])
    assert all(item.group_chat_id == games[0].group_chat_id for item in replies)
    assert repo.claim_chess_seat(games[0].id, "creator", games[0].code, NOW).status == "same_player"


def test_unconfigured_or_unregistered_does_not_create(tmp_path):
    service, _, factory = setup(tmp_path, enabled=False)
    send(service, "1")
    send(service, "2", sender="unregistered")
    send(service, "3", source="direct")
    with factory() as session:
        assert session.scalars(select(ChessGameRecord)).all() == []


def test_chess_command_only_creates_games_in_configured_test_group(tmp_path):
    _, repo, factory = setup(tmp_path)
    repo.create_group_chat(
        "其他群", "https://www.aikda.com/chat?c=other", True, True,
        False, False, NOW,
    )
    service = CoreService(repo, GroupCommandHandler(
        repo, chess_game_id="game-id", chess_game_url=GAME_URL,
        chess_public_api_url=API_URL, chess_test_chatroom_id="chess",
    ))
    service.receive_inbound(InboundMessage(
        "chess-other", "creator", "/象棋", NOW,
        source_type="group", chatroom_id="other",
    ))
    with factory() as session:
        assert session.scalars(select(ChessGameRecord)).all() == []
        replies = session.scalars(select(OutboundRecord)).all()
        assert len(replies) == 1 and "仅在测试群开放" in replies[0].text

    send(service, "1")
    with factory() as session:
        games = session.scalars(select(ChessGameRecord)).all()
        assert len(games) == 1


def test_sent_gate_and_expiry(tmp_path):
    service, repo, factory = setup(tmp_path)
    send(service, "1")
    with factory.begin() as session:
        game = session.scalar(select(ChessGameRecord))
        reply = session.scalar(select(OutboundRecord))
        game_id, code = game.id, game.code
    repo.create_user("second", "第二人", NOW, 0)
    assert repo.claim_chess_seat(game_id, "second", code, NOW).status == "not_announced"
    with factory.begin() as session:
        session.get(OutboundRecord, reply.id).status = "sent"
    assert repo.claim_chess_seat(game_id, "second", code, NOW).status == "not_announced"
    with factory.begin() as session:
        text_reply = session.scalar(select(OutboundRecord).where(OutboundRecord.content_type == "text"))
        text_reply.status = "sent"
    assert repo.claim_chess_seat(game_id, "second", code, NOW + timedelta(minutes=10, seconds=1)).status == "expired"
