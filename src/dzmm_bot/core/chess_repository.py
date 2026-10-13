from dataclasses import dataclass
from datetime import datetime, timedelta
from secrets import randbelow
from uuid import UUID

from sqlalchemy import select, update

from .schema import ChessGameRecord, GroupChatRecord, InboundRecord, OutboundRecord, UserRecord


@dataclass(frozen=True)
class ChessGameView:
    id: UUID
    group_chat_id: UUID
    inbound_message_id: UUID
    creator_platform_id: str
    opponent_platform_id: str | None
    red_platform_id: str | None
    black_platform_id: str | None
    code: str
    status: str
    created_at: datetime
    claim_deadline: datetime
    position: dict | None
    red_remaining_ms: int
    black_remaining_ms: int
    turn_started_at: datetime | None
    version: int
    result: str | None
    pending_offer: str | None
    offer_platform_id: str | None
    finished_at: datetime | None


@dataclass(frozen=True)
class ChessClaimResult:
    status: str
    game: ChessGameView | None = None


class ChessRepositoryMixin:
    def _chess_view(self, session, row: ChessGameRecord) -> ChessGameView:
        def pid(user_id):
            return session.get(UserRecord, user_id).platform_id if user_id else None

        return ChessGameView(
            id=row.id, group_chat_id=row.group_chat_id, inbound_message_id=row.inbound_message_id,
            creator_platform_id=pid(row.creator_user_id), opponent_platform_id=pid(row.opponent_user_id),
            red_platform_id=pid(row.red_user_id), black_platform_id=pid(row.black_user_id),
            code=row.code, status=row.status, created_at=row.created_at, claim_deadline=row.claim_deadline,
            position=row.position, red_remaining_ms=row.red_remaining_ms,
            black_remaining_ms=row.black_remaining_ms, turn_started_at=row.turn_started_at,
            version=row.version, result=row.result, pending_offer=row.pending_offer,
            offer_platform_id=pid(row.offer_user_id), finished_at=row.finished_at,
        )

    def create_chess_game(
        self, creator_platform_id: str, group_chat_id: UUID, inbound_id: UUID, now: datetime
    ) -> ChessGameView:
        with self._session() as session:
            creator = session.scalar(select(UserRecord).where(UserRecord.platform_id == creator_platform_id))
            group = session.get(GroupChatRecord, group_chat_id)
            inbound = session.get(InboundRecord, inbound_id)
            if creator is None:
                raise ValueError("只有已入职用户可以发起象棋")
            if group is None or not group.listening_enabled or inbound is None or inbound.group_chat_id != group_chat_id:
                raise ValueError("群聊或入站消息不可用")
            row = ChessGameRecord(
                group_chat_id=group_chat_id, inbound_message_id=inbound_id,
                creator_user_id=creator.id, code=f"{randbelow(10000):04d}",
                status="waiting", created_at=now, claim_deadline=now + timedelta(minutes=10),
                red_remaining_ms=900000, black_remaining_ms=900000, version=0,
            )
            session.add(row)
            session.flush()
            return self._chess_view(session, row)

    def get_chess_game(self, game_id: UUID) -> ChessGameView:
        with self._session() as session:
            row = session.get(ChessGameRecord, game_id)
            if row is None:
                raise ValueError("棋局不存在")
            return self._chess_view(session, row)

    def claim_chess_seat(
        self, game_id: UUID, platform_id: str, code: str, now: datetime
    ) -> ChessClaimResult:
        with self._session() as session:
            row = session.get(ChessGameRecord, game_id)
            if row is None:
                return ChessClaimResult("not_found")
            user = session.scalar(select(UserRecord).where(UserRecord.platform_id == platform_id))
            if user is None:
                return ChessClaimResult("not_joined")
            if row.status != "waiting":
                return ChessClaimResult("occupied", self._chess_view(session, row))
            if user.id == row.creator_user_id:
                return ChessClaimResult("same_player")
            if now >= row.claim_deadline:
                return ChessClaimResult("expired")
            if code != row.code:
                return ChessClaimResult("invalid_code")
            sent = session.scalar(
                select(OutboundRecord.id).where(
                    OutboundRecord.inbound_message_id == row.inbound_message_id,
                    OutboundRecord.group_chat_id == row.group_chat_id,
                    OutboundRecord.status == "sent",
                ).limit(1)
            )
            if sent is None:
                return ChessClaimResult("not_announced")
            creator_red = randbelow(2) == 0
            values = {
                "opponent_user_id": user.id,
                "red_user_id": row.creator_user_id if creator_red else user.id,
                "black_user_id": user.id if creator_red else row.creator_user_id,
                "status": "playing", "turn_started_at": now, "version": 1,
                "code": "",  # Used code is never usable again.
            }
            result = session.execute(
                update(ChessGameRecord)
                .where(ChessGameRecord.id == game_id, ChessGameRecord.status == "waiting")
                .values(**values)
            )
            session.flush()
            session.expire_all()
            row = session.get(ChessGameRecord, game_id)
            return ChessClaimResult("claimed" if result.rowcount == 1 else "occupied", self._chess_view(session, row))
