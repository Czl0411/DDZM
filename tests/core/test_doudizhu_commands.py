from datetime import timedelta
from sqlalchemy import select

from dzmm_bot.core.commands import GroupCommandHandler
from dzmm_bot.core.service import CoreService
from dzmm_bot.core.schema import DoudizhuRoomRecord, OutboundRecord
from dzmm_bot.runtime.contracts import InboundMessage
from dzmm_bot.runtime.settings import Settings
from tests.core.test_doudizhu_repository import ddz, NOW
from tests.core.test_doudizhu_repository import dealt, act


def service(repo, **changes):
    config = dict(doudizhu_game_id='new-card', doudizhu_game_url='https://www.aikda.com/chat?card=new-card',
                  doudizhu_public_api_url='https://api.example.com', doudizhu_chatroom_id='test-ddz')
    config.update(changes)
    return CoreService(repo, GroupCommandHandler(repo, **config))


def send(svc, uid='host', group='test-ddz', number=1):
    return svc.receive_inbound(InboundMessage(f'ddz-{number}', uid, '/斗地主', NOW + timedelta(seconds=number), source_type='group', chatroom_id=group))


def test_command_shares_card_then_text(ddz):
    repo, factory, _ = ddz
    svc = service(repo)
    send(svc)
    send(svc)
    send(svc, number=2)
    with factory() as s:
        rooms = s.scalars(select(DoudizhuRoomRecord)).all()
        messages = s.scalars(select(OutboundRecord).order_by(OutboundRecord.created_at, OutboundRecord.reply_index)).all()
    assert len(rooms) == 2
    assert [m.content_type for m in messages] == ['character', 'text', 'character', 'text']
    assert messages[0].text == 'new-card'
    assert '10 分钟' in messages[1].text and '两位' in messages[1].text
    assert 'https://' not in messages[1].text


def test_command_requires_config_employee_and_allowed_group(ddz):
    repo, factory, _ = ddz
    send(service(repo, doudizhu_game_id=None))
    send(service(repo), uid='nobody', number=2)
    repo.create_group_chat('其他群', 'https://www.aikda.com/chat?c=other', True, True, False, False, NOW)
    send(service(repo), group='other', number=3)
    with factory() as s:
        assert s.scalars(select(DoudizhuRoomRecord)).all() == []


def test_doudizhu_settings_from_environment(monkeypatch):
    monkeypatch.setenv('DZMM_DATABASE_URL', 'sqlite://')
    monkeypatch.setenv('DZMM_CORE_TOKEN', 'test')
    monkeypatch.setenv('DZMM_DOUDIZHU_GAME_ID', 'new-card')
    monkeypatch.setenv('DZMM_DOUDIZHU_CHATROOM_ID', 'test-ddz')
    monkeypatch.setenv('DZMM_DOUDIZHU_GAME_URL', 'https://example.com/game')
    monkeypatch.setenv('DZMM_DOUDIZHU_PUBLIC_API_URL', 'https://example.com')
    settings = Settings.from_environment()
    assert settings.doudizhu_game_id == 'new-card'
    assert settings.doudizhu_chatroom_id == 'test-ddz'
    assert settings.doudizhu_game_url == 'https://example.com/game'
    assert settings.doudizhu_public_api_url == 'https://example.com'


def test_finish_notice_once_without_currency(ddz):
    from datetime import datetime
    from uuid import UUID
    from dzmm_bot.core.schema import UserRecord
    repo, factory, _ = ddz
    room = dealt(ddz)
    room = act(repo, room, ['host', 'alice', 'bob'][room['turn']], 'bid', {'score': 3})
    with factory() as s:
        before = [(u.id, u.balance) for u in s.scalars(select(UserRecord)).all()]
    for _ in range(100):
        if room['phase'] == 'finished':
            break
        repo.advance_doudizhu_deadlines(datetime.fromisoformat(room['deadline']))
        room = repo.doudizhu_view(UUID(room['id']), 'viewer', NOW)
    assert room['phase'] == 'finished'
    repo.advance_doudizhu_deadlines(NOW + timedelta(days=1))
    with factory() as s:
        notices = s.scalars(select(OutboundRecord).where(OutboundRecord.inbound_message_id.is_(None))).all()
        assert len(notices) == 1
        assert all(name in notices[0].text for name in ('host', 'alice', 'bob'))
        assert '胜利' in notices[0].text and '落败' in notices[0].text
        assert room['id'] not in notices[0].text and 'landlord' not in notices[0].text
        assert [(u.id, u.balance) for u in s.scalars(select(UserRecord)).all()] == before


def test_chess_and_doudizhu_have_independent_help_topics(ddz):
    repo, factory, _ = ddz
    svc = service(repo)
    for index, topic in enumerate(('象棋', '斗地主')):
        svc.receive_inbound(InboundMessage(f'help-{index}', 'host', f'/帮助 {topic}', NOW,
            source_type='group', chatroom_id='test-ddz'))
    with factory() as s:
        messages = s.scalars(select(OutboundRecord).order_by(OutboundRecord.created_at)).all()
        assert len(messages) == 2
        assert '【象棋】' in messages[0].text and '/斗地主' not in messages[0].text
        assert '【斗地主】' in messages[1].text
