"""Independent players and serialized room transactions for Mistrealm."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from secrets import SystemRandom, randbelow
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from .mistrealm_state import new_state, apply_action, advance, project
from .schema import (
    MistrealmPlayerRecord as Player, MistrealmRoomRecord as Room,
    MistrealmSeatRecord as Seat, MistrealmRequestRecord as Receipt,
)


class MistrealmError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def ms(now):
    if now.tzinfo is None:
        raise ValueError("时间必须包含时区")
    return int(now.timestamp()*1000)


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

    def _mr_advance(self, session, room, now):
        state = advance(room.state, ms(now), SystemRandom())
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
        state = project(room.state, seat.seat_index)
        # Seat table is authoritative for active membership.
        for entry in session.scalars(select(Seat).where(Seat.room_id == room.id)):
            profile = session.get(Player, entry.player_id)
            state["players"][entry.seat_index].update(name=profile.name, avatar=profile.avatar)
        return {"room_id": str(room.id), "code": room.active_code,
                "match_id": str(room.match_id) if room.match_id else None, "state": state}

    def mistrealm_me(self, uid, now):
        with self._session() as session:
            p = self._mr_player(session, uid)
            room = self._mr_active(session, p, now)
            return {"uid": uid, "name": p.name, "avatar": p.avatar,
                    "room_id": str(room.id) if room else None}

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

    def mistrealm_create(self, uid, request_id, now):
        self._mr_rate(uid, "create", 5, now)
        with self._session() as session:
            p = self._mr_player(session, uid)
            digest = self._mr_digest({"action": "create"})
            old = self._mr_replay(session, p, request_id, digest)
            if old is not None:
                return old
            room = self._mr_active(session, p, now)
            if room is None:
                for _ in range(100):
                    code = f"{randbelow(1000000):06d}"
                    try:
                        with session.begin_nested():
                            state = new_state(uid, ms(now))
                            room = Room(host_id=p.id, active_code=code, phase="waiting",
                                        state=state, created_at=now,
                                        deadline=datetime.fromtimestamp(state["deadline_ms"]/1000, timezone.utc))
                            session.add(room)
                            session.flush()
                        break
                    except IntegrityError:
                        continue
                else:
                    raise MistrealmError("暂时无法生成房间码")
                session.add(Seat(room_id=room.id, seat_index=0, player_id=p.id))
                session.flush()
            result = self._mr_view(session, room, p)
            return self._mr_save(session, p, request_id, digest, result, room, now)

    def mistrealm_join(self, uid, code, request_id, now):
        self._mr_rate(uid, "join", 20, now)
        with self._session() as session:
            p = self._mr_player(session, uid)
            digest = self._mr_digest({"action": "join", "code": code})
            old = self._mr_replay(session, p, request_id, digest)
            if old is not None:
                return old
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
                state = apply_action(room.state, 1, "join", {"uid": uid}, ms(now), SystemRandom())
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
            if room.phase == "closed":
                return {"room_id": str(room.id), "code": None,
                        "match_id": str(room.match_id) if room.match_id else None,
                        "state": {"phase": "closed", "version": room.state["version"]}}
            return self._mr_view(session, room, p)

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
            state = apply_action(room.state, seat, action, payload, ms(now), SystemRandom())
            if action == "start":
                room.match_id = uuid4()
            elif state["phase"] == "waiting":
                room.match_id = None
            self._mr_sync(session, room, state)
            if action == "leave" and state["phase"] == "waiting":
                session.execute(delete(Seat).where(Seat.room_id == room.id, Seat.player_id == p.id))
            if state["phase"] == "closed" or (action == "leave" and state["phase"] == "waiting"):
                result = {"room_id": str(room.id), "code": None, "match_id": None,
                          "state": {"phase": "closed", "version": state["version"]}}
            else:
                result = self._mr_view(session, room, p)
            return self._mr_save(session, p, request_id, digest, result, room, now)

    def advance_mistrealm_deadlines(self, now):
        with self._session() as session:
            rooms = session.scalars(select(Room).where(Room.deadline <= now).with_for_update(skip_locked=True))
            for room in rooms:
                self._mr_advance(session, room, now)
