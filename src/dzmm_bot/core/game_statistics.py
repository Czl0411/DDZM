from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .schema import (
    BlameGamePlayerRecord, BlameGameRecord, GameParticipationRecord,
    HideAndSeekGameRecord, KingGameRecord, KingGameRoundRecord,
    LiarDiceGameRecord, LiarDicePlayerRecord, LiarDiceRoundRecord, MemoryAssessmentGameRecord,
    MemoryAssessmentParticipantRecord, MemoryAssessmentRoundRecord, MemoryGuildMatchRecord, MemoryGuildMemberRecord,
    MemoryGuildSeriesRecord, MemoryGuildRoundRecord, NeverHaveIEverRoundRecord,
    NeverHaveIEverResponseRecord, NeverHaveIEverGameRecord, NumberBombGameRecord,
    NumberBombRoundPlayerRecord, NumberBombRoundRecord, TexasHoldemGameRecord,
    TexasHoldemPlayerRecord, TruthTradeGameRecord, TruthTradePlayerRecord, TruthTradeQuestionRecord,
    UndercoverGamePlayerRecord, UndercoverGameRecord, UndercoverSessionRecord,
)


def record_game_participations(
    session: Session, game_type: str, game_id: UUID, group_chat_id: UUID,
    user_ids: Sequence[UUID], completed_at: datetime,
) -> list[UUID]:
    dialect = session.get_bind().dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise ValueError(f"unsupported database dialect: {dialect}")
    insert = postgres_insert if dialect == "postgresql" else sqlite_insert
    added = []
    for user_id in dict.fromkeys(user_ids):
        inserted = session.scalar(insert(GameParticipationRecord).values(
            game_type=game_type, game_id=game_id, group_chat_id=group_chat_id,
            user_id=user_id, completed_at=completed_at,
        ).on_conflict_do_nothing(index_elements=["game_type", "game_id", "user_id"]).returning(
            GameParticipationRecord.user_id,
        ))
        if inserted is not None:
            added.append(inserted)
    return added


def resolved_game_users(session: Session, game_type: str, game_id: UUID) -> list[UUID]:
    if game_type == "king_game":
        snapshots = session.scalars(select(KingGameRoundRecord.number_map).where(
            KingGameRoundRecord.game_id == game_id, KingGameRoundRecord.state == "revealed",
            KingGameRoundRecord.revealed_at.is_not(None),
        ))
    elif game_type == "liar_dice":
        rounds = list(session.scalars(select(LiarDiceRoundRecord).where(
            LiarDiceRoundRecord.game_id == game_id, LiarDiceRoundRecord.state == "resolved",
            LiarDiceRoundRecord.resolved_at.is_not(None),
        )))
        users = set()
        for round_record in rounds:
            try:
                users.update(UUID(value) for value in round_record.dice_snapshot or {})
            except ValueError:
                users.update(session.scalars(select(LiarDicePlayerRecord.user_id).where(
                    LiarDicePlayerRecord.game_id == game_id,
                    or_(LiarDicePlayerRecord.seat_number.is_not(None), LiarDicePlayerRecord.dice.is_not(None)),
                    LiarDicePlayerRecord.joined_at <= round_record.started_at,
                    or_(LiarDicePlayerRecord.left_at.is_(None),
                        LiarDicePlayerRecord.left_at > round_record.started_at),
                )))
        return sorted(users, key=str)
    else:
        raise ValueError("unsupported round game")
    users = set()
    for snapshot in snapshots:
        for user_id in snapshot or {}:
            users.add(UUID(user_id))
    return sorted(users, key=str)


def truth_trade_game_users(session: Session, game: TruthTradeGameRecord) -> list[UUID]:
    if game.started_at is None or game.settled_rounds < 1:
        return []
    players = list(session.scalars(select(TruthTradePlayerRecord).where(
        TruthTradePlayerRecord.game_id == game.id,
        TruthTradePlayerRecord.joined_at <= game.started_at,
        or_(TruthTradePlayerRecord.withdrawn_at.is_(None),
            TruthTradePlayerRecord.withdrawn_at > game.started_at),
    )))
    rounds = {}
    for question in session.scalars(select(TruthTradeQuestionRecord).where(
        TruthTradeQuestionRecord.game_id == game.id,
        TruthTradeQuestionRecord.round_number <= game.settled_rounds,
    )):
        rounds.setdefault(question.round_number, []).append(question)
    for questions in rounds.values():
        if any(question.collected_at is None for question in questions):
            continue
        completed_at = max(question.collected_at for question in questions)
        positions = {question.position for question in questions}
        if all(player.position in positions or (
            player.withdrawn_at is not None and player.withdrawn_at <= completed_at
        ) for player in players):
            return [player.user_id for player in players]
    return []


def other_game_users(session: Session, game_type: str, game_id: UUID) -> list[UUID]:
    if game_type == "number_bomb":
        query = select(NumberBombRoundPlayerRecord.user_id).join(
            NumberBombRoundRecord, NumberBombRoundPlayerRecord.round_id == NumberBombRoundRecord.id,
        ).where(NumberBombRoundRecord.game_id == game_id, NumberBombRoundRecord.state == "settled",
                NumberBombRoundPlayerRecord.submitted_number.is_not(None))
    elif game_type == "never_have_i_ever":
        users = set(session.scalars(select(NeverHaveIEverRoundRecord.speaker_user_id).where(
            NeverHaveIEverRoundRecord.game_id == game_id, NeverHaveIEverRoundRecord.state == "settled",
        )))
        users.update(session.scalars(select(NeverHaveIEverResponseRecord.user_id).join(
            NeverHaveIEverRoundRecord, NeverHaveIEverResponseRecord.round_id == NeverHaveIEverRoundRecord.id,
        ).where(NeverHaveIEverRoundRecord.game_id == game_id, NeverHaveIEverRoundRecord.state == "settled")))
        return sorted(users, key=str)
    elif game_type == "undercover":
        game = session.get(UndercoverGameRecord, game_id)
        if game.state != "settled" and not session.scalar(select(UndercoverGamePlayerRecord.id).where(
            UndercoverGamePlayerRecord.game_id == game_id, UndercoverGamePlayerRecord.state == "eliminated",
        ).limit(1)):
            return []
        query = select(UndercoverGamePlayerRecord.user_id).where(
            UndercoverGamePlayerRecord.game_id == game_id,
            UndercoverGamePlayerRecord.card_delivery_state == "delivered",
        )
    else:
        raise ValueError("unsupported game")
    return list(session.scalars(query.distinct()))


def sync_game_participations(session: Session, start: datetime, end: datetime, groups: Sequence[UUID]) -> None:
    for game_type, game_record in (("king_game", KingGameRecord), ("liar_dice", LiarDiceGameRecord)):
        for game in session.scalars(select(game_record).where(
            game_record.finished_at >= start, game_record.finished_at < end,
            game_record.group_chat_id.in_(groups), game_record.state.in_(("completed", "forced_ended")),
        )):
            record_game_participations(session, game_type, game.id, game.group_chat_id,
                                       resolved_game_users(session, game_type, game.id), game.finished_at)

    for game in session.scalars(select(TruthTradeGameRecord).where(
        TruthTradeGameRecord.finished_at >= start, TruthTradeGameRecord.finished_at < end,
        TruthTradeGameRecord.group_chat_id.in_(groups), TruthTradeGameRecord.state == "finished",
        TruthTradeGameRecord.settled_rounds > 0,
    )):
        record_game_participations(session, "truth_trade", game.id, game.group_chat_id,
                                   truth_trade_game_users(session, game), game.finished_at)

    for game in session.scalars(select(HideAndSeekGameRecord).where(
        HideAndSeekGameRecord.finished_at >= start, HideAndSeekGameRecord.finished_at < end,
        HideAndSeekGameRecord.group_chat_id.in_(groups), HideAndSeekGameRecord.state.in_(("won", "found")),
        HideAndSeekGameRecord.selected_number.is_not(None),
    )):
        record_game_participations(session, "hide_and_seek", game.id, game.group_chat_id,
                                   [game.user_id], game.finished_at)

    for game_type, game_record, participant, participant_id, states, filters in (
        ("texas_holdem", TexasHoldemGameRecord, TexasHoldemPlayerRecord, TexasHoldemPlayerRecord.game_id,
         ("settled",), (TexasHoldemGameRecord.settlement_complete.is_(True), TexasHoldemPlayerRecord.seat_number.is_not(None))),
        ("blame_bomb", BlameGameRecord, BlameGamePlayerRecord, BlameGamePlayerRecord.game_id,
         ("settled",), (BlameGameRecord.settlement_complete.is_(True), BlameGamePlayerRecord.state.in_(("winner", "loser")))),
        ("memory_assessment", MemoryAssessmentGameRecord, MemoryAssessmentParticipantRecord, MemoryAssessmentParticipantRecord.game_id,
         ("settled", "failed", "collected", "cancelled"), (
             or_(MemoryAssessmentGameRecord.state != "cancelled", exists(select(MemoryAssessmentRoundRecord.id).where(
                 MemoryAssessmentRoundRecord.game_id == MemoryAssessmentGameRecord.id,
                 MemoryAssessmentRoundRecord.state.in_(("answered", "failed")),
             ))),
             MemoryAssessmentParticipantRecord.state.in_(("settled", "failed", "winner", "lost", "disqualified", "surrendered", "cancelled")),
         )),
    ):
        rows = session.execute(select(game_record.id, game_record.group_chat_id, game_record.finished_at, participant.user_id).join(
            participant, participant_id == game_record.id,
        ).where(game_record.finished_at >= start, game_record.finished_at < end,
                game_record.group_chat_id.in_(groups), game_record.state.in_(states), *filters))
        for game_id, group_id, completed_at, user_id in rows:
            record_game_participations(session, game_type, game_id, group_id, [user_id], completed_at)

    for game in session.scalars(select(NeverHaveIEverGameRecord).where(
        NeverHaveIEverGameRecord.finished_at >= start, NeverHaveIEverGameRecord.finished_at < end,
        NeverHaveIEverGameRecord.group_chat_id.in_(groups),
        NeverHaveIEverGameRecord.state.in_(("completed", "forced_ended")),
    )):
        record_game_participations(session, "never_have_i_ever", game.id, game.group_chat_id,
                                   other_game_users(session, "never_have_i_ever", game.id), game.finished_at)

    for game_id, group_id, completed_at, user_id in session.execute(select(
        MemoryGuildMatchRecord.id, MemoryGuildMatchRecord.group_chat_id,
        MemoryGuildMatchRecord.finished_at, MemoryGuildMemberRecord.user_id,
    ).join(MemoryGuildSeriesRecord, MemoryGuildSeriesRecord.match_id == MemoryGuildMatchRecord.id).join(
        MemoryGuildRoundRecord, MemoryGuildRoundRecord.series_id == MemoryGuildSeriesRecord.id,
    ).join(MemoryGuildMemberRecord, or_(
        MemoryGuildMemberRecord.id == MemoryGuildSeriesRecord.team1_member_id,
        MemoryGuildMemberRecord.id == MemoryGuildSeriesRecord.team2_member_id,
    )).where(MemoryGuildMatchRecord.state.in_(("finished", "forced_ended")),
             MemoryGuildMatchRecord.finished_at >= start, MemoryGuildMatchRecord.finished_at < end,
             MemoryGuildMatchRecord.group_chat_id.in_(groups),
             MemoryGuildRoundRecord.state.in_(("finished", "drawn"))).distinct()):
        record_game_participations(session, "memory_guild", game_id, group_id, [user_id], completed_at)

    for game_id, group_id, completed_at, user_id in session.execute(select(
        NumberBombGameRecord.id, NumberBombGameRecord.group_chat_id,
        NumberBombGameRecord.finished_at, NumberBombRoundPlayerRecord.user_id,
    ).join(NumberBombRoundRecord, NumberBombRoundRecord.game_id == NumberBombGameRecord.id).join(
        NumberBombRoundPlayerRecord, NumberBombRoundPlayerRecord.round_id == NumberBombRoundRecord.id,
    ).where(NumberBombGameRecord.state == "ended", NumberBombGameRecord.finished_at >= start,
            NumberBombGameRecord.finished_at < end, NumberBombGameRecord.group_chat_id.in_(groups),
            NumberBombRoundRecord.state == "settled", NumberBombRoundPlayerRecord.submitted_number.is_not(None)).distinct()):
        record_game_participations(session, "number_bomb", game_id, group_id, [user_id], completed_at)

    for game, group_id in session.execute(select(
        UndercoverGameRecord, UndercoverSessionRecord.group_chat_id,
    ).join(UndercoverSessionRecord, UndercoverSessionRecord.id == UndercoverGameRecord.session_id,
    ).where(UndercoverGameRecord.state.in_(("settled", "ended")), UndercoverGameRecord.finished_at >= start,
            UndercoverGameRecord.finished_at < end, UndercoverSessionRecord.group_chat_id.in_(groups))):
        record_game_participations(session, "undercover", game.id, group_id,
                                   other_game_users(session, "undercover", game.id), game.finished_at)
