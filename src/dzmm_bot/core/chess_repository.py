from dataclasses import dataclass
from datetime import datetime, timedelta
from secrets import randbelow
from uuid import UUID

from sqlalchemy import delete, select, update

from .chess_rules import (
    ChessMove, ChessPosition, ChessViolation, IllegalChessMove, adjudicate_repetition,
    basic_outcome, initial_position, play_move,
)
from .schema import ChessGameRecord, ChessMessageRecord, ChessMoveRecord, GroupChatRecord, InboundRecord, OutboundRecord, UserRecord


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


class ChessRateLimitError(ValueError):
    pass


class ChessRepositoryMixin:
    def chess_inbound_id(self, group_chat_id: UUID, platform_message_id: str) -> UUID | None:
        with self._session() as session:
            return session.scalar(select(InboundRecord.id).where(
                InboundRecord.group_chat_id == group_chat_id,
                InboundRecord.platform_message_id == platform_message_id,
                InboundRecord.source_type == "group",
            ))

    @staticmethod
    def _position_data(position: ChessPosition) -> dict:
        return {"board": list(position.board), "turn": position.turn}

    @staticmethod
    def _position(value: dict) -> ChessPosition:
        return ChessPosition(tuple(value["board"]), value["turn"])

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
            if group is None or not group.listening_enabled or inbound is None or inbound.group_chat_id != group_chat_id or inbound.sender_platform_id != creator_platform_id:
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
                "position": self._position_data(initial_position()),
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

    @staticmethod
    def _chess_notice(session, row: ChessGameRecord, text: str) -> None:
        group = session.get(GroupChatRecord, row.group_chat_id)
        if group is None or group.chatroom_id is None:
            return
        session.add(OutboundRecord(
            group_chat_id=row.group_chat_id, destination_chatroom_id=group.chatroom_id,
            delivery_key=group.chatroom_id, delivery_kind="group", text=text,
        ))

    def _finish_chess(self, session, row: ChessGameRecord, result: str, now: datetime) -> None:
        if row.status != "playing":
            return
        row.status = "finished"
        row.result = result
        row.finished_at = now
        row.turn_started_at = None
        row.pending_offer = None
        row.offer_user_id = None
        row.version += 1
        session.execute(delete(ChessMessageRecord).where(ChessMessageRecord.game_id == row.id))
        self._chess_notice(session, row, f"象棋对局已结束：{result}。对局编号 {row.id}")

    @staticmethod
    def _elapsed_ms(row: ChessGameRecord, now: datetime) -> int:
        return max(0, int((now - row.turn_started_at).total_seconds() * 1000))

    def _timeout_chess(self, session, row: ChessGameRecord, now: datetime) -> bool:
        if row.status != "playing" or row.turn_started_at is None:
            return False
        color = row.position["turn"]
        remaining = row.red_remaining_ms if color == "red" else row.black_remaining_ms
        elapsed = self._elapsed_ms(row, now)
        if elapsed < min(remaining, 60000):
            return False
        winner = "black" if color == "red" else "red"
        reason = "total_timeout" if remaining <= 60000 else "step_timeout"
        self._finish_chess(session, row, f"{winner}:{reason}", now)
        return True

    def play_chess(
        self, game_id: UUID, platform_id: str, from_xy: tuple[int, int],
        to_xy: tuple[int, int], expected_version: int, now: datetime,
    ) -> ChessGameView:
        with self._session() as session:
            row = session.scalar(select(ChessGameRecord).where(ChessGameRecord.id == game_id).with_for_update())
            if row is None or row.status != "playing":
                raise ValueError("棋局未在进行")
            if self._timeout_chess(session, row, now):
                return self._chess_view(session, row)
            if row.version != expected_version:
                raise ValueError("棋局版本已变化")
            position = self._position(row.position)
            user = session.scalar(select(UserRecord).where(UserRecord.platform_id == platform_id))
            current_user_id = row.red_user_id if position.turn == "red" else row.black_user_id
            if user is None or user.id != current_user_id:
                raise ValueError("现在不是你的回合")
            move = ChessMove(*from_xy, *to_xy)
            next_position = play_move(position, move)
            records = session.scalars(select(ChessMoveRecord).where(ChessMoveRecord.game_id == game_id).order_by(ChessMoveRecord.ply)).all()
            history = tuple(self._position(record.position_before) for record in records) + (position, next_position)
            moves = tuple(ChessMove(record.from_x, record.from_y, record.to_x, record.to_y) for record in records) + (move,)
            violation = adjudicate_repetition(history, moves)
            if isinstance(violation, ChessViolation) and violation.reason != "long_check" and violation.side == position.turn:
                raise IllegalChessMove("长将／长捉须变着")
            elapsed = self._elapsed_ms(row, now)
            if position.turn == "red":
                row.red_remaining_ms -= elapsed
            else:
                row.black_remaining_ms -= elapsed
            row.position = self._position_data(next_position)
            row.turn_started_at = now
            row.version += 1
            row.pending_offer = None
            row.offer_user_id = None
            session.add(ChessMoveRecord(
                game_id=game_id, ply=len(records) + 1,
                from_x=move.from_x, from_y=move.from_y, to_x=move.to_x, to_y=move.to_y,
                position_before=self._position_data(position), created_at=now,
            ))
            outcome = basic_outcome(next_position)
            if isinstance(violation, ChessViolation) and violation.reason == "long_check":
                winner = "black" if violation.side == "red" else "red"
                self._finish_chess(session, row, f"{winner}:long_check", now)
            elif outcome is not None:
                self._finish_chess(session, row, f"{outcome.winner}:{outcome.reason}", now)
            return self._chess_view(session, row)

    def chess_action(self, game_id: UUID, platform_id: str, action: str, now: datetime) -> ChessGameView:
        valid = {"offer_undo", "accept_undo", "decline_undo", "offer_draw", "accept_draw", "decline_draw", "resign"}
        if action not in valid:
            raise ValueError("未知的象棋操作")
        with self._session() as session:
            row = session.scalar(select(ChessGameRecord).where(ChessGameRecord.id == game_id).with_for_update())
            if row is None or row.status != "playing":
                raise ValueError("棋局未在进行")
            if self._timeout_chess(session, row, now):
                return self._chess_view(session, row)
            user = session.scalar(select(UserRecord).where(UserRecord.platform_id == platform_id))
            if user is None or user.id not in {row.red_user_id, row.black_user_id}:
                raise ValueError("只有棋手能执行此操作")
            color = "red" if user.id == row.red_user_id else "black"
            if action == "resign":
                self._finish_chess(session, row, f"{'black' if color == 'red' else 'red'}:resign", now)
            elif action.startswith("offer_"):
                if row.pending_offer is not None:
                    raise ValueError("已有待处理请求")
                if action == "offer_undo" and session.scalar(select(ChessMoveRecord.id).where(ChessMoveRecord.game_id == game_id).limit(1)) is None:
                    raise ValueError("还没有可悔的棋")
                row.pending_offer = action.removeprefix("offer_")
                row.offer_user_id = user.id
                row.version += 1
            else:
                kind = action.split("_", 1)[1]
                if row.pending_offer != kind or row.offer_user_id == user.id:
                    raise ValueError("没有对手的待处理请求")
                if action.startswith("decline_"):
                    row.pending_offer = None
                    row.offer_user_id = None
                    row.version += 1
                elif kind == "draw":
                    self._finish_chess(session, row, "draw:agreement", now)
                else:
                    last = session.scalar(select(ChessMoveRecord).where(ChessMoveRecord.game_id == game_id).order_by(ChessMoveRecord.ply.desc()).limit(1))
                    if last is None:
                        raise ValueError("还没有可悔的棋")
                    elapsed = self._elapsed_ms(row, now)
                    if row.position["turn"] == "red":
                        row.red_remaining_ms -= elapsed
                    else:
                        row.black_remaining_ms -= elapsed
                    row.position = last.position_before
                    row.turn_started_at = now
                    row.pending_offer = None
                    row.offer_user_id = None
                    row.version += 1
                    session.delete(last)
            return self._chess_view(session, row)

    def advance_chess_deadlines(self, now: datetime) -> int:
        count = 0
        with self._session() as session:
            rows = session.scalars(
                select(ChessGameRecord).where(ChessGameRecord.status.in_(("waiting", "playing"))).with_for_update()
            ).all()
            for row in rows:
                if row.status == "waiting" and now >= row.claim_deadline:
                    row.status = "cancelled"
                    row.version += 1
                    sent = session.scalar(select(OutboundRecord.id).where(
                        OutboundRecord.inbound_message_id == row.inbound_message_id,
                        OutboundRecord.status == "sent",
                    ).limit(1))
                    if sent is not None:
                        self._chess_notice(session, row, f"象棋对局 {row.id} 等候超时，已取消。")
                    count += 1
                elif self._timeout_chess(session, row, now):
                    count += 1
        return count

    def chess_messages(self, game_id: UUID) -> list[dict]:
        with self._session() as session:
            row = session.get(ChessGameRecord, game_id)
            if row is None or row.status == "finished":
                return []
            records = session.scalars(
                select(ChessMessageRecord)
                .where(ChessMessageRecord.game_id == game_id)
                .order_by(ChessMessageRecord.created_at, ChessMessageRecord.id)
            ).all()
            return [
                {"id": str(item.id), "sender": session.get(UserRecord, item.user_id).display_name,
                 "text": item.content, "created_at": item.created_at.isoformat()}
                for item in records
            ]

    def chess_moves(self, game_id: UUID) -> list[dict]:
        with self._session() as session:
            records = session.scalars(
                select(ChessMoveRecord)
                .where(ChessMoveRecord.game_id == game_id)
                .order_by(ChessMoveRecord.ply)
            ).all()
            return [
                {"ply": item.ply, "from_xy": [item.from_x, item.from_y],
                 "to_xy": [item.to_x, item.to_y]}
                for item in records
            ]

    def chess_chat(self, game_id: UUID, platform_id: str, text: str, now: datetime) -> dict:
        content = text.strip()
        if not content or len(content) > 300 or any(ord(char) < 32 and char not in "\n\t" for char in content):
            raise ValueError("聊天内容须为 1～300 字纯文字")
        with self._session() as session:
            game = session.scalar(select(ChessGameRecord).where(ChessGameRecord.id == game_id).with_for_update())
            user = session.scalar(select(UserRecord).where(UserRecord.platform_id == platform_id))
            if game is None or user is None or game.status != "playing":
                raise ValueError("当前不可发送聊天")
            last = session.scalar(
                select(ChessMessageRecord.created_at)
                .where(ChessMessageRecord.game_id == game_id, ChessMessageRecord.user_id == user.id)
                .order_by(ChessMessageRecord.created_at.desc()).limit(1)
            )
            if last is not None and (now - last).total_seconds() < 2:
                raise ChessRateLimitError("请稍后再发")
            message = ChessMessageRecord(game_id=game_id, user_id=user.id, content=content, created_at=now)
            session.add(message)
            session.flush()
            return {"id": str(message.id), "sender": user.display_name, "text": content, "created_at": now.isoformat()}
