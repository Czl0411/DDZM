import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
import pytest

from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, MistrealmPlayerRecord as Player, MistrealmSocialRevisionRecord as Revision
from dzmm_bot.core.mistrealm_events import SocialEvents


@pytest.fixture
def setup(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'events.db'),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    repo=CoreRepository(factory);now=[datetime(2026,10,16,tzinfo=timezone.utc)]
    for uid in ('a','b','c'):
        repo.mistrealm_register(uid,uid,None,now[0]);repo.mistrealm_social_connect(uid,now[0])
    with factory() as s: ids={p.platform_uid:p.id for p in s.scalars(select(Player))}
    return repo,factory,now,ids


def versions(factory):
    with factory() as s:return dict(s.execute(select(Revision.scope,Revision.version)).all())


def test_counters_commit_and_rollback_with_message(setup):
    repo,factory,now,ids=setup
    before=versions(factory)
    with pytest.raises(RuntimeError):
        with repo.transaction():
            repo.mistrealm_channel_post('a','not committed',now[0]);raise RuntimeError()
    assert versions(factory)==before
    repo.mistrealm_channel_post('a','committed',now[0])
    assert versions(factory)['channel']>before['channel']


def test_touch_does_not_emit_changes_until_presence_transition(setup):
    repo,factory,now,ids=setup;before=versions(factory)
    repo.mistrealm_social_touch('a',now[0]+timedelta(seconds=15))
    assert versions(factory)==before
    repo.mistrealm_social_touch('a',now[0]+timedelta(seconds=80))
    assert versions(factory)['players']>before['players']


def test_private_changes_are_scoped_to_participants_and_read_only_once(setup):
    repo,factory,now,ids=setup
    repo.mistrealm_friend('a','b','request',now[0]);repo.mistrealm_friend('b','a','accept',now[0])
    before=versions(factory);request=uuid4()
    item=repo.mistrealm_dm_send('a','b','private',request,now[0])
    after=versions(factory)
    changed={k for k in after if after[k]!=before.get(k)}
    assert changed=={'messages:'+str(ids['a']),'messages:'+str(ids['b'])}
    repo.mistrealm_dm_send('a','b','private',request,now[0]);assert versions(factory)==after
    repo.mistrealm_dm_read('b','a',item['id'],now[0]);read=versions(factory)
    assert read['messages:'+str(ids['b'])]>after['messages:'+str(ids['b'])]
    repo.mistrealm_dm_read('b','a',item['id'],now[0]);assert versions(factory)==read


def test_two_dispatchers_observe_other_repository_commits_without_cross_user_dm(setup):
    repo,factory,now,ids=setup
    repo.mistrealm_friend('a','b','request',now[0]);repo.mistrealm_friend('b','a','accept',now[0])
    async def run():
        first=SocialEvents(repo,lambda:now[0]);second=SocialEvents(CoreRepository(factory),lambda:now[0])
        a=first.subscribe(ids['a']);c=second.subscribe(ids['c'])
        await asyncio.wait_for(a.wait(),3);await asyncio.wait_for(c.wait(),3)
        first.take(a);second.take(c)
        await asyncio.to_thread(repo.mistrealm_dm_send,'a','b','secret',uuid4(),now[0])
        await asyncio.wait_for(a.wait(),3)
        assert first.take(a)=={'messages:'+str(ids['a'])}
        await asyncio.sleep(1.1);assert not c.is_set()
        await asyncio.to_thread(repo.mistrealm_channel_post,'b','public',now[0])
        await asyncio.wait_for(c.wait(),3);assert 'channel' in second.take(c)
        first.unsubscribe(a);second.unsubscribe(c)
        assert first.task is None and second.task is None
    asyncio.run(run())


def test_offline_transition_notifies_even_without_a_database_write(setup):
    repo,factory,now,ids=setup
    events=SocialEvents(repo,lambda:now[0]+timedelta(seconds=61))
    _,expired,_=events.read({'players','channel'},now[0])
    assert {'players','channel'}<=expired


def test_invite_expiry_only_wakes_the_two_players(setup):
    from dzmm_bot.core.schema import MistrealmInviteRecord as Invite
    repo,factory,now,ids=setup
    with repo._session() as session:
        session.add(Invite(sender_id=ids['a'],receiver_id=ids['b'],status='pending',deck_snapshot={},
            created_at=now[0],expires_at=now[0]+timedelta(seconds=5)))
    events=SocialEvents(repo,lambda:now[0]+timedelta(seconds=6))
    _,expired,_=events.read(set(),now[0])
    assert expired=={'social:'+str(ids['a']),'social:'+str(ids['b'])}
