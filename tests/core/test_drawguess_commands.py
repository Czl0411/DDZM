from datetime import timedelta

from sqlalchemy import select

from dzmm_bot.core.commands import GroupCommandHandler
from dzmm_bot.core.schema import DrawguessRoomRecord, OutboundRecord
from dzmm_bot.core.service import CoreService
from dzmm_bot.runtime.contracts import InboundMessage
from dzmm_bot.runtime.settings import Settings
from tests.core.test_drawguess_repository import NOW, game


def service(repo, **changes):
    config = dict(
        drawguess_game_id="draw-card", drawguess_game_url="https://www.aikda.com/chat?card=draw-card",
        drawguess_public_api_url="https://api.example.com", drawguess_chatroom_id="drawguess",
    )
    config.update(changes)
    return CoreService(repo, GroupCommandHandler(repo, **config))


def send(svc, uid="host", group="drawguess", number=1):
    return svc.receive_inbound(InboundMessage(
        f"draw-{number}", uid, "/你画我猜", NOW + timedelta(seconds=number),
        source_type="group", chatroom_id=group,
    ))


def test_command_shares_character_card_then_text(game):
    repo, factory, _ = game
    send(service(repo))
    with factory() as session:
        rooms = session.scalars(select(DrawguessRoomRecord)).all()
        messages = session.scalars(select(OutboundRecord).order_by(OutboundRecord.created_at, OutboundRecord.reply_index)).all()
    assert len(rooms) == 1
    assert [message.content_type for message in messages] == ["character", "text"]
    assert messages[0].text == "draw-card"
    assert "入座码" in messages[1].text and "3～8 人" in messages[1].text
    assert "https://" not in messages[1].text


def test_command_requires_config_employee_and_exact_group(game):
    repo, factory, _ = game
    send(service(repo, drawguess_game_id=None))
    send(service(repo), uid="unknown", number=2)
    repo.create_group_chat("其他群", "https://www.aikda.com/chat?c=other", True, True, False, False, NOW)
    send(service(repo), group="other", number=3)
    with factory() as session:
        assert session.scalars(select(DrawguessRoomRecord)).all() == []


def test_drawguess_settings_from_environment(monkeypatch):
    monkeypatch.setenv("DZMM_DATABASE_URL", "sqlite://")
    monkeypatch.setenv("DZMM_CORE_TOKEN", "test")
    monkeypatch.setenv("DZMM_DRAWGUESS_GAME_ID", "draw-card")
    monkeypatch.setenv("DZMM_DRAWGUESS_CHATROOM_ID", "drawguess")
    monkeypatch.setenv("DZMM_DRAWGUESS_GAME_URL", "https://example.com/game")
    monkeypatch.setenv("DZMM_DRAWGUESS_PUBLIC_API_URL", "https://example.com")
    settings = Settings.from_environment()
    assert settings.drawguess_game_id == "draw-card"
    assert settings.drawguess_chatroom_id == "drawguess"
    assert settings.drawguess_game_url == "https://example.com/game"
    assert settings.drawguess_public_api_url == "https://example.com"
