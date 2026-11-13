"""Current-company-season title eligibility and persistence."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Uuid,
    inspect,
    select,
)

from .bot_accounts import is_bot_platform_id
from .schema import (
    CompanySeasonTitleRecord,
    GameSettingsRecord,
    RankRecord,
    UserRecord,
)


SEASON_TABLES_METADATA = MetaData()
COMPANY_SEASONS = Table(
    "company_seasons",
    SEASON_TABLES_METADATA,
    Column("code", String(16), primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)
COMPANY_SEASON_SETTLEMENTS = Table(
    "company_season_settlements",
    SEASON_TABLES_METADATA,
    Column("id", Uuid, primary_key=True),
    Column("season_code", String(16), nullable=False),
    Column("user_id", Uuid, nullable=False),
    Column("is_bot", Boolean, nullable=False),
    Column("old_rank_id", Uuid),
    Column("breakdown", JSON, nullable=False),
)


_INELIGIBLE_REPLY = "上个赛季你的职位等级不允许你有赛季称号，这个赛季努努力吧"


def _validate_title_name(value: str) -> str:
    title = value.strip()
    if not 1 <= len(title) <= 20 or any(character in "\r\n" for character in title):
        raise ValueError("赛季称号需为 1～20 个字符，且不能包含换行")
    return title


class SeasonTitlesMixin:
    @staticmethod
    def _current_company_season(session, now):
        bind = session.get_bind()
        if (
            bind.dialect.name == "sqlite"
            and not inspect(bind).has_table("company_seasons")
        ):
            return None
        return session.execute(
            select(COMPANY_SEASONS)
            .where(COMPANY_SEASONS.c.applied_at <= now)
            .order_by(
                COMPANY_SEASONS.c.applied_at.desc(),
                COMPANY_SEASONS.c.code.desc(),
            )
            .limit(1)
        ).mappings().first()

    @staticmethod
    def _season_title_rank_order(session, user_id, season_code):
        settlement = session.execute(
            select(COMPANY_SEASON_SETTLEMENTS).where(
                COMPANY_SEASON_SETTLEMENTS.c.season_code == season_code,
                COMPANY_SEASON_SETTLEMENTS.c.user_id == user_id,
            )
        ).mappings().first()
        if settlement is None or settlement["is_bot"]:
            return None

        breakdown = settlement["breakdown"] or {}
        snapshot = breakdown.get("rank") or {}
        try:
            sort_order = int(snapshot.get("sort_order"))
        except (TypeError, ValueError):
            sort_order = None
        if sort_order is not None:
            return sort_order

        old_rank_id = settlement["old_rank_id"]
        if old_rank_id is None:
            return None
        old_rank = session.get(RankRecord, old_rank_id)
        return old_rank.sort_order if old_rank is not None else None

    @staticmethod
    def _season_title_settings(session):
        settings = session.get(GameSettingsRecord, 1)
        minimum_rank_order = (
            settings.season_title_minimum_rank_order if settings is not None else 8
        )
        daily_reward = settings.season_title_daily_reward if settings is not None else 5
        return minimum_rank_order, daily_reward

    def current_season_title(self, platform_id: str, now: datetime) -> dict | None:
        if is_bot_platform_id(platform_id):
            return None
        with self._session() as session:
            season = self._current_company_season(session, now)
            if season is None:
                return None
            user = session.scalar(
                select(UserRecord).where(UserRecord.platform_id == platform_id)
            )
            if user is None:
                return None
            minimum_rank_order, daily_reward = self._season_title_settings(session)
            rank_order = self._season_title_rank_order(
                session, user.id, season["code"]
            )
            if rank_order is None or rank_order < minimum_rank_order:
                return None
            record = session.scalar(
                select(CompanySeasonTitleRecord).where(
                    CompanySeasonTitleRecord.season_code == season["code"],
                    CompanySeasonTitleRecord.user_id == user.id,
                )
            )
            if record is None:
                return None
            return {
                "season_code": season["code"],
                "title_name": record.title_name,
                "daily_reward": daily_reward,
            }

    def define_season_title(
        self, platform_id: str, title_name: str, now: datetime
    ) -> dict:
        title = _validate_title_name(title_name)
        with self.transaction(), self._session() as session:
            season = self._current_company_season(session, now)
            if season is None:
                return {"status": "no_season"}
            user = session.scalar(
                select(UserRecord)
                .where(UserRecord.platform_id == platform_id)
                .with_for_update()
            )
            if user is None:
                return {"status": "not_joined"}

            minimum_rank_order, daily_reward = self._season_title_settings(session)
            rank_order = None
            if not is_bot_platform_id(platform_id):
                rank_order = self._season_title_rank_order(
                    session, user.id, season["code"]
                )
            if rank_order is None or rank_order < minimum_rank_order:
                return {"status": "not_qualified", "message": _INELIGIBLE_REPLY}

            record = session.scalar(
                select(CompanySeasonTitleRecord)
                .where(
                    CompanySeasonTitleRecord.season_code == season["code"],
                    CompanySeasonTitleRecord.user_id == user.id,
                )
                .with_for_update()
            )
            if record is None:
                session.add(
                    CompanySeasonTitleRecord(
                        season_code=season["code"],
                        user_id=user.id,
                        title_name=title,
                        defined_at=now,
                        updated_at=now,
                    )
                )
            elif record.title_name != title:
                record.title_name = title
                record.updated_at = now
            return {
                "status": "defined",
                "season_code": season["code"],
                "title_name": title,
                "daily_reward": daily_reward,
            }

    def season_title_daily_reward(self, platform_id: str, now: datetime) -> int:
        title = self.current_season_title(platform_id, now)
        return 0 if title is None else title["daily_reward"]
