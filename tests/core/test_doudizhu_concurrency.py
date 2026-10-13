"""Optional real PostgreSQL tests, in an isolated disposable schema."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, InboundRecord, OutboundRecord, PRIMARY_GROUP_CHAT_ID


def test_concurrent_claim_and_timeout():
    url = os.environ.get('DOUDIZHU_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set DOUDIZHU_TEST_DATABASE_URL to a disposable local PostgreSQL database')
    schema = 'ddz_test_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as c:
        c.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    try:
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        repo = CoreRepository(factory)
        now = datetime(2026, 10, 13, tzinfo=timezone.utc)
        repo.bootstrap_primary_group('https://www.aikda.com/chat?c=ddz', now)
        for uid in ('host', 'a', 'b', 'c'):
            repo.create_user(uid, uid, now, 0)
        inbound = uuid4()
        with factory.begin() as s:
            s.add(InboundRecord(id=inbound, platform_message_id=str(inbound), sender_platform_id='host', content='/斗地主', received_at=now, group_chat_id=PRIMARY_GROUP_CHAT_ID, chatroom_id='ddz'))
            s.flush()
            s.add(OutboundRecord(inbound_message_id=inbound, group_chat_id=PRIMARY_GROUP_CHAT_ID, text='code', status='sent', content_type='text'))
        room = repo.create_doudizhu_room('host', PRIMARY_GROUP_CHAT_ID, inbound, now)
        room_id, code = UUID(room['id']), room['code']
        room = repo.doudizhu_action(room_id, 'a', None, room['version'], uuid4(), 'claim', {'code': code}, now)
        def claim(uid):
            try:
                return repo.doudizhu_action(room_id, uid, None, room['version'], uuid4(), 'claim', {'code': code}, now)
            except ValueError:
                return None
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(claim, ('b', 'c')))
        assert sum(r is not None for r in results) == 1
        room = next(r for r in results if r is not None)
        winner = room['players'][2]['name']
        for uid in ('host', 'a'):
            room = repo.doudizhu_action(room_id, uid, None, room['version'], uuid4(), 'ready', {}, now)
        def ready(_):
            try:
                return repo.doudizhu_action(room_id, winner, None, room['version'], uuid4(), 'ready', {}, now)
            except ValueError:
                return None
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(ready, range(2)))
        assert sum(r is not None for r in results) == 1
        with ThreadPoolExecutor(2) as pool:
            counts = list(pool.map(lambda _: repo.advance_doudizhu_deadlines(now + timedelta(seconds=15)), range(2)))
        assert sum(counts) == 1
        assert repo.doudizhu_view(room_id, 'host', now)['bid'] == 0
        room = repo.doudizhu_view(room_id, 'host', now)
        next_uid = ['host', 'a', winner][room['turn']]
        def move_or_timeout(kind):
            if kind == 'timeout':
                return bool(repo.advance_doudizhu_deadlines(now + timedelta(seconds=30)))
            try:
                repo.doudizhu_action(room_id, next_uid, UUID(room['round_id']), room['version'],
                    uuid4(), 'bid', {'score': 3}, now + timedelta(seconds=29))
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(move_or_timeout, ('move', 'timeout')))
        assert sum(results) == 1
        assert repo.doudizhu_view(room_id, 'host', now)['version'] == room['version'] + 1
    finally:
        engine.dispose()
        with admin.begin() as c:
            c.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()
