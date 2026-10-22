from datetime import timedelta

from sqlalchemy import select

from dzmm_bot.core.commands import GroupCommandHandler
from dzmm_bot.core.schema import MahjongRoomRecord, OutboundRecord
from dzmm_bot.core.service import CoreService
from dzmm_bot.runtime.contracts import InboundMessage
from tests.core.test_mahjong_repository import NOW, mahjong


def service(repo, **changes):
    config = {
        "club_game_id": "club-card",
        "club_game_url": "https://www.aikda.com/chat?card=club-card",
        "club_public_api_url": "https://api.example.com",
        "club_chatroom_id": "games",
    }
    config.update(changes)
    return CoreService(repo, GroupCommandHandler(repo, **config))


def send(svc, content="/麻将", uid="host", group="games", number=1):
    return svc.receive_inbound(InboundMessage(
        f"mahjong-{number}", uid, content, NOW + timedelta(seconds=number),
        source_type="group", chatroom_id=group,
    ))


def prepare(mahjong):
    repo, factory = mahjong
    repo.bootstrap_primary_group("https://www.aikda.com/chat?c=games", NOW)
    return repo, factory


def test_mahjong_command_shares_club_without_creating_a_room(mahjong):
    repo, factory = prepare(mahjong)
    send(service(repo))
    with factory() as session:
        room = session.scalar(select(MahjongRoomRecord))
        messages = session.scalars(
            select(OutboundRecord).order_by(OutboundRecord.created_at, OutboundRecord.reply_index)
        ).all()
    assert room is None
    assert [message.content_type for message in messages] == ["character", "text"]
    assert messages[0].text == "club-card"
    assert "摸鱼麻将" in messages[1].text
    assert "打开上方卡片后选择游戏和牌桌" in messages[1].text
    assert "https://" not in messages[1].text


def test_mahjong_command_ignores_legacy_room_options_and_shares_club(mahjong):
    repo, factory = prepare(mahjong)
    send(service(repo), "/麻将 休闲 半庄")
    send(service(repo), "/麻将 三麻", number=2)
    with factory() as session:
        rooms = session.scalars(select(MahjongRoomRecord)).all()
        messages = session.scalars(select(OutboundRecord)).all()
    assert rooms == []
    assert [message.content_type for message in messages] == ["character", "text"] * 2


def test_club_command_allows_guest_players_in_monitored_groups_and_requires_config(mahjong):
    repo, factory = prepare(mahjong)
    send(service(repo), "/club")
    send(service(repo), uid="unknown", number=2)
    send(service(repo), group="other", number=3)
    send(service(repo, club_game_id=None), number=4)
    with factory() as session:
        messages = session.scalars(select(OutboundRecord).order_by(OutboundRecord.created_at)).all()
    assert [message.content_type for message in messages[:4]] == ["character", "text"] * 2
    assert [message.text for message in messages[:4:2]] == ["club-card"] * 2
    assert messages[-1].content_type == "text"
    assert messages[-1].text == "摸鱼 Club 入口尚未配置完成。"
