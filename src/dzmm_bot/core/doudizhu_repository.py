"""Transactional doudizhu persistence and recipient-specific projections."""
from datetime import datetime, timedelta
from hashlib import sha256
import json
from secrets import SystemRandom, randbelow
from uuid import UUID, uuid4

from sqlalchemy import select

from .doudizhu_state import apply_action, apply_timeout, new_round
from .schema import (DoudizhuRoomRecord as Room, DoudizhuRoundRecord as Round,
                     DoudizhuRequestRecord as Receipt, DoudizhuMessageRecord as Message,
                     GroupChatRecord, InboundRecord, OutboundRecord, UserRecord)


class DoudizhuRepositoryMixin:
    @staticmethod
    def _ddz_employee(session, platform_id):
        if not isinstance(platform_id, str) or not platform_id or len(platform_id) > 255 or any(c.isspace() for c in platform_id):
            raise ValueError('无法读取玩家身份')
        user = session.scalar(select(UserRecord).where(UserRecord.platform_id == platform_id))
        if user is None:
            raise ValueError('请先入职')
        return user

    @staticmethod
    def _ddz_room(session, room_id):
        room = session.scalar(select(Room).where(Room.id == room_id).with_for_update())
        if room is None:
            raise ValueError('房间不存在')
        return room

    @staticmethod
    def _ddz_announced(session, room):
        return session.scalar(select(OutboundRecord.id).where(
            OutboundRecord.inbound_message_id == room.inbound_id,
            OutboundRecord.group_chat_id == room.group_chat_id,
            OutboundRecord.content_type == 'text', OutboundRecord.status == 'sent').limit(1)) is not None

    def create_doudizhu_room(self, platform_id, group_chat_id, inbound_id, now):
        with self._session() as session:
            user = self._ddz_employee(session, platform_id)
            inbound = session.scalar(select(InboundRecord).where(InboundRecord.id == inbound_id).with_for_update())
            group = session.get(GroupChatRecord, group_chat_id)
            if not inbound or inbound.group_chat_id != group_chat_id or inbound.sender_platform_id != platform_id or not group or not group.listening_enabled:
                raise ValueError('群聊或入站消息不可用')
            room = session.scalar(select(Room).where(Room.inbound_id == inbound_id))
            if room is None:
                room = Room(group_chat_id=group_chat_id, inbound_id=inbound_id, creator_id=user.id,
                    short_id=uuid4().hex[:12], code=f'{randbelow(10000):04d}',
                    seats=[str(user.id), None, None], ready=[False] * 3, phase='waiting',
                    created_at=now, deadline=now + timedelta(minutes=10))
                session.add(room)
                session.flush()
            return {**self._ddz_view(session, room, user, now), 'code': room.code}

    def _ddz_view(self, session, room, user, now):
        round_row = session.get(Round, room.round_id) if room.round_id else None
        state = round_row.state if round_row else None
        seat = room.seats.index(str(user.id)) if str(user.id) in room.seats else None
        players = []
        for i, uid in enumerate(room.seats):
            person = session.get(UserRecord, UUID(uid)) if uid else None
            players.append({'name': person.display_name if person else '已离职玩家', 'ready': room.ready[i],
                'count': len(state['hands'][i]) if state else 0,
                'trustee': state['trustees'][i] if state else False} if uid else None)
        messages = session.execute(select(Message, UserRecord.display_name).join(UserRecord, UserRecord.id == Message.user_id)
            .where(Message.room_id == room.id, Message.round_id == room.round_id)
            .order_by(Message.created_at.desc(), Message.id.desc()).limit(100)).all()
        return {'id': str(room.id), 'short_id': room.short_id, 'round_id': str(room.round_id) if room.round_id else None,
            'version': room.version, 'phase': room.phase, 'seat': seat, 'players': players,
            'deadline': room.deadline.isoformat() if room.deadline else None, 'server_time': now.isoformat(),
            'hand': list(state['hands'][seat]) if state and seat is not None else [],
            'bottom': list(state['bottom']) if state and state['landlord'] is not None else [],
            'turn': state['turn'] if state else None, 'landlord': state['landlord'] if state else None,
            'bid': state['bid'] if state else 0, 'multiplier': state['multiplier'] if state else 1,
            'previous': state['previous'] if state else None, 'table': state['table'] if state else [None] * 3,
            'result': state['result'] if state else None, 'events': state['events'] if state else [],
            'messages': [{'id': str(m.id), 'name': name, 'text': m.content} for m, name in reversed(messages)]}

    def doudizhu_view(self, room_id, platform_id, now):
        with self._session() as session:
            user = self._ddz_employee(session, platform_id)
            room = self._ddz_room(session, room_id)
            return self._ddz_view(session, room, user, now)

    def list_doudizhu_rooms(self, platform_id, now):
        with self._session() as session:
            self._ddz_employee(session, platform_id)
            rooms = session.scalars(select(Room).where(Room.phase.in_(('waiting', 'bidding', 'playing')))
                .order_by(Room.created_at.desc()).limit(100)).all()
            return [{'id': str(r.id), 'short_id': r.short_id, 'phase': r.phase,
                     'occupied': sum(uid is not None for uid in r.seats)} for r in rooms
                    if self._ddz_announced(session, r) and (r.phase != 'waiting' or r.deadline > now)]

    @staticmethod
    def _ddz_notice(session, room, text):
        group = session.get(GroupChatRecord, room.group_chat_id)
        if group and group.chatroom_id:
            session.add(OutboundRecord(group_chat_id=group.id, destination_chatroom_id=group.chatroom_id,
                delivery_key=group.chatroom_id, delivery_kind='group', text=text))

    def _ddz_deal(self, session, room, now):
        deck = list(range(54))
        SystemRandom().shuffle(deck)
        room.round_number += 1
        row = Round(room_id=room.id, number=room.round_number, state=new_round(tuple(deck), randbelow(3), now))
        session.add(row)
        session.flush()
        room.round_id = row.id
        room.phase = 'bidding'
        room.deadline = datetime.fromisoformat(row.state['deadline'])
        return row

    def _ddz_sync(self, session, room, row, now):
        state = row.state
        if state['phase'] == 'redeal':
            room.redeals += 1
            if room.redeals < 3:
                self._ddz_deal(session, room, now)
                return
            room.phase, room.deadline = 'cancelled', None
            if not row.notice_sent:
                self._ddz_notice(session, room, f'斗地主房间 {room.short_id} 连续三次无人叫分，已取消。')
                row.notice_sent = True
            return
        room.phase = state['phase']
        room.deadline = datetime.fromisoformat(state['deadline']) if state['deadline'] else None
        if room.phase == 'finished' and not row.notice_sent:
            names = [(session.get(UserRecord, UUID(uid)).display_name if session.get(UserRecord, UUID(uid)) else '已离职玩家') for uid in room.seats]
            landlord = state['landlord']
            winners = state['result']['winners']
            lines = ['🃏 斗地主对局结束']
            for i, name in enumerate(names):
                lines.append(f'{"地主" if i == landlord else "农民"}：{name} · {"胜利" if i in winners else "落败"}')
            spring = {'spring': '春天', 'reverse_spring': '反春'}.get(state['result']['spring'])
            lines.append(f'本局倍数：{state["multiplier"]}' + (f'（{spring}）' if spring else ''))
            self._ddz_notice(session, room, '\n'.join(lines))
            row.notice_sent = True

    def doudizhu_action(self, room_id, platform_id, round_id, version, request_id, action, payload, now):
        digest = sha256(json.dumps([str(round_id), version, action, payload], sort_keys=True).encode()).hexdigest()
        with self._session() as session:
            user = self._ddz_employee(session, platform_id)
            room = self._ddz_room(session, room_id)
            receipt = session.scalar(select(Receipt).where(Receipt.room_id == room_id, Receipt.user_id == user.id, Receipt.request_id == request_id))
            if receipt:
                if receipt.digest != digest:
                    raise ValueError('重复请求内容不同')
                return self._ddz_view(session, room, user, now)
            if room.version != version or room.round_id != round_id:
                raise ValueError('牌局已更新，请刷新')
            if room.deadline and now >= room.deadline:
                raise ValueError('操作已超时，请刷新')
            seat = room.seats.index(str(user.id)) if str(user.id) in room.seats else None
            if room.phase == 'waiting':
                seats, ready = list(room.seats), list(room.ready)
                if action == 'claim':
                    if not self._ddz_announced(session, room):
                        raise ValueError('群消息尚未送达')
                    if seat is not None or None not in seats or payload.get('code') != room.code:
                        raise ValueError('入座码错误、已入座或房间已满')
                    seats[seats.index(None)] = str(user.id)
                elif seat is None:
                    raise ValueError('观众不能操作席位')
                elif action in ('ready', 'unready'):
                    ready[seat] = action == 'ready'
                elif action == 'leave':
                    if user.id == room.creator_id:
                        room.phase, room.deadline = 'cancelled', None
                    else:
                        seats[seat], ready[seat] = None, False
                else:
                    raise ValueError('当前不能进行该操作')
                room.seats, room.ready = seats, ready
                if None not in seats and all(ready):
                    if not self._ddz_announced(session, room):
                        raise ValueError('群消息尚未送达')
                    room.code = ''
                    self._ddz_deal(session, room, now)
            else:
                if seat is None or room.phase == 'cancelled':
                    raise ValueError('当前不能进行该操作')
                row = session.get(Round, room.round_id)
                if action == 'rematch' and row.state['phase'] == 'finished':
                    room.round_id, room.phase, room.ready = None, 'waiting', [False] * 3
                    room.redeals = 0
                    room.code = f'{randbelow(10000):04d}'
                    room.deadline = now + timedelta(minutes=10)
                else:
                    row.state = apply_action(row.state, seat, 'takeover' if action == 'leave' else action, payload, now)
                    self._ddz_sync(session, room, row, now)
            room.version += 1
            session.add(Receipt(room_id=room_id, user_id=user.id, request_id=request_id, digest=digest))
            session.flush()
            return self._ddz_view(session, room, user, now)

    def advance_doudizhu_deadlines(self, now):
        with self._session() as session:
            rooms = session.scalars(select(Room).where(Room.phase.in_(('waiting', 'bidding', 'playing')), Room.deadline <= now)
                .order_by(Room.deadline).limit(100).with_for_update(skip_locked=True)).all()
            for room in rooms:
                deadline = room.deadline
                if room.phase == 'waiting':
                    room.phase, room.deadline = 'cancelled', None
                    self._ddz_notice(session, room, f'斗地主房间 {room.short_id} 等待超时，已取消。')
                else:
                    row = session.get(Round, room.round_id)
                    row.state = apply_timeout(row.state, now)
                    self._ddz_sync(session, room, row, deadline)
                room.version += 1
            return len(rooms)
