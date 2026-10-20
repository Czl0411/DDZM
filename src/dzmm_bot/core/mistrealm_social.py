"""Presence and bilateral social actions, independent of employee accounts."""
from datetime import timedelta
from secrets import SystemRandom
from zoneinfo import ZoneInfo

from sqlalchemy import select, func, or_, and_, case

from .schema import (MistrealmPlayerRecord as Player, MistrealmSeatRecord as Seat,
                     MistrealmRoomRecord as Room, MistrealmFriendRecord as Friend,
                     MistrealmInviteRecord as Invite, MistrealmDirectMessageRecord as DirectMessage)

from .mistrealm_profile import settings, challenge_permission

ONLINE_TTL = timedelta(seconds=60)
INVITE_TTL = timedelta(seconds=60)


def fail(text, status=409):
    from .mistrealm_repository import MistrealmError
    raise MistrealmError(text,status)


def pair(a,b):
    return tuple(sorted((a,b),key=str))


def midnight(now):
    return now.astimezone(ZoneInfo('Asia/Shanghai')).replace(hour=0,minute=0,second=0,microsecond=0)


def online(p,now):
    return p.online_seen_at is not None and p.online_seen_at > now-ONLINE_TTL


def profile(p):
    return dict(uid=p.platform_uid,name=p.name,avatar=p.avatar)


class MistrealmSocialMixin:
    def _social_pair(self,session,uid,target):
        # Lock both players in stable order; serializes reverse invites and acceptance.
        players=list(session.scalars(select(Player).where(Player.platform_uid.in_([uid,target])).order_by(Player.id).with_for_update().execution_options(populate_existing=True)))
        if uid==target: fail('不能对自己进行此操作')
        if len(players)!=2: fail('玩家不存在',404)
        me=next(p for p in players if p.platform_uid==uid)
        other=next(p for p in players if p.platform_uid==target)
        return me,other

    @staticmethod
    def _social_room(session,p):
        return session.scalar(select(Room).join(Seat,Seat.room_id==Room.id).where(Seat.player_id==p.id,Room.phase!='closed'))

    def _social_idle(self,session,p,now):
        if self._social_room(session,p): fail('请双方先离开当前房间，再发起或接受挑战')
        if p.queue_ticket and p.queue_expires_at>now: fail('请双方先取消匹配，再发起或接受挑战')
        if not online(p,now): fail('玩家已离线，暂时无法挑战')

    @staticmethod
    def _social_invite_view(session,item,me,now):
        other=session.get(Player,item.receiver_id if item.sender_id==me.id else item.sender_id)
        status='expired' if item.status=='pending' and item.expires_at<=now else item.status
        return dict(id=str(item.id),player=profile(other),outgoing=item.sender_id==me.id,
                    status=status,expires_at=item.expires_at.isoformat())

    def mistrealm_social_pulse(self,uid,now,*,touch=True):
        with self._session() as session:
            me=self._mr_player(session,uid)
            if touch: me.online_seen_at=now
            session.flush()
            count=session.scalar(select(func.count()).select_from(Player).where(Player.online_seen_at>now-ONLINE_TTL))
            requests=session.scalar(select(func.count()).select_from(Friend).where(
                or_(Friend.low_id==me.id,Friend.high_id==me.id),Friend.status=='pending',Friend.requester_id!=me.id))
            invitations=list(session.scalars(select(Invite).where(or_(Invite.sender_id==me.id,Invite.receiver_id==me.id),
                Invite.created_at>now-timedelta(days=1)).order_by(Invite.created_at.desc()).limit(50)))
            current=self._social_room(session,me)
            joined=next((i for i in invitations if i.status=='accepted' and current and i.room_id==current.id),None)
            return dict(online_count=count,friend_requests=requests,
                        invitations=[self._social_invite_view(session,i,me,now) for i in invitations],
                        joined_room_id=str(joined.room_id) if joined else None,
                        unread_messages=session.scalar(select(func.count()).select_from(DirectMessage).where(DirectMessage.receiver_id==me.id,DirectMessage.read_at.is_(None))))

    def mistrealm_social_players(self,uid,scope,search,page,now):
        with self._session() as session:
            me=self._mr_player(session,uid)
            relation=or_(and_(Friend.low_id==me.id,Friend.high_id==Player.id),and_(Friend.high_id==me.id,Friend.low_id==Player.id))
            query=select(Player,Friend,Room).outerjoin(Friend,relation).outerjoin(Seat,Seat.player_id==Player.id).outerjoin(Room,Room.id==Seat.room_id).where(Player.id!=me.id)
            if scope=='friends': query=query.where(Friend.status=='accepted')
            if scope=='requests': query=query.where(Friend.status=='pending')
            if search: query=query.where(or_(Player.name.contains(search,autoescape=True),Player.platform_uid==search))
            total=session.scalar(select(func.count()).select_from(query.subquery()))
            entries=session.execute(query.order_by(case((Player.online_seen_at>now-ONLINE_TTL,0),else_=1),Player.name,Player.id).offset(page*6).limit(6)).all()
            items=[self._social_player_view(session,me,p,now) for p,_,_ in entries]
            return dict(items=items,total=total,page=page)

    def _social_player_view(self,session,me,p,now):
        f=session.get(Friend,pair(me.id,p.id));room=self._social_room(session,p)
        phase=room.phase if room else None
        state='offline' if not online(p,now) else 'playing' if phase and phase not in ('waiting','closed','finished') else 'room' if phase and phase!='closed' else 'matching' if p.queue_ticket and p.queue_expires_at>now else 'online'
        friend='friend' if f and f.status=='accepted' else ('sent' if f.requester_id==me.id else 'received') if f and f.status=='pending' else 'none'
        both=or_(and_(Invite.sender_id==me.id,Invite.receiver_id==p.id),and_(Invite.sender_id==p.id,Invite.receiver_id==me.id))
        invitations=list(session.scalars(select(Invite).where(both,Invite.created_at>=midnight(now))))
        pending=any(i.status=='pending' and i.expires_at>now for i in invitations)
        own_busy=bool(self._social_room(session,me) or (me.queue_ticket and me.queue_expires_at>now))
        reason=challenge_permission(p,friend=='friend') or ('请先离开房间或取消匹配' if own_busy else '玩家已离线' if state=='offline' else '玩家暂时忙碌' if state!='online' else '已有待回应挑战' if pending else '今日挑战已用完' if friend!='friend' and invitations else '')
        watch=friend=='friend' and settings(p)['spectate'] and room and room.state.get('rules_version')==3 and room.state.get('balance_revision')==2 and phase in ('choose_first','mulligan','playing','round_result')
        return dict(**profile(p),presence=state,friend=friend,challenge_reason=reason,
                    friend_request_reason='' if settings(p)['friend_requests'] else '暂不接受好友申请',
                    spectate_room_id=str(room.id) if watch else None,spectate_match_id=str(room.match_id) if watch else None)

    def mistrealm_spectate(self,room_id,uid,target,match_id,now):
        with self._session() as session:
            me=self._mr_player(session,uid)
            other=session.scalar(select(Player).where(Player.platform_uid==target))
            if not other or other.id==me.id: fail('只能观战好友的对局',403)
            friend=session.get(Friend,pair(me.id,other.id))
            if not friend or friend.status!='accepted': fail('成为好友后才能观战',403)
            if not settings(other)['spectate']: fail('好友已关闭观战',403)
            if self._social_room(session,me) or (me.queue_ticket and me.queue_expires_at>now):
                fail('请先离开房间或取消匹配，再进入观战')
            room=self._mr_room(session,room_id)
            if not any(p and p['uid']==target for p in room.state['players']): fail('好友不在这场对局中',403)
            if room.state.get('rules_version')!=3 or room.state.get('balance_revision')!=2: fail('该版本对局暂不支持观战')
            if room.match_id!=match_id or room.phase in ('waiting','closed'):
                return dict(room_id=str(room.id),code=None,match_id=str(match_id),state=dict(phase='closed',version=room.state['version']))
            self._mr_advance(session,room,now)
            self._mr_story_drive(session,room,other,now)
            if room.phase=='closed':
                return dict(room_id=str(room.id),code=None,match_id=str(match_id),state=dict(phase='closed',version=room.state['version']))
            value=self._mr_view(session,room,other)
            # Strip private data on the server; the spectator never receives either hand or choices.
            state=value['state'];state['spectator']=True;state['you']=None;state['legal_moves']=[]
            for player in state['players']:
                player.pop('hand',None);player.pop('selection',None)
            if state['pending']: state['pending']={'actor':state['pending']['actor']}
            state['server_time_ms']=int(now.timestamp()*1000)
            value['code']=None
            return value

    def mistrealm_friend(self,uid,target,operation,now):
        self._mr_rate(uid,'friend',12,now)
        with self._session() as session:
            me,other=self._social_pair(session,uid,target)
            key=pair(me.id,other.id);f=session.get(Friend,key)
            if operation=='request':
                if f and f.status in ('pending','accepted'): return dict(status=f.status)
                if not settings(other)['friend_requests']: fail('玩家暂不接受好友申请',403)
                if f: f.requester_id=me.id;f.status='pending';f.updated_at=now
                else: session.add(Friend(low_id=key[0],high_id=key[1],requester_id=me.id,status='pending',updated_at=now))
                return dict(status='pending')
            if not f or f.status!='pending' or f.requester_id==me.id: fail('没有可处理的好友申请')
            if operation=='accept' and not settings(me)['friend_requests']: fail('请先开启接受好友申请',403)
            f.status='accepted' if operation=='accept' else 'declined';f.updated_at=now
            return dict(status=f.status)

    def mistrealm_invite(self,uid,target,deck_id,now):
        self._mr_rate(uid,'invite',6,now)
        with self._session() as session:
            me,other=self._social_pair(session,uid,target)
            f=session.get(Friend,pair(me.id,other.id))
            reason=challenge_permission(other,bool(f and f.status=='accepted'))
            if reason:fail(reason,403)
            self._social_idle(session,me,now);self._social_idle(session,other,now)
            both=or_(and_(Invite.sender_id==me.id,Invite.receiver_id==other.id),and_(Invite.sender_id==other.id,Invite.receiver_id==me.id))
            existing=session.scalar(select(Invite).where(both,Invite.status=='pending',Invite.expires_at>now))
            if existing: return self._social_invite_view(session,existing,me,now)
            f=session.get(Friend,pair(me.id,other.id))
            if not f or f.status!='accepted':
                if session.scalar(select(Invite.id).where(both,Invite.created_at>=midnight(now)).limit(1)):
                    fail('非好友双方每天只能发起一次挑战，添加好友后可继续约战')
            deck=self._mr_deck_snapshot(session,me,deck_id,3)
            item=Invite(sender_id=me.id,receiver_id=other.id,status='pending',deck_snapshot=deck,created_at=now,expires_at=now+INVITE_TTL)
            session.add(item);session.flush()
            return self._social_invite_view(session,item,me,now)

    def mistrealm_invite_reply(self,uid,invite_id,operation,deck_id,now):
        self._mr_rate(uid,'invite_reply',20,now)
        with self._session() as session:
            item=session.get(Invite,invite_id)
            if not item: fail('挑战不存在',404)
            sender=session.get(Player,item.sender_id);receiver=session.get(Player,item.receiver_id)
            if uid not in (sender.platform_uid,receiver.platform_uid): fail('无权处理此挑战',403)
            me,other=self._social_pair(session,uid,receiver.platform_uid if uid==sender.platform_uid else sender.platform_uid)
            session.refresh(item,with_for_update=True)
            if operation=='cancel' and me.id!=item.sender_id: fail('只有发起者可以取消',403)
            if operation!='cancel' and me.id!=item.receiver_id: fail('只有接收者可以回应',403)
            if item.status=='accepted' and operation=='accept':
                room=session.get(Room,item.room_id)
                return dict(status='accepted',room=self._mr_view(session,room,me))
            if item.status!='pending' or item.expires_at<=now: fail('挑战已处理或过期')
            if operation!='accept':
                item.status='cancelled' if operation=='cancel' else 'declined'
                return dict(status=item.status)
            f=session.get(Friend,pair(me.id,other.id))
            reason=challenge_permission(me,bool(f and f.status=='accepted'))
            if reason:fail(reason,403)
            self._social_idle(session,me,now);self._social_idle(session,other,now)
            if deck_id is None: fail('请先选择出战牌组')
            deck=self._mr_deck_snapshot(session,me,deck_id,3)
            room=self._mr_new_room(session,other,now,item.deck_snapshot)
            from . import mistrealm_v3_state as v3
            state=v3.apply_action(room.state,1,'join',dict(uid=uid,deck=deck),int(now.timestamp()*1000),SystemRandom())
            self._mr_sync(session,room,state)
            session.add(Seat(room_id=room.id,seat_index=1,player_id=me.id))
            item.status='accepted';item.room_id=room.id
            session.flush()
            return dict(status='accepted',room=self._mr_view(session,room,me))

    def _dm_pair(self,session,uid,target):
        me,other=self._social_pair(session,uid,target)
        friend=session.get(Friend,pair(me.id,other.id))
        if not friend or friend.status!='accepted': fail('成为好友后才能私聊',403)
        return me,other

    @staticmethod
    def _dm_between(me,other):
        return or_(and_(DirectMessage.sender_id==me.id,DirectMessage.receiver_id==other.id),
                   and_(DirectMessage.sender_id==other.id,DirectMessage.receiver_id==me.id))

    @staticmethod
    def _dm_view(message,me):
        return dict(id=message.id,text=message.text,outgoing=message.sender_id==me.id,created_at=message.created_at.isoformat())

    def mistrealm_dm_conversations(self,uid,page,now):
        with self._session() as session:
            me=self._mr_player(session,uid)
            other=case((DirectMessage.sender_id==me.id,DirectMessage.receiver_id),else_=DirectMessage.sender_id)
            grouped=select(other.label('other_id'),func.max(DirectMessage.id).label('latest'),
                func.sum(case((and_(DirectMessage.receiver_id==me.id,DirectMessage.read_at.is_(None)),1),else_=0)).label('unread'))\
                .where(or_(DirectMessage.sender_id==me.id,DirectMessage.receiver_id==me.id)).group_by(other).subquery()
            total=session.scalar(select(func.count()).select_from(grouped))
            rows=session.execute(select(Player,DirectMessage,grouped.c.unread).join(grouped,grouped.c.other_id==Player.id)
                .join(DirectMessage,DirectMessage.id==grouped.c.latest).order_by(grouped.c.latest.desc()).offset(page*6).limit(6)).all()
            return dict(total=total,page=page,items=[dict(player=profile(p),online=online(p,now),unread=unread,
                message=self._dm_view(message,me)) for p,message,unread in rows])

    def mistrealm_dm_messages(self,uid,target,before,after,now):
        with self._session() as session:
            me,other=self._dm_pair(session,uid,target)
            query=select(DirectMessage).where(self._dm_between(me,other))
            if before is not None: query=query.where(DirectMessage.id<before)
            if after is not None: query=query.where(DirectMessage.id>after)
            # Catch up forward without skipping messages; history loads backward.
            rows=list(session.scalars(query.order_by(DirectMessage.id.asc() if after is not None else DirectMessage.id.desc()).limit(31)))
            more=len(rows)>30;rows=rows[:30]
            if after is None: rows.reverse()
            return dict(player=profile(other),online=online(other,now),has_more=more,items=[self._dm_view(m,me) for m in rows])

    def mistrealm_dm_send(self,uid,target,text,request_id,now):
        text=text.strip()
        if not text or len(text)>200: fail('请输入1至200字的私聊消息')
        self._mr_rate(uid,'private_message',30,now)
        with self._session() as session:
            me,other=self._dm_pair(session,uid,target)
            existing=session.scalar(select(DirectMessage).where(DirectMessage.sender_id==me.id,DirectMessage.request_id==request_id))
            if existing:
                if existing.receiver_id!=other.id or existing.text!=text: fail('消息请求已用于其他内容')
                return self._dm_view(existing,me)
            message=DirectMessage(sender_id=me.id,receiver_id=other.id,request_id=request_id,text=text,created_at=now)
            session.add(message);session.flush()
            return self._dm_view(message,me)

    def mistrealm_dm_read(self,uid,target,through_id,now):
        with self._session() as session:
            me,other=self._dm_pair(session,uid,target)
            message=session.scalar(select(DirectMessage).where(self._dm_between(me,other),DirectMessage.id==through_id))
            if message is None: fail('消息不存在',404)
            from sqlalchemy import update
            result=session.execute(update(DirectMessage).where(DirectMessage.sender_id==other.id,DirectMessage.receiver_id==me.id,
                DirectMessage.id<=through_id,DirectMessage.read_at.is_(None)).values(read_at=now))
            if result.rowcount:
                from .mistrealm_events import bump
                bump(session, {'messages:'+str(me.id)})
            return dict(ok=True,unread_messages=session.scalar(select(func.count()).select_from(DirectMessage).where(DirectMessage.receiver_id==me.id,DirectMessage.read_at.is_(None))))

    def mistrealm_social_connect(self,uid,now):
        with self._session() as session:
            me=self._mr_player(session,uid)
            me.online_seen_at=now
            return me.id

    def mistrealm_social_touch(self,uid,now):
        with self._session() as session:
            self._mr_player(session,uid).online_seen_at=now
