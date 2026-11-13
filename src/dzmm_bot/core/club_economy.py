"""Shared coin stakes and rake settings for Club game modules."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from .schema import ClubGameEconomySettingRecord


CLUB_ECONOMY_GAMES = (
    "mahjong",
    "chess",
    "doudizhu",
    "drawguess",
    "texas",
    "zhajinhua",
    "blackjack",
    "niuniu",
)
DEFAULT_CLUB_COIN_STAKES = (5, 10, 20)
DEFAULT_CLUB_RAKE_PERCENT = 20


@dataclass(frozen=True)
class ClubGameEconomySetting:
    game: str
    coin_stakes: tuple[int, ...]
    rake_percent: int


def _validate_game(game: str) -> str:
    if game not in CLUB_ECONOMY_GAMES:
        raise ValueError("不支持的 Club 游戏")
    return game


def _validate_coin_stakes(coin_stakes) -> tuple[int, ...]:
    values = tuple(coin_stakes)
    if (
        not 1 <= len(values) <= 6
        or any(type(value) is not int or not 1 <= value <= 99999 for value in values)
        or tuple(sorted(set(values))) != values
    ):
        raise ValueError("摸鱼币场次必须为 1 至 6 个、1 至 99999 的升序唯一整数")
    return values


def _validate_rake_percent(rake_percent: int) -> int:
    if type(rake_percent) is not int or not 0 <= rake_percent <= 100:
        raise ValueError("抽水比例必须为 0 至 100 的整数")
    return rake_percent


class ClubEconomyMixin:
    @staticmethod
    def _club_game_economy_view(
        record: ClubGameEconomySettingRecord,
    ) -> ClubGameEconomySetting:
        return ClubGameEconomySetting(
            game=record.game,
            coin_stakes=tuple(record.coin_stakes),
            rake_percent=record.rake_percent,
        )

    @staticmethod
    def _seed_club_game_economy_settings(session) -> None:
        existing = set(
            session.scalars(select(ClubGameEconomySettingRecord.game)).all()
        )
        for game in CLUB_ECONOMY_GAMES:
            if game not in existing:
                session.add(
                    ClubGameEconomySettingRecord(
                        game=game,
                        coin_stakes=list(DEFAULT_CLUB_COIN_STAKES),
                        rake_percent=DEFAULT_CLUB_RAKE_PERCENT,
                    )
                )
        session.flush()

    def list_club_game_economy_settings(
        self,
    ) -> tuple[ClubGameEconomySetting, ...]:
        with self._session() as session:
            self._seed_club_game_economy_settings(session)
            records = {
                record.game: record
                for record in session.scalars(
                    select(ClubGameEconomySettingRecord)
                ).all()
            }
            return tuple(
                self._club_game_economy_view(records[game])
                for game in CLUB_ECONOMY_GAMES
            )

    def get_club_game_economy_settings(
        self, game: str
    ) -> ClubGameEconomySetting:
        _validate_game(game)
        with self._session() as session:
            self._seed_club_game_economy_settings(session)
            record = session.get(ClubGameEconomySettingRecord, game)
            if record is None:
                raise RuntimeError("Club 游戏经济设置消失")
            return self._club_game_economy_view(record)

    def set_club_game_economy_settings(
        self,
        game: str,
        *,
        coin_stakes,
        rake_percent: int,
    ) -> ClubGameEconomySetting:
        _validate_game(game)
        stakes = _validate_coin_stakes(coin_stakes)
        rake = _validate_rake_percent(rake_percent)
        with self._session() as session:
            self._seed_club_game_economy_settings(session)
            record = session.get(ClubGameEconomySettingRecord, game)
            if record is None:
                raise RuntimeError("Club 游戏经济设置消失")
            record.coin_stakes = list(stakes)
            record.rake_percent = rake
            session.flush()
            return self._club_game_economy_view(record)
