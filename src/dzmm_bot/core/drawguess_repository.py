"""Transactional draw-and-guess persistence and recipient projections."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from math import isfinite
from secrets import SystemRandom, randbelow
from uuid import UUID, uuid4

from sqlalchemy import delete, select

from .drawguess_state import advance, apply_action, new_state
from .drawguess_words import WORDS
from .schema import (
    DrawguessEventRecord as Event,
    DrawguessMessageRecord as Message,
    DrawguessRequestRecord as Receipt,
    DrawguessRoomRecord as Room,
    GroupChatRecord,
    InboundRecord,
    OutboundRecord,
    UserRecord,
)


class DrawguessRateLimitError(ValueError):
    pass


class DrawguessRepositoryMixin:
    @staticmethod
    def _dg_ms(now: datetime) -> int:
        if now.tzinfo is None:
            raise ValueError("时间必须包含时区")
        return int(now.timestamp() * 1000)

    @staticmethod
    def _dg_employee(session, platform_id):
        if not isinstance(platform_id, str) or not platform_id or len(platform_id) > 255 or any(char.isspace() for char in platform_id):
            raise ValueError("无法读取玩家身份")
        user = session.scalar(select(UserRecord).where(UserRecord.platform_id == platform_id))
        if user is None:
            raise ValueError("请先入职")
        return user

    @staticmethod
    def _dg_room(session, room_id):
        room = session.scalar(select(Room).where(Room.id == room_id).with_for_update())
        if room is None:
            raise ValueError("房间不存在")
        return room

    @staticmethod
    def _dg_announced(session, room):
        return session.scalar(select(OutboundRecord.id).where(
            OutboundRecord.inbound_message_id == room.inbound_id,
            OutboundRecord.group_chat_id == room.group_chat_id,
            OutboundRecord.content_type == "text", OutboundRecord.status == "sent",
        ).limit(1)) is not None

    @staticmethod
    def _dg_sync_room(room, state):
        room.state = state
        room.phase = state["phase"]
        deadline = state.get("deadline_ms")
        room.deadline = datetime.fromtimestamp(deadline / 1000, timezone.utc) if deadline is not None else None
        if state["phase"] != "waiting":
            room.active_code = None

    @staticmethod
    def _dg_prune_turn(session, room_id, turn_id):
        for model in (Event, Receipt):
            session.execute(delete(model).where(model.room_id == room_id, model.turn_id != turn_id))

    @staticmethod
    def _dg_candidates(state):
        available = [word.id for word in WORDS if word.id not in set(state.get("used_words", []))]
        if len(available) < 3:
            raise ValueError("词库可用词不足")
        return SystemRandom().sample(available, 3)

    @staticmethod
    def _dg_code(session):
        for _ in range(100):
            code = f"{randbelow(10_000):04d}"
            if session.scalar(select(Room.id).where(Room.active_code == code).limit(1)) is None:
                return code
        raise ValueError("暂时无法生成入座码")

    def create_drawguess_room(self, platform_id, group_chat_id, inbound_id, now):
        with self._session() as session:
            user = self._dg_employee(session, platform_id)
            inbound = session.scalar(select(InboundRecord).where(InboundRecord.id == inbound_id).with_for_update())
            group = session.get(GroupChatRecord, group_chat_id)
            if (not inbound or inbound.group_chat_id != group_chat_id or
                    inbound.sender_platform_id != platform_id or not group or not group.listening_enabled):
                raise ValueError("群聊或入站消息不可用")
            room = session.scalar(select(Room).where(Room.inbound_id == inbound_id))
            if room is None:
                state = new_state(str(user.id), self._dg_ms(now))
                room = Room(
                    group_chat_id=group_chat_id, inbound_id=inbound_id, creator_id=user.id,
                    short_id=uuid4().hex[:12], active_code=self._dg_code(session), state=state,
                    cursor=0, phase="waiting", created_at=now,
                    deadline=now + timedelta(minutes=10),
                )
                session.add(room)
                session.flush()
            return {**self._dg_view(session, room, user, now), "code": room.active_code}

    def _dg_advance(self, session, room, now):
        now_ms = self._dg_ms(now)
        state = room.state
        for _ in range(64):
            deadline = state.get("deadline_ms")
            if deadline is None or now_ms < deadline:
                break
            old_turn = state.get("turn_id")
            changed = advance(state, now_ms, self._dg_candidates(state))
            if changed == state:
                break
            state = changed
            if state.get("turn_id") != old_turn:
                self._dg_prune_turn(session, room.id, state["turn_id"])
        else:
            raise ValueError("房间状态推进过多，请稍后重试")
        if state != room.state:
            self._dg_sync_room(room, state)

    @staticmethod
    def _dg_canvas(session, room):
        turn_id = room.state["turn_id"]
        rows = session.scalars(select(Event).where(
            Event.room_id == room.id, Event.turn_id == turn_id,
        ).order_by(Event.seq)).all()
        visible = []
        for row in rows:
            operation = {"seq": row.seq, "turn_id": row.turn_id, **row.operation}
            if operation["op"] == "clear":
                visible = []
            elif operation["op"] == "undo":
                stroke_id = operation.get("stroke_id")
                visible = [item for item in visible if item.get("stroke_id") != stroke_id]
            else:
                visible.append(operation)
        return visible

    def _dg_view(self, session, room, user, now):
        state = room.state
        seat_ids = state["seats"]
        self_id = str(user.id)
        self_seat = seat_ids.index(self_id) if self_id in seat_ids else None
        people = {uid: session.get(UserRecord, UUID(uid)) for uid in seat_ids}
        players = []
        for index, uid in enumerate(seat_ids):
            person = people[uid]
            players.append({
                "name": person.display_name if person else "已离职玩家",
                "ready": state["ready"][index] if index < len(state["ready"]) else False,
                "score": state["scores"].get(uid, 0), "is_host": uid == state["host"],
                "guessed": uid in state.get("guessed", []),
            })
        public = {
            "phase": state["phase"], "version": state["version"],
            "match_id": state["match_id"], "turn_id": state["turn_id"],
            "turn_index": state["turn_index"], "deadline_ms": state.get("deadline_ms"),
            "players": players, "host_name": people[state["host"]].display_name if state["host"] in people else "已离职玩家",
            "drawer_seat": state["turn_index"] % len(seat_ids) if seat_ids and state["phase"] not in {"waiting", "finished", "closed"} else None,
            "ranking": [
                {"name": people[item["player"]].display_name if people.get(item["player"]) else "已离职玩家",
                 "score": item["score"], "rank": item["rank"]}
                for item in state.get("ranking", [])
            ],
            "turn_points": {
                str(seat_ids.index(uid)): points for uid, points in state.get("turn_points", {}).items() if uid in seat_ids
            },
        }
        drawer = seat_ids[public["drawer_seat"]] if public["drawer_seat"] is not None else None
        if state["phase"] == "selecting" and self_id == drawer:
            public["candidates"] = [
                {"id": word.id, "answer": word.answer}
                for word in WORDS if word.id in state["candidates"]
            ]
            public["candidates"].sort(key=lambda item: state["candidates"].index(item["id"]))
        if state["phase"] == "drawing":
            public["word_length"] = len(state["answer"])
            if self_id == drawer:
                public["answer"] = state["answer"]
        elif state["phase"] in {"revealing", "finished"} and state.get("answer"):
            public["answer"] = state["answer"]
        message_rows = session.execute(select(Message, UserRecord.display_name).join(
            UserRecord, UserRecord.id == Message.user_id,
        ).where(Message.room_id == room.id)
            .order_by(Message.created_at.desc(), Message.id.desc()).limit(100)).all()
        messages = [
            {"id": str(message.id), "name": name, "text": message.content}
            for message, name in reversed(message_rows)
        ]
        return {
            "room_id": str(room.id), "short_id": room.short_id, "cursor": room.cursor,
            "server_time_ms": self._dg_ms(now), "self_seat": self_seat, "state": public,
            "canvas": self._dg_canvas(session, room), "messages": messages,
            "code": room.active_code if self_seat is not None and state["phase"] == "waiting" else None,
        }

    def drawguess_view(self, room_id, platform_id, now):
        with self._session() as session:
            user = self._dg_employee(session, platform_id)
            room = self._dg_room(session, room_id)
            self._dg_advance(session, room, now)
            return self._dg_view(session, room, user, now)

    def list_drawguess_rooms(self, platform_id, now):
        with self._session() as session:
            user = self._dg_employee(session, platform_id)
            rooms = session.scalars(select(Room).where(Room.phase.notin_(("closed",)))
                .order_by(Room.created_at.desc()).limit(100)).all()
            result = []
            for room in rooms:
                self._dg_advance(session, room, now)
                if room.phase == "closed" or not self._dg_announced(session, room):
                    continue
                seats = room.state["seats"]
                result.append({
                    "room_id": str(room.id), "short_id": room.short_id, "phase": room.phase,
                    "occupied": len(seats), "capacity": 8,
                    "mine": str(user.id) in seats,
                })
            return result

    def drawguess_action(self, room_id, platform_id, turn_id, version, request_id, action, payload, now):
        digest = sha256(json.dumps([turn_id, version, action, payload], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        expired = False
        with self._session() as session:
            user = self._dg_employee(session, platform_id)
            room = self._dg_room(session, room_id)
            receipt = session.scalar(select(Receipt).where(
                Receipt.room_id == room_id, Receipt.user_id == user.id, Receipt.request_id == request_id,
            ))
            if receipt:
                if receipt.digest != digest:
                    raise ValueError("重复请求内容不同")
                return self._dg_view(session, room, user, now)
            if room.deadline and now >= room.deadline:
                if room.phase == "waiting":
                    state = advance(room.state, self._dg_ms(now), self._dg_candidates(room.state))
                    self._dg_sync_room(room, state)
                    expired = True
                else:
                    raise ValueError("操作已超时，请刷新")
            if not expired:
                state = room.state
                if state["turn_id"] != turn_id or state["version"] != version:
                    raise ValueError("房间已更新，请刷新")
                user_id = str(user.id)
                if action == "rematch":
                    if state["phase"] != "finished" or user_id != state["host"]:
                        raise ValueError("只有房主可发起下一局")
                    fresh = new_state(state["host"], self._dg_ms(now))
                    fresh.update(
                        seats=list(state["seats"]), ready=[False] * len(state["seats"]),
                        scores={uid: 0 for uid in state["seats"]}, match_id=state["match_id"],
                        version=state["version"] + 1,
                    )
                    session.execute(delete(Event).where(Event.room_id == room.id))
                    session.execute(delete(Receipt).where(Receipt.room_id == room.id))
                    room.active_code = self._dg_code(session)
                    self._dg_sync_room(room, fresh)
                else:
                    if state["phase"] == "waiting" and action == "claim":
                        if not self._dg_announced(session, room):
                            raise ValueError("群消息尚未送达")
                        if payload.get("code") != room.active_code:
                            raise ValueError("入座码错误")
                    elif state["phase"] != "waiting" and action == "claim":
                        raise ValueError("游戏进行中，仅可观战")
                    candidates = self._dg_candidates(state) if action == "start" else list(state.get("candidates", []))
                    changed = apply_action(state, user_id, action, payload, self._dg_ms(now), candidates)
                    if changed.get("turn_id") != state.get("turn_id"):
                        self._dg_prune_turn(session, room.id, changed["turn_id"])
                    self._dg_sync_room(room, changed)
                session.add(Receipt(
                    room_id=room_id, user_id=user.id, request_id=request_id,
                    digest=digest, turn_id=turn_id, created_at=now,
                ))
                session.flush()
                return self._dg_view(session, room, user, now)
        if expired:
            raise ValueError("入座码已过期")
        raise ValueError("操作失败")

    @staticmethod
    def _dg_validate_operations(operations):
        if not isinstance(operations, list) or not operations:
            raise ValueError("请提交画笔操作")
        if len(json.dumps(operations, ensure_ascii=False).encode()) > 16 * 1024:
            raise ValueError("单批画笔数据不能超过 16 KiB")
        point_count = 0
        result = []
        for operation in operations:
            if not isinstance(operation, dict) or operation.get("op") not in {"begin", "append", "end", "undo", "clear"}:
                raise ValueError("画笔操作不正确")
            kind = operation["op"]
            if kind == "clear":
                if set(operation) != {"op"}:
                    raise ValueError("清空参数不正确")
                result.append({"op": "clear"})
                continue
            if kind == "undo":
                if set(operation) != {"op", "stroke_id"} or not isinstance(operation["stroke_id"], str):
                    raise ValueError("撤销参数不正确")
                result.append({"op": "undo", "stroke_id": operation["stroke_id"]})
                continue
            required = {"op", "stroke_id", "points", "color", "width", "tool"}
            if set(operation) != required or not isinstance(operation["stroke_id"], str) or not 1 <= len(operation["stroke_id"]) <= 64:
                raise ValueError("笔触参数不正确")
            points = operation["points"]
            if not isinstance(points, list):
                raise ValueError("笔触坐标不正确")
            point_count += len(points)
            if point_count > 256:
                raise ValueError("单批最多 256 个坐标点")
            if any(not isinstance(point, list) or len(point) != 2 or
                   any(type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1 for value in point)
                   for point in points):
                raise ValueError("笔触坐标不正确")
            if operation["color"] not in {"#222222", "#ef5b5b", "#f59e0b", "#22a06b", "#3b82f6", "#8b5cf6", "#ffffff"}:
                raise ValueError("画笔颜色不正确")
            if operation["width"] not in {0.003, 0.008, 0.016} or operation["tool"] not in {"pen", "eraser"}:
                raise ValueError("画笔工具不正确")
            result.append(deepcopy(operation))
        return result

    def drawguess_strokes(self, room_id, platform_id, turn_id, request_id, operations, now):
        operations = self._dg_validate_operations(operations)
        digest = sha256(json.dumps(["strokes", turn_id, operations], sort_keys=True).encode()).hexdigest()
        with self._session() as session:
            user = self._dg_employee(session, platform_id)
            room = self._dg_room(session, room_id)
            receipt = session.scalar(select(Receipt).where(
                Receipt.room_id == room_id, Receipt.user_id == user.id, Receipt.request_id == request_id,
            ))
            if receipt:
                if receipt.digest != digest:
                    raise ValueError("重复请求内容不同")
                return {"cursor": room.cursor}
            state = room.state
            drawer = state["seats"][state["turn_index"] % len(state["seats"])] if state["seats"] else None
            if state["phase"] != "drawing" or state["turn_id"] != turn_id or str(user.id) != drawer:
                raise ValueError("只有当前画手可以绘画")
            current = self._dg_canvas(session, room)
            active_points = sum(len(item.get("points", [])) for item in current)
            for operation in operations:
                if operation["op"] == "clear":
                    active_points = 0
                elif operation["op"] == "undo":
                    active_points -= sum(len(item.get("points", [])) for item in current if item.get("stroke_id") == operation["stroke_id"])
                else:
                    active_points += len(operation["points"])
                if active_points > 30_000:
                    raise ValueError("本题画布已达上限")
                room.cursor += 1
                session.add(Event(
                    room_id=room.id, seq=room.cursor, turn_id=turn_id,
                    operation=operation, created_at=now,
                ))
            session.add(Receipt(
                room_id=room_id, user_id=user.id, request_id=request_id,
                digest=digest, turn_id=turn_id, created_at=now,
            ))
            session.flush()
            return {"cursor": room.cursor}

    def drawguess_chat(self, room_id, platform_id, turn_id, request_id, text, now):
        content = text.strip() if isinstance(text, str) else ""
        if not 1 <= len(content) <= 100:
            raise ValueError("消息需要 1～100 字")
        digest = sha256(json.dumps(["chat", turn_id, content], ensure_ascii=False).encode()).hexdigest()
        with self._session() as session:
            user = self._dg_employee(session, platform_id)
            room = self._dg_room(session, room_id)
            receipt = session.scalar(select(Receipt).where(
                Receipt.room_id == room_id, Receipt.user_id == user.id, Receipt.request_id == request_id,
            ))
            old = session.scalar(select(Message).where(
                Message.room_id == room_id, Message.user_id == user.id, Message.request_id == request_id,
            ))
            if receipt:
                if receipt.digest != digest:
                    raise ValueError("重复请求内容不同")
                if old is None:
                    raise ValueError("重复请求记录不完整")
                return {"id": str(old.id), "name": user.display_name, "text": old.content}
            if old:
                raise ValueError("重复请求记录不完整")
            state = room.state
            user_id = str(user.id)
            if state["phase"] == "closed":
                raise ValueError("房间已经关闭")
            previous = session.scalar(select(Message.created_at).where(
                Message.room_id == room_id, Message.user_id == user.id,
            ).order_by(Message.created_at.desc()).limit(1))
            if previous and (now - previous).total_seconds() < 1:
                raise DrawguessRateLimitError("请间隔一秒再发言")
            if state["turn_id"] != turn_id:
                raise ValueError("本题已更新，请刷新")
            if state["phase"] == "drawing":
                drawer = state["seats"][state["turn_index"] % len(state["seats"])]
                can_guess = (
                    user_id in state["seats"]
                    and user_id != drawer
                    and user_id not in state["guessed"]
                )
                if can_guess:
                    before = state["scores"].get(user_id, 0)
                    state = apply_action(
                        state, user_id, "guess", {"text": content},
                        self._dg_ms(now), state["candidates"],
                    )
                    after = state["scores"].get(user_id, 0)
                    if after > before:
                        content = f"已猜中 +{after - before}分"
                    self._dg_sync_room(room, state)
            message = Message(
                room_id=room_id, turn_id=turn_id, user_id=user.id,
                request_id=request_id, content=content, created_at=now,
            )
            session.add_all((message, Receipt(
                room_id=room_id, user_id=user.id, request_id=request_id,
                digest=digest, turn_id=turn_id, created_at=now,
            )))
            session.flush()
            stale_ids = list(session.scalars(
                select(Message.id).where(Message.room_id == room_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .offset(100)
            ))
            if stale_ids:
                session.execute(delete(Message).where(Message.id.in_(stale_ids)))
            return {"id": str(message.id), "name": user.display_name, "text": content}

    def _dg_events_result(self, session, room, user, after, now):
        current = room.state["turn_id"]
        rows = session.scalars(select(Event).where(
            Event.room_id == room.id, Event.turn_id == current, Event.seq > after,
        ).order_by(Event.seq).limit(201)).all()
        first = session.scalar(select(Event.seq).where(
            Event.room_id == room.id, Event.turn_id == current,
        ).order_by(Event.seq).limit(1))
        reset = after == 0 or after > room.cursor or (first is not None and after < first - 1) or len(rows) > 200
        events = [] if reset else [{"seq": row.seq, "turn_id": row.turn_id, **row.operation} for row in rows]
        result = {
            "cursor": room.cursor, "reset": reset, "events": events,
            "version": room.state["version"],
        }
        if reset:
            result["snapshot"] = self._dg_view(session, room, user, now)
        return result

    def drawguess_events(self, room_id, platform_id, after, now):
        if type(after) is not int or after < 0:
            raise ValueError("事件游标不正确")
        with self._session() as session:
            user = self._dg_employee(session, platform_id)
            room = self._dg_room(session, room_id)
            self._dg_advance(session, room, now)
            return self._dg_events_result(session, room, user, after, now)

    def advance_drawguess_deadlines(self, now):
        with self._session() as session:
            rooms = session.scalars(select(Room).where(
                Room.deadline <= now, Room.phase.in_(("waiting", "selecting", "drawing", "revealing")),
            ).order_by(Room.deadline).limit(100).with_for_update(skip_locked=True)).all()
            for room in rooms:
                self._dg_advance(session, room, now)
            return len(rooms)
