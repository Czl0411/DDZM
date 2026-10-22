from datetime import datetime, timedelta
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
    handler = GroupCommandHandler(
        repo,
        club_game_url=GAME_URL if enabled else None,
        club_public_api_url=API_URL if enabled else None,
        club_game_id="game-id" if enabled else None,
    )
    return CoreService(repo, handler), repo, factory


def send(service, suffix, sender="creator", source="group"):
    return service.receive_inbound(InboundMessage(
        f"chess-{suffix}", sender, "/象棋", NOW + timedelta(seconds=int(suffix)),
        source_type=source, chatroom_id="chess" if source == "group" else "direct",
    ))


def test_chess_command_shares_club_without_creating_code_rooms(tmp_path):
    service, _, factory = setup(tmp_path)
    send(service, "1")
    send(service, "2")
    with factory() as session:
        games = session.scalars(select(ChessGameRecord).order_by(ChessGameRecord.created_at)).all()
        replies = session.scalars(select(OutboundRecord).order_by(OutboundRecord.created_at)).all()
    assert games == []
    assert len(replies) == 4
    assert [item.content_type for item in replies] == ["character", "text", "character", "text"]
    assert all(item.text == "game-id" for item in replies[::2])
    assert all("选择游戏和牌桌" in item.text and "https://" not in item.text for item in replies[1::2])


def test_unconfigured_or_unregistered_does_not_create(tmp_path):
    service, _, factory = setup(tmp_path, enabled=False)
    send(service, "1")
    send(service, "2", sender="unregistered")
    send(service, "3", source="direct")
    with factory() as session:
        assert session.scalars(select(ChessGameRecord)).all() == []


def test_chess_command_shares_club_in_every_monitored_group(tmp_path):
    _, repo, factory = setup(tmp_path)
    repo.create_group_chat(
        "其他群", "https://www.aikda.com/chat?c=other", True, True,
        False, False, NOW,
    )
    service = CoreService(repo, GroupCommandHandler(
        repo, club_game_id="game-id", club_game_url=GAME_URL,
        club_public_api_url=API_URL,
    ))
    service.receive_inbound(InboundMessage(
        "chess-other", "creator", "/象棋", NOW,
        source_type="group", chatroom_id="other",
    ))
    with factory() as session:
        assert session.scalars(select(ChessGameRecord)).all() == []
        replies = session.scalars(select(OutboundRecord)).all()
        assert [reply.content_type for reply in replies] == ["character", "text"]

    send(service, "1")
    with factory() as session:
        games = session.scalars(select(ChessGameRecord)).all()
        assert games == []


def test_chess_command_never_creates_a_legacy_seat_code(tmp_path):
    service, _, factory = setup(tmp_path)
    send(service, "1")
    with factory() as session:
        assert session.scalars(select(ChessGameRecord)).all() == []
        text = session.scalar(select(OutboundRecord).where(OutboundRecord.content_type == "text"))
        assert "入座码" not in text.text
