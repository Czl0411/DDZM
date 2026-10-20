"""Server-owned Elo, ranked match receipts and 28-day season honors."""
from datetime import timedelta
from math import floor
from zoneinfo import ZoneInfo

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from .schema import (
    MistrealmPlayerRecord as Player, MistrealmSeasonRecord as Season,
    MistrealmRatingRecord as Rating, MistrealmRankedMatchRecord as Match,
)

TIERS = (
    ('bronze', '青铜', 0), ('silver', '白银', 1100), ('gold', '黄金', 1250),
    ('platinum', '铂金', 1400), ('diamond', '钻石', 1600), ('crown', '王冠', 1800),
)
SEASON_DAYS = 28


def tier(score):
    index = max(i for i, (_, _, threshold) in enumerate(TIERS) if score >= threshold)
    key, name, threshold = TIERS[index]
    return dict(key=key, name=name, threshold=threshold,
                next=TIERS[index+1][2] if index+1 < len(TIERS) else None)


def elo_delta(a, b, winner, weight=32):
    expected = 1 / (1 + 10 ** (max(-2000, min(2000, b-a)) / 400))
    actual = .5 if winner is None else 1 if winner == 0 else 0
    delta = floor(weight * (actual - expected) + .5)
    return [max(-a, delta), max(-b, -delta)]


def search_radius(seconds):
    return min(400, 100 + max(0, int(seconds)) // 5 * 100)


def season_view(s, now):
    return dict(id=s.id, name=f'S{s.id} · 王冠征途', starts_at=s.starts_at.isoformat(),
                ends_at=s.ends_at.isoformat(), remaining_ms=max(0,int((s.ends_at-now).total_seconds()*1000)),
                status='settled' if s.finalized_at else 'closing' if now >= s.ends_at else 'active')


def rating_view(r, seed=1000):
    value=r.rating if r else seed
    return dict(rating=value, peak=r.peak if r else value, tier=tier(value),
                wins=r.wins if r else 0, losses=r.losses if r else 0, draws=r.draws if r else 0,
                games=r.wins+r.losses+r.draws if r else 0)


class MistrealmRankedMixin:
    @staticmethod
    def _rank_current(session, now):
        while True:
            latest=session.scalar(select(Season).order_by(Season.id.desc()).limit(1))
            if latest and now < latest.ends_at:
                return latest
            start=latest.ends_at if latest else now.astimezone(ZoneInfo('Asia/Shanghai')).replace(hour=0,minute=0,second=0,microsecond=0)
            try:
                with session.begin_nested():
                    session.add(Season(id=latest.id+1 if latest else 1,starts_at=start,ends_at=start+timedelta(days=SEASON_DAYS)))
                    session.flush()
            except IntegrityError:
                # Another worker created the same numbered season.
                pass

    @staticmethod
    def _rank_finalize(session, now, skip_locked=False):
        for s in session.scalars(select(Season).where(Season.ends_at<=now,Season.finalized_at.is_(None))
                                 .order_by(Season.id).with_for_update(skip_locked=skip_locked)):
            if session.scalar(select(Match.match_id).where(Match.season_id==s.id,Match.finished_at.is_(None)).limit(1)):
                continue
            for r in session.scalars(select(Rating).where(Rating.season_id==s.id,
                    Rating.wins+Rating.losses+Rating.draws>0).with_for_update()):
                r.reward_tier=tier(r.peak)['key']
            s.finalized_at=now

    @staticmethod
    def _rank_seed(session, player_id, season_id):
        previous=session.scalar(select(Rating).where(Rating.player_id==player_id,Rating.season_id<season_id,
                Rating.wins+Rating.losses+Rating.draws>0).order_by(Rating.season_id.desc()).limit(1))
        return round(1000+(previous.rating-1000)*(.5**(season_id-previous.season_id))) if previous else 1000

    def _rank_entry(self, session, player, season):
        r=session.get(Rating,(season.id,player.id))
        if r is None:
            seed=self._rank_seed(session,player.id,season.id)
            r=Rating(season_id=season.id,player_id=player.id,rating=seed,peak=seed,wins=0,losses=0,draws=0)
            session.add(r);session.flush()
        return r

    @staticmethod
    def _rank_honor(session, player):
        if not player.ranked_reward_season:
            return None
        r=session.get(Rating,(player.ranked_reward_season,player.id))
        if not r or not r.reward_tier:
            return None
        name=next(name for key,name,_ in TIERS if key==r.reward_tier)
        return dict(season_id=r.season_id, badge=r.reward_tier, title=f'S{r.season_id} · {name}征服者')

    def mistrealm_ranked_profile(self, uid, now):
        with self._session() as session:
            p=self._mr_player(session,uid)
            current=self._rank_current(session,now)
            self._rank_finalize(session,now)
            r=session.get(Rating,(current.id,p.id))
            rewards=[]
            for entry in session.scalars(select(Rating).where(Rating.player_id==p.id,Rating.reward_tier.is_not(None)).order_by(Rating.season_id.desc())):
                name=next(name for key,name,_ in TIERS if key==entry.reward_tier)
                rewards.append(dict(season_id=entry.season_id,badge=entry.reward_tier,title=f'S{entry.season_id} · {name}征服者',
                                    peak=entry.peak,equipped=p.ranked_reward_season==entry.season_id))
            return dict(season=season_view(current,now),player=rating_view(r,self._rank_seed(session,p.id,current.id)),
                        tiers=[dict(key=k,name=n,threshold=v) for k,n,v in TIERS],rewards=rewards,
                        seasons=[season_view(s,now) for s in session.scalars(select(Season).order_by(Season.id.desc()).limit(12))],
                        honor=self._rank_honor(session,p))

    def mistrealm_ranked_equip(self, uid, season_id, now):
        with self._session() as session:
            p=self._mr_player(session,uid)
            self._rank_finalize(session,now)
            if season_id is not None:
                r=session.get(Rating,(season_id,p.id))
                if r is None or r.reward_tier is None:
                    raise ValueError('尚未获得这个赛季的荣誉')
            p.ranked_reward_season=season_id
            return dict(honor=self._rank_honor(session,p))

    def mistrealm_ranked_leaderboard(self, uid, season_id, page, now):
        with self._session() as session:
            p=self._mr_player(session,uid)
            current=self._rank_current(session,now)
            self._rank_finalize(session,now)
            season=session.get(Season,season_id or current.id)
            if season is None:
                raise ValueError('赛季不存在')
            standings=select(Rating.player_id,Rating.rating,Rating.peak,Rating.wins,Rating.losses,Rating.draws,
                func.row_number().over(order_by=(Rating.rating.desc(),Rating.wins.desc(),Rating.played_at,Rating.player_id)).label('position')
            ).where(Rating.season_id==season.id,Rating.wins+Rating.losses+Rating.draws>0).subquery()
            total=session.scalar(select(func.count()).select_from(standings))
            mine=session.scalar(select(standings.c.position).where(standings.c.player_id==p.id))
            items=[]
            for row in session.execute(select(standings,Player.platform_uid,Player.name,Player.avatar)
                    .join(Player,Player.id==standings.c.player_id).order_by(standings.c.position).offset(page*6).limit(6)).mappings():
                items.append(dict(position=row['position'],uid=row['platform_uid'],name=row['name'],avatar=row['avatar'],
                    rating=row['rating'],tier=tier(row['rating']),wins=row['wins'],games=row['wins']+row['losses']+row['draws']))
            return dict(season=season_view(season,now),items=items,total=total,page=page,page_size=6,my_position=mine)

    def _rank_begin(self, session, room, host, guest, now):
        a=host.queue_snapshot['ranked'];b=guest.queue_snapshot['ranked'] if guest else dict(season=a['season'],rating=a['rating'])
        s=session.scalar(select(Season).where(Season.id==a['season']).with_for_update())
        if a['season']!=b['season'] or now>=s.ends_at or s.finalized_at:
            raise ValueError('赛季已切换，请重新匹配')
        session.add(Match(match_id=room.match_id,room_id=room.id,season_id=s.id,
            player_a=host.id,player_b=guest.id if guest else None,rating_a=a['rating'],rating_b=b['rating'],started_at=now))
        session.flush()

    @staticmethod
    def _rank_settle(session, room, now):
        if not room.state.get('ranked_match') or room.phase not in ('finished','closed'):
            return
        m=session.scalar(select(Match).where(Match.match_id==room.match_id).with_for_update())
        if m is None or m.finished_at:
            return
        if room.phase=='closed':
            m.finished_at=now;m.result=dict(void=True,deltas=[0,0]);return
        rows={r.player_id:r for r in session.scalars(select(Rating).where(Rating.season_id==m.season_id,
                Rating.player_id.in_([m.player_a,m.player_b])).order_by(Rating.player_id).with_for_update())}
        players=[rows[m.player_a]]+([rows[m.player_b]] if m.player_b else [])
        changes=elo_delta(m.rating_a,m.rating_b,room.state['winner'],32 if m.player_b else 16)
        if m.player_b is None:changes[1]=0
        before=[m.rating_a,m.rating_b]
        for seat,(p,change) in enumerate(zip(players,changes)):
            p.rating+=change;p.peak=max(p.peak,p.rating);p.played_at=now
            if room.state['winner'] is None:p.draws+=1
            elif room.state['winner']==seat:p.wins+=1
            else:p.losses+=1
        m.finished_at=now
        m.result=dict(void=False,winner=room.state['winner'],before=before,deltas=changes,
                      after=before[:],tiers=[])
        for i,p in enumerate(players):m.result['after'][i]=p.rating
        m.result['tiers']=[tier(score) for score in m.result['after']]

    @staticmethod
    def _rank_room_view(session, room):
        m=session.get(Match,room.match_id)
        return dict(season_id=m.season_id,ratings=[m.rating_a,m.rating_b],
                    tiers=[tier(m.rating_a),tier(m.rating_b)],result=m.result) if m else None
