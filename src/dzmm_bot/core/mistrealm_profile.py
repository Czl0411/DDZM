"""Player preferences and durable, private whole-match history."""
from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import select, func, or_

from .schema import (MistrealmPlayerRecord as Player, MistrealmRoomRecord as Room,
                     MistrealmHistoryRecord as History, MistrealmRatingRecord as Rating)
from .mistrealm_ranked import rating_view, season_view

DEFAULT_SETTINGS = dict(challenges='all', friend_requests=True, spectate=True, animations=True, sound=False)


def settings(player):
    return {**DEFAULT_SETTINGS, **(player.preferences or {})}


def challenge_permission(player, is_friend):
    mode=settings(player)['challenges']
    return '暂不接受挑战' if mode=='off' else '仅接受好友挑战' if mode=='friends' and not is_friend else ''


class MistrealmProfileMixin:
    def mistrealm_profile(self, uid, target, now):
        with self._session() as session:
            me=self._mr_player(session,uid)
            p=me if not target or target==uid else session.scalar(select(Player).where(Player.platform_uid==target))
            if p is None:
                from .mistrealm_social import fail
                fail('玩家不存在',404)
            current=self._rank_current(session,now)
            rank=session.get(Rating,(current.id,p.id))
            result=dict(uid=p.platform_uid,name=p.name,avatar=p.avatar,self=p.id==me.id,
                        rank=rating_view(rank,self._rank_seed(session,p.id,current.id)),
                        season=season_view(current,now),honor=self._rank_honor(session,p))
            if p.id==me.id:result['settings']=settings(p)
            else:result['interaction']=self._social_player_view(session,me,p,now)
            return result

    def mistrealm_preferences(self,uid,values,now):
        self._mr_rate(uid,'preferences',30,now)
        with self._session() as session:
            p=self._mr_player(session,uid)
            p.preferences={**settings(p),**values};p.updated_at=now
            return dict(settings=settings(p))

    def _mr_record_history(self,session,room,now):
        s=room.state
        if s.get('rules_version')!=3 or s.get('balance_revision')!=2 or s['phase']!='finished' or not room.match_id:return
        players=[session.scalar(select(Player).where(Player.platform_uid==p['uid'])) for p in s['players']]
        profiles=[]
        for i,p in enumerate(s['players']):
            stored=players[i]
            value=dict(uid=p['uid'],name=stored.name if stored else '旅人',avatar=stored.avatar if stored else None,
                       faction=p['selection']['faction'],leader=p['selection']['leader'])
            if i==1 and s.get('mode')=='bot':value.update({k:s['bot'].get(k) for k in ('name','avatar')})
            if i==1 and s.get('mode')=='story':value.update(name=s['story']['enemy_name'],avatar=None)
            profiles.append(value)
        ranked=self._rank_room_view(session,room) if s.get('ranked_match') else None
        summary=dict(mode='ranked' if ranked else 'story' if s.get('mode')=='story' else 'casual',players=profiles,
                     winner=s['winner'],rounds=deepcopy(s.get('history',[])),lives=s['lives'][:],ranked=ranked,
                     conceded=any(e['kind']=='concede' for e in s.get('action_log',[])))
        for seat,p in enumerate(players):
            if not p or (seat==1 and s.get('mode') in ('bot','story')):continue
            if session.get(History,(room.match_id,p.id)):continue
            session.add(History(match_id=room.match_id,player_id=p.id,finished_at=now,seat=seat,
                                summary=deepcopy(summary),actions=deepcopy(s.get('action_log',[]))))
        session.flush()

    def mistrealm_history(self,uid,page,now):
        with self._session() as session:
            p=self._mr_player(session,uid)
            # Recover retained finished rooms from before the feature; rematches cannot be reconstructed.
            rooms=session.scalars(select(Room).where(Room.phase=='finished',~select(History.match_id).where(History.match_id==Room.match_id,History.player_id==p.id).exists(),or_(
                Room.state['players'][0]['uid'].as_string()==uid,Room.state['players'][1]['uid'].as_string()==uid))
                .order_by(Room.id).with_for_update())
            for room in rooms:
                if room.state.get('rules_version')==3:
                    self._mr_record_history(session,room,datetime.fromtimestamp(room.state['server_time_ms']/1000,timezone.utc))
            query=select(History).where(History.player_id==p.id)
            total=session.scalar(select(func.count()).select_from(query.subquery()))
            items=session.scalars(query.order_by(History.finished_at.desc(),History.match_id).offset(page*5).limit(5))
            return dict(total=total,page=page,items=[dict(match_id=str(h.match_id),finished_at=h.finished_at.isoformat(),seat=h.seat,**h.summary) for h in items])

    def mistrealm_history_detail(self,uid,match_id):
        with self._session() as session:
            p=self._mr_player(session,uid);h=session.get(History,(match_id,p.id))
            if h is None:
                from .mistrealm_social import fail
                fail('对局记录不存在',404)
            return dict(match_id=str(h.match_id),finished_at=h.finished_at.isoformat(),seat=h.seat,**h.summary,actions=h.actions)
