"""Independent players and serialized room transactions for Mistrealm."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from secrets import SystemRandom, randbelow
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from . import mistrealm_state as legacy
from . import mistrealm_classic_state as classic
from . import mistrealm_story as story
from .mistrealm_classic_cards import validate_deck
from .schema import (
    MistrealmPlayerRecord as Player, MistrealmRoomRecord as Room,
    MistrealmSeatRecord as Seat, MistrealmRequestRecord as Receipt, MistrealmDeckRecord as Deck,
    MistrealmStoryProgressRecord as StoryProgress,
    MistrealmChannelMessageRecord as ChannelMessage,
)


class MistrealmError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def ms(now):
    if now.tzinfo is None:
        raise ValueError("时间必须包含时区")
    return int(now.timestamp()*1000)


def _engine(state):
    return classic if state.get('rules_version', 1) == 2 else legacy


class MistrealmRepositoryMixin:
    @staticmethod
    def _mr_player(session, uid):
        p = session.scalar(select(Player).where(Player.platform_uid == uid).with_for_update())
        if p is None:
            raise MistrealmError("请先登记玩家", 401)
        return p

    def mistrealm_register(self, uid, name, avatar, now):
        with self._session() as session:
            p = session.scalar(select(Player).where(Player.platform_uid == uid).with_for_update())
            if p is None:
                try:
                    with session.begin_nested():
                        p = Player(platform_uid=uid, name=name, avatar=avatar,
                                   created_at=now, updated_at=now, rate_limits={})
                        session.add(p)
                        session.flush()
                except IntegrityError:
                    p = self._mr_player(session, uid)
            p.name, p.avatar, p.updated_at = name, avatar, now
            return {"uid": uid, "name": name, "avatar": avatar}

    @staticmethod
    def _mr_room(session, room_id):
        room = session.scalar(select(Room).where(Room.id == room_id).with_for_update())
        if room is None:
            raise MistrealmError("房间不存在", 404)
        return room

    @staticmethod
    def _mr_sync(session, room, state):
        room.state, room.phase = state, state["phase"]
        deadline = state["deadline_ms"]
        room.deadline = datetime.fromtimestamp(deadline/1000, timezone.utc) if deadline is not None else None
        if room.phase == "closed":
            room.active_code = None
            session.execute(delete(Seat).where(Seat.room_id == room.id))

    @staticmethod
    def _mr_story_progress_record(session, player, now):
        record = session.get(StoryProgress, player.id)
        if record is None:
            record = StoryProgress(player_id=player.id, completed_chapters=[], updated_at=now)
            session.add(record)
            session.flush()
        return record

    def _mr_story_finish(self, session, room, player, now):
        state = room.state
        if state.get("mode") != "story" or state["phase"] != "finished" or state["winner"] != 0:
            return
        progress = self._mr_story_progress_record(session, player, now)
        chapter = state["story"]["chapter"]
        if chapter not in progress.completed_chapters:
            progress.completed_chapters = sorted([*progress.completed_chapters, chapter])
            progress.updated_at = now

    def _mr_story_drive(self, session, room, player, now):
        if room.state.get("mode") != "story":
            return
        state = story.drive(room.state, ms(now), SystemRandom())
        if state != room.state:
            self._mr_sync(session, room, state)
        self._mr_story_finish(session, room, player, now)

    def _mr_advance(self, session, room, now):
        state = _engine(room.state).advance(room.state, ms(now), SystemRandom())
        if state != room.state:
            self._mr_sync(session, room, state)

    def _mr_active(self, session, p, now):
        seat = session.scalar(select(Seat).where(Seat.player_id == p.id))
        if seat:
            room = self._mr_room(session, seat.room_id)
            self._mr_advance(session, room, now)
            return room if room.phase != "closed" else None
        return None

    @staticmethod
    def _mr_view(session, room, p):
        seat = session.scalar(select(Seat).where(Seat.room_id == room.id, Seat.player_id == p.id))
        if seat is None:
            raise MistrealmError("你不在这个房间", 403)
        state = _engine(room.state).project(room.state, seat.seat_index)
        # Seat table is authoritative for active membership.
        for entry in session.scalars(select(Seat).where(Seat.room_id == room.id)):
            profile = session.get(Player, entry.player_id)
            state["players"][entry.seat_index].update(name=profile.name, avatar=profile.avatar)
        if room.state.get("mode") == "story":
            state["mode"] = "story"
            state["story"] = deepcopy(room.state["story"])
            state["players"][1].update(
                name=room.state["story"]["enemy_name"], avatar=None
            )
        return {"room_id": str(room.id), "code": room.active_code,
                "match_id": str(room.match_id) if room.match_id else None, "state": state}

    def mistrealm_me(self, uid, now):
        with self._session() as session:
            p = self._mr_player(session, uid)
            room = self._mr_active(session, p, now)
            return {"uid": uid, "name": p.name, "avatar": p.avatar,
                    "room_id": str(room.id) if room else None,
                    "matchmaking": self._mr_queue_status(p, now)}

    def _mr_rate(self, uid, kind, limit, now):
        # Separate transaction: rejected attempts still count; shared by all workers.
        with self._session() as session:
            p = self._mr_player(session, uid)
            rates = dict(p.rate_limits)
            stamp = ms(now)
            attempts = [t for t in rates.get(kind, []) if t > stamp-60000]
            if len(attempts) >= limit:
                raise MistrealmError("操作过于频繁，请稍后重试", 429)
            rates[kind] = [*attempts, stamp]
            p.rate_limits = rates

    @staticmethod
    def _mr_digest(value):
        return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

    @staticmethod
    def _mr_replay(session, p, request_id, digest):
        old = session.get(Receipt, (p.id, request_id))
        if old:
            if old.digest != digest:
                raise MistrealmError("同一请求编号不能用于不同操作")
            return old.result
        return None

    @staticmethod
    def _mr_save(session, p, request_id, digest, result, room, now):
        session.add(Receipt(player_id=p.id, request_id=request_id, room_id=room.id,
                            digest=digest, result=result, created_at=now))
        return result

    def mistrealm_create(self, uid, request_id, now, deck_id=None):
        self._mr_rate(uid, "create", 5, now)
        with self._session() as session:
            p = self._mr_player(session, uid)
            digest = self._mr_digest({"action": "create", "deck_id": deck_id})
            old = self._mr_replay(session, p, request_id, digest)
            if old is not None:
                return old
            self._mr_clear_queue(p)
            room = self._mr_active(session, p, now)
            if room is None:
                room = self._mr_new_room(session, p, now, self._mr_deck_snapshot(session,p,deck_id) if deck_id else None)
            result = self._mr_view(session, room, p)
            return self._mr_save(session, p, request_id, digest, result, room, now)

    def mistrealm_join(self, uid, code, request_id, now, deck_id=None):
        self._mr_rate(uid, "join", 20, now)
        with self._session() as session:
            p = self._mr_player(session, uid)
            digest = self._mr_digest({"action": "join", "code": code, "deck_id": deck_id})
            old = self._mr_replay(session, p, request_id, digest)
            if old is not None:
                return old
            self._mr_clear_queue(p)
            room = self._mr_active(session, p, now)
            if room is None:
                room = session.scalar(select(Room).where(Room.active_code == code).with_for_update())
                if room is None:
                    raise MistrealmError("房间码不存在或已失效", 404)
                self._mr_advance(session, room, now)
                if room.phase == "closed":
                    raise MistrealmError("房间码已失效", 404)
                if session.get(Seat, (room.id, 1)):
                    raise MistrealmError("房间已满")
                if room.state.get('rules_version',1) != (2 if deck_id else 1):
                    raise MistrealmError('房间规则版本不同，请使用对应入口')
                payload={'uid':uid}
                if deck_id: payload['deck']=self._mr_deck_snapshot(session,p,deck_id)
                state = _engine(room.state).apply_action(room.state, 1, "join", payload, ms(now), SystemRandom())
                self._mr_sync(session, room, state)
                session.add(Seat(room_id=room.id, seat_index=1, player_id=p.id))
                session.flush()
            result = self._mr_view(session, room, p)
            return self._mr_save(session, p, request_id, digest, result, room, now)

    def mistrealm_view(self, room_id, uid, now):
        with self._session() as session:
            p = self._mr_player(session, uid)
            room = self._mr_room(session, room_id)
            # Authorize before advancing or emitting any room data.
            self._mr_view(session, room, p)
            self._mr_advance(session, room, now)
            self._mr_story_drive(session, room, p, now)
            if room.phase == "closed":
                return {"room_id": str(room.id), "code": None,
                        "match_id": str(room.match_id) if room.match_id else None,
                        "state": {"phase": "closed", "version": room.state["version"]}}
            result=self._mr_view(session, room, p)
            if room.state.get('rules_version')==2: result['state']['server_time_ms']=ms(now)
            return result

    def mistrealm_action(self, room_id, uid, match_id, version, request_id, action, payload, now):
        self._mr_rate(uid, "action", 120, now)
        # Persist elapsed deadlines independently of a stale or invalid submitted action.
        with self._session() as session:
            p = self._mr_player(session, uid)
            digest = self._mr_digest(dict(room=room_id, match=match_id, version=version, action=action, payload=payload))
            old = self._mr_replay(session, p, request_id, digest)
            if old is not None:
                return old
            room = self._mr_room(session, room_id)
            self._mr_view(session, room, p)
            self._mr_advance(session, room, now)
        with self._session() as session:
            p = self._mr_player(session, uid)
            digest = self._mr_digest(dict(room=room_id, match=match_id, version=version, action=action, payload=payload))
            old = self._mr_replay(session, p, request_id, digest)
            if old is not None:
                return old
            room = self._mr_room(session, room_id)
            view = self._mr_view(session, room, p)
            self._mr_advance(session, room, now)
            if room.match_id != match_id or room.state["version"] != version:
                raise MistrealmError("房间状态已更新，请刷新")
            seat = view["state"]["seat"]
            if room.state.get('rules_version')==2 and action=='select_deck':
                payload={'deck':self._mr_deck_snapshot(session,p,UUID(payload['deck_id']))}
            state = _engine(room.state).apply_action(room.state, seat, action, payload, ms(now), SystemRandom())
            if room.state.get("mode") == "story" and action == "rematch":
                raise MistrealmError("剧情关卡请从章节页重新开始")
            if action == "start" or (room.state.get("rules_version")==2 and room.state["phase"]=="waiting" and state["phase"]!="waiting"):
                room.match_id = uuid4()
            elif state["phase"] == "waiting":
                room.match_id = None
            self._mr_sync(session, room, state)
            self._mr_story_drive(session, room, p, now)
            if action == "leave" and state["phase"] == "waiting":
                session.execute(delete(Seat).where(Seat.room_id == room.id, Seat.player_id == p.id))
            if state["phase"] == "closed" or (action == "leave" and state["phase"] == "waiting"):
                result = {"room_id": str(room.id), "code": None, "match_id": None,
                          "state": {"phase": "closed", "version": state["version"]}}
            else:
                result = self._mr_view(session, room, p)
            return self._mr_save(session, p, request_id, digest, result, room, now)

    def mistrealm_story_progress(self, uid, now):
        with self._session() as session:
            player = self._mr_player(session, uid)
            progress = self._mr_story_progress_record(session, player, now)
            return story.public_chapters(progress.completed_chapters)

    def mistrealm_story_start(self, uid, chapter, deck_id, now):
        self._mr_rate(uid, "story", 10, now)
        with self._session() as session:
            player = self._mr_player(session, uid)
            progress = self._mr_story_progress_record(session, player, now)
            available = story.public_chapters(progress.completed_chapters)
            if chapter > available["unlocked"]:
                raise MistrealmError("请先完成前一章", 403)
            current = self._mr_active(session, player, now)
            if current is not None:
                if current.state.get("mode") == "story":
                    return self._mr_view(session, current, player)
                raise MistrealmError("请先结束当前玩家对局")
            self._mr_clear_queue(player)
            state = story.new_story_state(
                uid,
                self._mr_deck_snapshot(session, player, deck_id),
                chapter,
                ms(now),
                SystemRandom(),
            )
            room = Room(
                host_id=player.id,
                active_code=None,
                phase=state["phase"],
                match_id=uuid4(),
                state=state,
                created_at=now,
                deadline=None,
            )
            session.add(room)
            session.flush()
            session.add(Seat(room_id=room.id, seat_index=0, player_id=player.id))
            self._mr_sync(session, room, state)
            session.flush()
            self._mr_story_finish(session, room, player, now)
            return self._mr_view(session, room, player)

    @staticmethod
    def _mr_channel_item(session, message):
        player = session.get(Player, message.player_id)
        item = {
            "id": str(message.id),
            "kind": message.kind,
            "text": message.text,
            "created_at": message.created_at.isoformat(),
            "player": {"uid": player.platform_uid, "name": player.name, "avatar": player.avatar},
        }
        if message.kind == "challenge":
            room = session.get(Room, message.room_id)
            waiting = bool(
                room
                and room.phase == "waiting"
                and room.active_code
                and room.state.get("mode") != "story"
                and room.state["players"][1] is None
            )
            item["challenge"] = {
                "room_id": str(message.room_id),
                "status": "waiting" if waiting else "ended",
                "code": room.active_code if waiting else None,
            }
        return item

    def mistrealm_channel_messages(self, uid, limit, now):
        with self._session() as session:
            self._mr_player(session, uid)
            rows = list(
                session.scalars(
                    select(ChannelMessage)
                    .where(ChannelMessage.deleted_at.is_(None))
                    .order_by(ChannelMessage.created_at.desc(), ChannelMessage.id.desc())
                    .limit(limit)
                )
            )
            return {"items": [self._mr_channel_item(session, row) for row in reversed(rows)]}

    def _mr_channel_guard(self, player, now):
        if player.channel_muted_until and player.channel_muted_until > now:
            raise MistrealmError(
                "你已被频道禁言至" + player.channel_muted_until.isoformat(), 403
            )

    def mistrealm_channel_post(self, uid, text, now):
        self._mr_rate(uid, "channel", 6, now)
        content = text.strip()
        if not content or len(content) > 200:
            raise MistrealmError("消息需要1至200字", 422)
        with self._session() as session:
            player = self._mr_player(session, uid)
            self._mr_channel_guard(player, now)
            message = ChannelMessage(
                player_id=player.id, kind="text", text=content, created_at=now
            )
            session.add(message)
            session.flush()
            return self._mr_channel_item(session, message)

    def mistrealm_channel_challenge(self, uid, room_id, now):
        self._mr_rate(uid, "channel", 6, now)
        with self._session() as session:
            player = self._mr_player(session, uid)
            self._mr_channel_guard(player, now)
            room = self._mr_room(session, room_id)
            if (
                room.host_id != player.id
                or room.phase != "waiting"
                or room.active_code is None
                or room.state.get("mode") == "story"
                or room.state["players"][1] is not None
            ):
                raise MistrealmError("当前房间不能发布约战")
            old = session.scalar(
                select(ChannelMessage).where(
                    ChannelMessage.room_id == room.id,
                    ChannelMessage.kind == "challenge",
                    ChannelMessage.deleted_at.is_(None),
                )
            )
            if old is not None:
                return self._mr_channel_item(session, old)
            message = ChannelMessage(
                player_id=player.id,
                kind="challenge",
                room_id=room.id,
                created_at=now,
            )
            session.add(message)
            session.flush()
            return self._mr_channel_item(session, message)

    def advance_mistrealm_deadlines(self, now):
        with self._session() as session:
            rooms = session.scalars(select(Room).where(Room.deadline <= now).with_for_update(skip_locked=True))
            for room in rooms:
                self._mr_advance(session, room, now)


    @staticmethod
    def _mr_clear_queue(p):
        p.queue_ticket = p.queued_at = p.queue_expires_at = None
        p.queue_snapshot = None
        p.queue_rules_version = 1

    @staticmethod
    def _mr_queue_status(p, now):
        if not p.queue_ticket or p.queue_expires_at <= now:
            return {"status": "idle"}
        result = {"status": "waiting", "ticket": str(p.queue_ticket),
                "queued_at_ms": ms(p.queued_at), "expires_at_ms": ms(p.queue_expires_at),
                "elapsed_ms": max(0, ms(now)-ms(p.queued_at))}
        if p.queue_rules_version == 2:
            snapshot = p.queue_snapshot
            result.update(rules_version=2, deck=dict(id=snapshot['deck_id'],name=snapshot.get('name','已锁定军团'),faction=snapshot['faction'],leader=snapshot['leader']))
        return result

    def _mr_new_room(self, session, host, now, deck_snapshot=None):
        for _ in range(100):
            try:
                with session.begin_nested():
                    state = classic.new_state(host.platform_uid, deck_snapshot, ms(now)) if deck_snapshot else legacy.new_state(host.platform_uid, ms(now))
                    room = Room(host_id=host.id, active_code=f"{randbelow(1000000):06d}",
                                phase="waiting", state=state, created_at=now,
                                deadline=now+timedelta(minutes=30))
                    session.add(room)
                    session.flush()
                break
            except IntegrityError:
                continue
        else:
            raise MistrealmError("暂时无法生成房间码")
        session.add(Seat(room_id=room.id, seat_index=0, player_id=host.id))
        session.flush()
        return room

    def mistrealm_matchmaking(self, uid, operation, ticket, now, rules_version=1, deck_id=None):
        if operation not in ("start", "heartbeat", "cancel"):
            raise MistrealmError("匹配操作不正确", 422)
        if operation == "start":
            self._mr_rate(uid, "matchmaking", 10, now)
        with self._session() as session:
            p = self._mr_player(session, uid)
            room = self._mr_active(session, p, now)
            if room:
                self._mr_clear_queue(p)
                return {"status": "matched", "room": self._mr_view(session, room, p)}
            current = self._mr_queue_status(p, now)
            if current['status']=='waiting' and p.queue_rules_version!=rules_version:
                if operation=='start': raise MistrealmError('请先取消另一规则的匹配')
                return {'status':'idle'}
            if operation=='start' and rules_version==2 and current['status']=='waiting' and str(deck_id)!=p.queue_snapshot['deck_id']:
                raise MistrealmError('请先取消匹配再更换牌组')
            if operation == "cancel":
                if str(p.queue_ticket) == str(ticket):
                    self._mr_clear_queue(p)
                return self._mr_queue_status(p, now)
            if operation == "heartbeat":
                if current["status"] != "waiting" or str(p.queue_ticket) != str(ticket):
                    return {"status": "idle"}
            elif current["status"] != "waiting":
                p.queue_ticket, p.queued_at = uuid4(), now
                p.queue_rules_version = rules_version
                p.queue_snapshot = self._mr_deck_snapshot(session,p,deck_id) if rules_version==2 else None
            p.queue_expires_at = now+timedelta(seconds=20)
            session.flush()
            # Lock the caller first; SKIP LOCKED avoids reciprocal candidate deadlocks.
            # Custom-room entry uses the same player lock and clears its queue lease.
            candidate = session.scalar(
                select(Player).where(
                    Player.id != p.id, Player.queue_ticket.is_not(None),
                    Player.queue_expires_at > now, Player.queue_rules_version == rules_version,
                    ~select(Seat.player_id).where(Seat.player_id == Player.id).exists(),
                ).order_by(Player.queued_at, Player.id).with_for_update(skip_locked=True).limit(1)
            )
            if candidate is None:
                return self._mr_queue_status(p, now)
            room = self._mr_new_room(session, candidate, now, candidate.queue_snapshot if rules_version==2 else None)
            join_payload={'uid':uid}
            if rules_version==2: join_payload['deck']=deepcopy(p.queue_snapshot)
            state = _engine(room.state).apply_action(room.state, 1, "join", join_payload, ms(now), SystemRandom())
            if rules_version==2:
                state=classic.apply_action(state,0,'lock',{},ms(now),SystemRandom())
                state=classic.apply_action(state,1,'lock',{},ms(now),SystemRandom())
                room.match_id=uuid4()
            self._mr_sync(session, room, state)
            session.add(Seat(room_id=room.id, seat_index=1, player_id=p.id))
            self._mr_clear_queue(candidate)
            self._mr_clear_queue(p)
            session.flush()
            return {"status": "matched", "room": self._mr_view(session, room, p)}

    @staticmethod
    def _mr_deck(session, player, deck_id):
        deck=session.scalar(select(Deck).where(Deck.id==deck_id,Deck.player_id==player.id).with_for_update())
        if deck is None: raise MistrealmError('牌组不存在',404)
        return deck

    def _mr_deck_snapshot(self, session, player, deck_id):
        deck=self._mr_deck(session,player,deck_id)
        return dict(deck_id=str(deck.id),name=deck.name,**validate_deck(deck.faction,deck.leader,deck.counts))

    @staticmethod
    def _mr_deck_view(deck):
        return dict(id=str(deck.id),name=deck.name,faction=deck.faction,leader=deck.leader,counts=deepcopy(deck.counts))

    def mistrealm_decks(self, uid, now):
        with self._session() as session:
            player=self._mr_player(session,uid)
            return {'decks':[self._mr_deck_view(d) for d in session.scalars(select(Deck).where(Deck.player_id==player.id).order_by(Deck.updated_at,Deck.id))]}

    def mistrealm_save_deck(self, uid, deck_id, name, faction, leader, counts, now):
        self._mr_rate(uid,'deck',60,now)
        snapshot=validate_deck(faction,leader,counts)
        if not isinstance(name,str) or not name.strip() or len(name)>40: raise ValueError('牌组名称需要1至40字')
        with self._session() as session:
            player=self._mr_player(session,uid)
            deck=self._mr_deck(session,player,deck_id) if deck_id else Deck(player_id=player.id)
            deck.name=name.strip();deck.updated_at=now
            deck.faction,deck.leader,deck.counts=snapshot['faction'],snapshot['leader'],snapshot['counts']
            session.add(deck);session.flush()
            return self._mr_deck_view(deck)

    def mistrealm_delete_deck(self, uid, deck_id, now):
        with self._session() as session:
            player=self._mr_player(session,uid)
            deck=self._mr_deck(session,player,deck_id)
            if self._mr_queue_status(player,now)['status']=='waiting' and player.queue_snapshot and player.queue_snapshot.get('deck_id')==str(deck_id):
                raise MistrealmError('匹配中的牌组不能删除')
            room=self._mr_active(session,player,now)
            if room and room.state.get('rules_version')==2:
                for p in room.state['players']:
                    if p and p['uid']==uid and p['locked'] and p['selection'].get('deck_id')==str(deck_id):
                        raise MistrealmError('对局中的牌组不能删除')
            session.delete(deck)
            return {'deleted':True}
