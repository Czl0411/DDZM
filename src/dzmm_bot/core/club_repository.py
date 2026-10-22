"""Shared Club identity, social features, and one-time task rewards."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select

from .schema import (
    ClubDirectMessageRecord,
    ClubFriendshipRecord,
    ClubPlayerRecord,
    ClubPublicMessageRecord,
    ClubTaskClaimRecord,
    ChessGameRecord,
    DailyCheckinRecord,
    DarkMarketListingRecord,
    DoudizhuRoomRecord,
    DrawguessRoomRecord,
    InboundRecord,
    MahjongRoomRecord,
    RandomEventParticipantRecord,
    UserRecord,
)


TASK_REWARDS = {
    "employment": 20,
    "checkin": 2,
    "random_event": 3,
    "five_rounds": 3,
    "activity": 5,
    "dark_market": 3,
}


class ClubRateLimitError(ValueError):
    pass


class ClubRepositoryMixin:
    @staticmethod
    def _club_platform_id(platform_id: str) -> str:
        if (
            not isinstance(platform_id, str)
            or not platform_id
            or len(platform_id) > 255
            or any(char.isspace() for char in platform_id)
        ):
            raise ValueError("无法读取玩家身份")
        return platform_id

    def _club_player(
        self,
        session,
        platform_id: str,
        now: datetime,
        *,
        display_name: str | None = None,
        avatar_url: str | None = None,
        lock: bool = False,
    ) -> ClubPlayerRecord:
        platform_id = self._club_platform_id(platform_id)
        query = select(ClubPlayerRecord).where(
            ClubPlayerRecord.platform_id == platform_id
        )
        if lock:
            query = query.with_for_update()
        player = session.scalar(query)
        employee = session.scalar(
            select(UserRecord).where(UserRecord.platform_id == platform_id)
        )
        if player is None:
            player = ClubPlayerRecord(
                id=employee.id if employee is not None else uuid4(),
                platform_id=platform_id,
                display_name=(display_name or (employee.display_name if employee else None) or f"玩家{platform_id[:6]}")[:64],
                avatar_url=avatar_url or (employee.profile_image_url if employee else None),
                user_id=employee.id if employee else None,
                created_at=now,
                updated_at=now,
            )
            session.add(player)
            session.flush()
            return player
        changed = False
        if employee is not None and player.user_id != employee.id:
            player.user_id = employee.id
            changed = True
        next_name = display_name or (employee.display_name if employee else None)
        if next_name and player.display_name != next_name[:64]:
            player.display_name = next_name[:64]
            changed = True
        if avatar_url and player.avatar_url != avatar_url:
            player.avatar_url = avatar_url
            changed = True
        if changed:
            player.updated_at = now
        return player

    def ensure_club_player(
        self,
        platform_id: str,
        now: datetime,
        *,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> dict:
        with self.transaction():
            with self._session() as session:
                player = self._club_player(
                    session,
                    platform_id,
                    now,
                    display_name=display_name,
                    avatar_url=avatar_url,
                    lock=True,
                )
                return self._club_player_view(session, player)

    @staticmethod
    def _club_player_view(session, player: ClubPlayerRecord) -> dict:
        employee = session.get(UserRecord, player.user_id) if player.user_id else None
        return {
            "id": str(player.id),
            "uid": player.platform_id,
            "name": player.display_name,
            "avatar_url": player.avatar_url,
            "employee": employee is not None,
            "balance": int(employee.balance) if employee is not None else None,
        }

    def club_profile(self, platform_id: str, now: datetime) -> dict:
        with self.transaction():
            with self._session() as session:
                player = self._club_player(session, platform_id, now)
                return {
                    **self._club_player_view(session, player),
                    "stats": self._club_game_stats(session, player),
                }

    @staticmethod
    def _club_game_stats(session, player: ClubPlayerRecord) -> dict:
        totals = {"played": 0, "wins": 0, "losses": 0, "draws": 0}
        games = {
            key: {"played": 0, "wins": 0, "losses": 0, "draws": 0}
            for key in ("mahjong", "chess", "doudizhu", "drawguess")
        }

        def record(game: str, outcome: str | None) -> None:
            if outcome not in {"win", "loss", "draw"}:
                return
            field = {"win": "wins", "loss": "losses", "draw": "draws"}[outcome]
            games[game]["played"] += 1
            games[game][field] += 1
            totals["played"] += 1
            totals[field] += 1

        for room in session.scalars(
            select(ChessGameRecord).where(
                ChessGameRecord.settled.is_(True),
                or_(
                    ChessGameRecord.red_user_id == player.id,
                    ChessGameRecord.black_user_id == player.id,
                ),
            )
        ):
            side = "red" if room.red_user_id == player.id else "black"
            record("chess", (room.settlement or {}).get("outcomes", {}).get(side))

        raw_id = str(player.id)
        for game, model, seats_getter in (
            ("doudizhu", DoudizhuRoomRecord, lambda room: room.seats),
            ("drawguess", DrawguessRoomRecord, lambda room: (room.state or {}).get("seats", [])),
            ("mahjong", MahjongRoomRecord, lambda room: room.seats),
        ):
            for room in session.scalars(select(model).where(model.settled.is_(True))):
                seats = seats_getter(room)
                if raw_id not in seats:
                    continue
                seat = seats.index(raw_id)
                outcomes = (room.settlement or {}).get("outcomes", [])
                record(game, outcomes[seat] if seat < len(outcomes) else None)

        return {"total": totals, "games": games}

    def club_public_messages(self, platform_id: str, now: datetime) -> list[dict]:
        with self.transaction():
            with self._session() as session:
                self._club_player(session, platform_id, now)
                rows = session.execute(
                    select(ClubPublicMessageRecord, ClubPlayerRecord)
                    .join(ClubPlayerRecord, ClubPlayerRecord.id == ClubPublicMessageRecord.player_id)
                    .order_by(ClubPublicMessageRecord.created_at.desc(), ClubPublicMessageRecord.id.desc())
                    .limit(100)
                ).all()
                return [
                    {
                        "id": str(message.id),
                        "player": self._club_player_view(session, player),
                        "text": message.content,
                        "at": message.created_at.isoformat(),
                    }
                    for message, player in reversed(rows)
                ]

    def send_club_public_message(
        self, platform_id: str, content: str, now: datetime
    ) -> dict:
        content = content.strip()
        if not content:
            raise ValueError("请输入消息")
        with self.transaction():
            with self._session() as session:
                player = self._club_player(session, platform_id, now)
                latest = session.scalar(
                    select(ClubPublicMessageRecord.created_at)
                    .where(ClubPublicMessageRecord.player_id == player.id)
                    .order_by(ClubPublicMessageRecord.created_at.desc())
                    .limit(1)
                )
                if latest and (now - latest).total_seconds() < 2:
                    raise ClubRateLimitError("请间隔两秒再发言")
                message = ClubPublicMessageRecord(
                    player_id=player.id,
                    content=content[:300],
                    created_at=now,
                )
                session.add(message)
                session.flush()
                return {
                    "id": str(message.id),
                    "player": self._club_player_view(session, player),
                    "text": message.content,
                    "at": now.isoformat(),
                }

    @staticmethod
    def _club_friendship(session, left: UUID, right: UUID):
        return session.scalar(
            select(ClubFriendshipRecord).where(
                or_(
                    and_(
                        ClubFriendshipRecord.requester_id == left,
                        ClubFriendshipRecord.recipient_id == right,
                    ),
                    and_(
                        ClubFriendshipRecord.requester_id == right,
                        ClubFriendshipRecord.recipient_id == left,
                    ),
                )
            )
        )

    def club_friends(self, platform_id: str, now: datetime) -> dict:
        with self.transaction():
            with self._session() as session:
                player = self._club_player(session, platform_id, now)
                rows = session.scalars(
                    select(ClubFriendshipRecord).where(
                        or_(
                            ClubFriendshipRecord.requester_id == player.id,
                            ClubFriendshipRecord.recipient_id == player.id,
                        )
                    ).order_by(ClubFriendshipRecord.updated_at.desc())
                ).all()
                result = {"friends": [], "incoming": [], "outgoing": []}
                for row in rows:
                    other_id = row.recipient_id if row.requester_id == player.id else row.requester_id
                    other = session.get(ClubPlayerRecord, other_id)
                    if other is None:
                        continue
                    view = self._club_player_view(session, other)
                    if row.status == "accepted":
                        result["friends"].append(view)
                    elif row.recipient_id == player.id:
                        result["incoming"].append({**view, "request_id": str(row.id)})
                    else:
                        result["outgoing"].append(view)
                return result

    def request_club_friend(
        self, platform_id: str, target_player_id: UUID, now: datetime
    ) -> dict:
        with self.transaction():
            with self._session() as session:
                player = self._club_player(session, platform_id, now)
                target = session.get(ClubPlayerRecord, target_player_id)
                if target is None:
                    raise ValueError("玩家不存在")
                if target.id == player.id:
                    raise ValueError("不能添加自己")
                existing = self._club_friendship(session, player.id, target.id)
                if existing is None:
                    existing = ClubFriendshipRecord(
                        requester_id=player.id,
                        recipient_id=target.id,
                        status="pending",
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(existing)
                elif existing.status == "accepted":
                    return self._club_player_view(session, target)
                elif existing.recipient_id == player.id:
                    existing.status = "accepted"
                    existing.updated_at = now
                session.flush()
                return self._club_player_view(session, target)

    def accept_club_friend(
        self, platform_id: str, request_id: UUID, now: datetime
    ) -> dict:
        with self.transaction():
            with self._session() as session:
                player = self._club_player(session, platform_id, now)
                request = session.scalar(
                    select(ClubFriendshipRecord).where(
                        ClubFriendshipRecord.id == request_id,
                        ClubFriendshipRecord.recipient_id == player.id,
                        ClubFriendshipRecord.status == "pending",
                    ).with_for_update()
                )
                if request is None:
                    raise ValueError("好友申请不存在")
                request.status = "accepted"
                request.updated_at = now
                other = session.get(ClubPlayerRecord, request.requester_id)
                return self._club_player_view(session, other)

    def club_direct_messages(
        self, platform_id: str, target_player_id: UUID, now: datetime
    ) -> list[dict]:
        with self.transaction():
            with self._session() as session:
                player = self._club_player(session, platform_id, now)
                friendship = self._club_friendship(session, player.id, target_player_id)
                if friendship is None or friendship.status != "accepted":
                    raise ValueError("仅好友可以私聊")
                rows = session.scalars(
                    select(ClubDirectMessageRecord)
                    .where(
                        or_(
                            and_(
                                ClubDirectMessageRecord.sender_id == player.id,
                                ClubDirectMessageRecord.recipient_id == target_player_id,
                            ),
                            and_(
                                ClubDirectMessageRecord.sender_id == target_player_id,
                                ClubDirectMessageRecord.recipient_id == player.id,
                            ),
                        )
                    )
                    .order_by(ClubDirectMessageRecord.created_at.desc())
                    .limit(100)
                ).all()
                return [
                    {
                        "id": str(message.id),
                        "mine": message.sender_id == player.id,
                        "text": message.content,
                        "at": message.created_at.isoformat(),
                    }
                    for message in reversed(rows)
                ]

    def send_club_direct_message(
        self,
        platform_id: str,
        target_player_id: UUID,
        content: str,
        now: datetime,
    ) -> dict:
        content = content.strip()
        if not content:
            raise ValueError("请输入消息")
        with self.transaction():
            with self._session() as session:
                player = self._club_player(session, platform_id, now)
                friendship = self._club_friendship(session, player.id, target_player_id)
                if friendship is None or friendship.status != "accepted":
                    raise ValueError("仅好友可以私聊")
                latest = session.scalar(
                    select(ClubDirectMessageRecord.created_at)
                    .where(ClubDirectMessageRecord.sender_id == player.id)
                    .order_by(ClubDirectMessageRecord.created_at.desc())
                    .limit(1)
                )
                if latest and (now - latest).total_seconds() < 2:
                    raise ClubRateLimitError("请间隔两秒再发言")
                message = ClubDirectMessageRecord(
                    sender_id=player.id,
                    recipient_id=target_player_id,
                    content=content[:300],
                    created_at=now,
                )
                session.add(message)
                session.flush()
                return {
                    "id": str(message.id),
                    "mine": True,
                    "text": message.content,
                    "at": now.isoformat(),
                }

    @staticmethod
    def _club_five_rounds(session, player: ClubPlayerRecord) -> bool:
        raw_id = str(player.id)
        for room in session.scalars(
            select(DoudizhuRoomRecord).where(DoudizhuRoomRecord.round_number >= 5)
        ):
            if raw_id in room.seats:
                return True
        for room in session.scalars(select(DrawguessRoomRecord)):
            state = room.state or {}
            if raw_id in state.get("seats", []) and int(state.get("turn_index", 0)) >= 5:
                return True
        for room in session.scalars(select(MahjongRoomRecord)):
            state = room.state or {}
            completed_hands = max(0, int(state.get("round_wind", 27)) - 27) * 4
            completed_hands += max(0, int(state.get("hand_number", 1)) - 1)
            if raw_id in room.seats and completed_hands >= 5:
                return True
        return False

    def _club_task_eligibility(self, session, player: ClubPlayerRecord) -> dict[str, bool]:
        if player.user_id is None:
            return {key: False for key in TASK_REWARDS}
        user_id = player.user_id
        activity = session.execute(
            select(func.count(InboundRecord.id), func.coalesce(func.sum(func.length(InboundRecord.content)), 0)).where(
                InboundRecord.sender_platform_id == player.platform_id,
                InboundRecord.source_type == "group",
                InboundRecord.content_type == "text",
            )
        ).one()
        return {
            "employment": True,
            "checkin": session.scalar(
                select(DailyCheckinRecord.id).where(DailyCheckinRecord.user_id == user_id).limit(1)
            ) is not None,
            "random_event": session.scalar(
                select(RandomEventParticipantRecord.id).where(
                    RandomEventParticipantRecord.user_id == user_id,
                    RandomEventParticipantRecord.rounds > 0,
                ).limit(1)
            ) is not None,
            "five_rounds": self._club_five_rounds(session, player),
            "activity": int(activity[0]) >= 20 and int(activity[1]) > 300,
            "dark_market": session.scalar(
                select(DarkMarketListingRecord.id).where(
                    DarkMarketListingRecord.seller_user_id == user_id
                ).limit(1)
            ) is not None,
        }

    def club_tasks(self, platform_id: str, now: datetime) -> list[dict]:
        with self.transaction():
            with self._session() as session:
                player = self._club_player(session, platform_id, now)
                eligibility = self._club_task_eligibility(session, player)
                claimed = set()
                if player.user_id:
                    claimed = set(session.scalars(
                        select(ClubTaskClaimRecord.task_key).where(
                            ClubTaskClaimRecord.user_id == player.user_id
                        )
                    ))
                return [
                    {
                        "key": key,
                        "reward": reward,
                        "eligible": eligibility[key],
                        "claimed": key in claimed,
                        "hidden": key == "activity",
                    }
                    for key, reward in TASK_REWARDS.items()
                ]

    def claim_club_task(self, platform_id: str, task_key: str, now: datetime) -> dict:
        if task_key not in TASK_REWARDS:
            raise ValueError("任务不存在")
        with self.transaction():
            with self._session() as session:
                player = self._club_player(session, platform_id, now, lock=True)
                if player.user_id is None:
                    raise ValueError("领取任务奖励需要先入职")
                user = session.get(UserRecord, player.user_id, with_for_update=True)
                existing = session.scalar(
                    select(ClubTaskClaimRecord).where(
                        ClubTaskClaimRecord.user_id == user.id,
                        ClubTaskClaimRecord.task_key == task_key,
                    )
                )
                if existing is not None:
                    raise ValueError("奖励已经领取")
                if not self._club_task_eligibility(session, player)[task_key]:
                    raise ValueError("任务尚未完成")
                reward = TASK_REWARDS[task_key]
                self._apply_balance_change(
                    user,
                    reward,
                    "club_task_reward",
                    now,
                    memo=f"Club 一次性任务：{task_key}",
                )
                session.add(ClubTaskClaimRecord(
                    user_id=user.id,
                    task_key=task_key,
                    reward=reward,
                    claimed_at=now,
                ))
                session.flush()
                return {"task_key": task_key, "reward": reward, "balance": user.balance}
