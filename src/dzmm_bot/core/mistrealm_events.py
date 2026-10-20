"""Transactional change counters and a shared, bounded SSE wake-up dispatcher."""
import asyncio
from datetime import timedelta

from sqlalchemy import event, inspect, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .schema import MistrealmSocialRevisionRecord as Revision


def bump(session, scopes):
    insert = pg_insert if session.bind.dialect.name == 'postgresql' else sqlite_insert
    for scope in sorted(set(scopes)):
        statement = insert(Revision).values(scope=scope, version=1)
        session.execute(statement.on_conflict_do_update(
            index_elements=[Revision.scope], set_={'version': Revision.version + 1}))


def observe(session):
    """Install on repository-owned sessions; rollback also rolls back counters."""
    @event.listens_for(session, 'before_flush')
    def collect(session, context, instances):
        scopes = session.info.setdefault('mistrealm_changes', set())
        for obj in session.new | session.dirty | session.deleted:
            table = getattr(obj, '__tablename__', '')
            if not table.startswith('mistrealm_'):
                continue
            state = inspect(obj)
            changed = lambda name: state.attrs[name].history.has_changes()
            if table == 'mistrealm_channel_messages':
                scopes.add('channel')
            elif table in ('mistrealm_rooms', 'mistrealm_seats'):
                if table == 'mistrealm_seats' or obj in session.new or changed('phase') or changed('active_code'):
                    scopes.update(('players', 'channel'))
            elif table == 'mistrealm_players':
                seen = state.attrs.online_seen_at.history
                became_online = bool(seen.added and seen.added[0] and
                    (not seen.deleted or seen.deleted[0] is None or seen.deleted[0] <= seen.added[0] - timedelta(seconds=60)))
                if obj in session.new or became_online or any(changed(k) for k in ('name','avatar','queue_ticket','preferences')):
                    scopes.update(('players', 'channel'))
            elif table == 'mistrealm_friends':
                scopes.update('social:'+str(uid) for uid in (obj.low_id, obj.high_id))
            elif table in ('mistrealm_invites', 'mistrealm_direct_messages'):
                prefix = 'messages:' if table == 'mistrealm_direct_messages' else 'social:'
                scopes.update(prefix+str(uid) for uid in (obj.sender_id, obj.receiver_id))

    @event.listens_for(session, 'after_flush_postexec')
    def publish(session, context):
        scopes = session.info.pop('mistrealm_changes', set())
        if scopes:
            bump(session, scopes)


class SocialEvents:
    """One compact counter query per second per worker, not per player."""
    def __init__(self, repository, clock):
        self.repository, self.clock = repository, clock
        self.listeners = {}
        self.task = None

    def subscribe(self, player_id):
        scopes = {'players', 'channel', 'social:'+str(player_id), 'messages:'+str(player_id)}
        event = asyncio.Event()
        self.listeners[event] = (scopes, set())
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.watch())
        return event

    def unsubscribe(self, event):
        self.listeners.pop(event, None)
        if not self.listeners and self.task:
            self.task.cancel()
            self.task = None

    def take(self, event):
        event.clear()
        pending = self.listeners[event][1]
        result = set(pending)
        pending.clear()
        return result

    def read(self, scopes, since):
        from .schema import MistrealmPlayerRecord as Player, MistrealmInviteRecord as Invite
        now = self.clock()
        with self.repository._session() as session:
            versions = dict(session.execute(select(Revision.scope, Revision.version).where(Revision.scope.in_(scopes))).all())
            expired = set()
            # Time passing can change presence, matchmaking and invitation state without a write.
            if session.scalar(select(Player.id).where(Player.online_seen_at > since-timedelta(seconds=60),
                    Player.online_seen_at <= now-timedelta(seconds=60)).limit(1)):
                expired.update(('players','channel'))
            if session.scalar(select(Player.id).where(Player.queue_expires_at > since,Player.queue_expires_at <= now).limit(1)):
                expired.add('players')
            for a,b in session.execute(select(Invite.sender_id,Invite.receiver_id).where(
                    Invite.status=='pending',Invite.expires_at>since,Invite.expires_at<=now)):
                expired.update(('social:'+str(a),'social:'+str(b)))
        return versions, expired, now

    async def watch(self):
        previous = {}
        since = self.clock()
        while self.listeners:
            scopes = set().union(*(item[0] for item in self.listeners.values()))
            try:
                versions, expired, since = await asyncio.to_thread(self.read, scopes, since)
                changed = {scope for scope in scopes if versions.get(scope,0) != previous.get(scope,0)} | expired
                previous = versions
                for event,(wanted,pending) in tuple(self.listeners.items()):
                    if changed & wanted:
                        pending.update(changed & wanted)
                        event.set()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Force reconnect/resnapshot after a database interruption; never silently go stale.
                for event,(_,pending) in tuple(self.listeners.items()):
                    pending.add('unavailable');event.set()
            await asyncio.sleep(1)
