from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.bot_accounts import BOT_PLATFORM_IDS
from dzmm_bot.core.schema import (
    Base,
    CompanySeasonTitleRecord,
    GameSettingsRecord,
    RankRecord,
    UserRecord,
)
from dzmm_bot.core.season_titles import (
    COMPANY_SEASONS,
    COMPANY_SEASON_SETTLEMENTS,
    SEASON_TABLES_METADATA,
    SeasonTitlesMixin,
)


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
INELIGIBLE_REPLY = "上个赛季你的职位等级不允许你有赛季称号，这个赛季努努力吧"


class Repository(SeasonTitlesMixin):
    def __init__(self, factory):
        self._factory = factory
        self._active_session = None

    @contextmanager
    def transaction(self):
        if self._active_session is not None:
            yield
            return
        with self._factory.begin() as session:
            self._active_session = session
            try:
                yield
            finally:
                self._active_session = None

    @contextmanager
    def _session(self):
        if self._active_session is not None:
            yield self._active_session
            return
        with self._factory.begin() as session:
            yield session


@pytest.fixture
def context():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SEASON_TABLES_METADATA.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    rank_ids = {order: uuid4() for order in (1, 7, 8, 10)}
    user_id = uuid4()
    with factory.begin() as session:
        session.add_all(
            RankRecord(
                id=rank_id,
                sort_order=order,
                name=f"职位 {order}",
                level_label=f"LV{order}",
                promotion_price=order * 10,
                checkin_reward=5,
                vote_weight=1,
                multiplayer_game_limit=1,
                has_group_management=False,
                is_board=False,
                enabled=True,
            )
            for order, rank_id in rank_ids.items()
        )
        session.add(
            UserRecord(
                id=user_id,
                platform_id="human",
                display_name="普通员工",
                employee_number=1,
                balance=0,
                rank_id=rank_ids[1],
                joined_at=NOW,
            )
        )
        session.add(
            GameSettingsRecord(
                id=1,
                currency_name="摸鱼币",
                onboarding_bonus=20,
                checkin_reward=2,
                weekly_attendance_reward=10,
                season_title_minimum_rank_order=8,
                season_title_daily_reward=5,
            )
        )
        session.execute(
            COMPANY_SEASONS.insert().values(code="S2", applied_at=NOW)
        )
    return Repository(factory), factory, user_id, rank_ids


def add_settlement(
    factory,
    *,
    season_code,
    user_id,
    rank_order,
    old_rank_id,
    is_bot=False,
):
    with factory.begin() as session:
        session.execute(
            COMPANY_SEASON_SETTLEMENTS.insert().values(
                id=uuid4(),
                season_code=season_code,
                user_id=user_id,
                is_bot=is_bot,
                old_rank_id=old_rank_id,
                breakdown={"rank": {"sort_order": rank_order}},
            )
        )


def test_title_uses_current_season_and_configured_daily_reward(context):
    repository, factory, user_id, rank_ids = context
    add_settlement(
        factory,
        season_code="S2",
        user_id=user_id,
        rank_order=8,
        old_rank_id=rank_ids[1],
    )
    with factory.begin() as session:
        session.get(GameSettingsRecord, 1).season_title_daily_reward = 7

    assert repository.define_season_title("human", "赛季先锋", NOW) == {
        "status": "defined",
        "season_code": "S2",
        "title_name": "赛季先锋",
        "daily_reward": 7,
    }
    assert repository.current_season_title("human", NOW) == {
        "season_code": "S2",
        "title_name": "赛季先锋",
        "daily_reward": 7,
    }
    assert repository.season_title_daily_reward("human", NOW) == 7


def test_breakdown_rank_snapshot_takes_priority_over_old_rank(context):
    repository, factory, user_id, rank_ids = context
    add_settlement(
        factory,
        season_code="S2",
        user_id=user_id,
        rank_order=8,
        old_rank_id=rank_ids[1],
    )

    assert repository.define_season_title("human", "快照达标", NOW)["status"] == "defined"


def test_old_rank_is_used_when_snapshot_rank_is_missing(context):
    repository, factory, user_id, rank_ids = context
    with factory.begin() as session:
        session.execute(
            COMPANY_SEASON_SETTLEMENTS.insert().values(
                id=uuid4(),
                season_code="S2",
                user_id=user_id,
                is_bot=False,
                old_rank_id=rank_ids[8],
                breakdown={"rank": {}},
            )
        )

    assert repository.define_season_title("human", "旧职位达标", NOW)["status"] == "defined"


def test_below_configured_rank_is_ineligible(context):
    repository, factory, user_id, rank_ids = context
    add_settlement(
        factory,
        season_code="S2",
        user_id=user_id,
        rank_order=7,
        old_rank_id=rank_ids[10],
    )

    assert repository.define_season_title("human", "差一级", NOW) == {
        "status": "not_qualified",
        "message": INELIGIBLE_REPLY,
    }


def test_current_title_is_hidden_after_admin_raises_rank_threshold(context):
    repository, factory, user_id, rank_ids = context
    add_settlement(
        factory,
        season_code="S2",
        user_id=user_id,
        rank_order=8,
        old_rank_id=rank_ids[8],
    )
    repository.define_season_title("human", "曾经达标", NOW)
    with factory.begin() as session:
        session.get(GameSettingsRecord, 1).season_title_minimum_rank_order = 10

    assert repository.current_season_title("human", NOW) is None
    assert repository.season_title_daily_reward("human", NOW) == 0


def test_bot_cannot_define_or_receive_season_title_reward(context):
    repository, factory, _, rank_ids = context
    bot_id = uuid4()
    bot_platform_id = next(iter(BOT_PLATFORM_IDS))
    with factory.begin() as session:
        session.add(
            UserRecord(
                id=bot_id,
                platform_id=bot_platform_id,
                display_name="机器人",
                employee_number=2,
                balance=0,
                rank_id=rank_ids[10],
                joined_at=NOW,
            )
        )
    add_settlement(
        factory,
        season_code="S2",
        user_id=bot_id,
        rank_order=10,
        old_rank_id=rank_ids[10],
        is_bot=True,
    )

    assert repository.define_season_title(bot_platform_id, "机器人称号", NOW) == {
        "status": "not_qualified",
        "message": INELIGIBLE_REPLY,
    }
    assert repository.current_season_title(bot_platform_id, NOW) is None
    assert repository.season_title_daily_reward(bot_platform_id, NOW) == 0


def test_define_reports_missing_employee_and_season(context):
    repository, factory, _, _ = context
    assert repository.define_season_title("missing", "称号", NOW) == {
        "status": "not_joined"
    }
    with factory.begin() as session:
        session.execute(COMPANY_SEASONS.delete())
    assert repository.define_season_title("human", "称号", NOW) == {
        "status": "no_season"
    }


def test_same_season_title_update_is_idempotent(context):
    repository, factory, user_id, rank_ids = context
    add_settlement(
        factory,
        season_code="S2",
        user_id=user_id,
        rank_order=8,
        old_rank_id=rank_ids[8],
    )
    repository.define_season_title("human", "先锋", NOW)
    repository.define_season_title("human", "先锋", NOW + timedelta(hours=1))

    with factory.begin() as session:
        first = session.scalar(select(CompanySeasonTitleRecord))
        assert first.defined_at == NOW
        assert first.updated_at == NOW

    repository.define_season_title("human", "领航者", NOW + timedelta(hours=2))
    with factory.begin() as session:
        record = session.scalar(select(CompanySeasonTitleRecord))
        assert session.scalar(
            select(func.count()).select_from(CompanySeasonTitleRecord)
        ) == 1
        assert record.title_name == "领航者"
        assert record.defined_at == NOW
        assert record.updated_at == NOW + timedelta(hours=2)


def test_new_season_does_not_read_previous_season_title(context):
    repository, factory, user_id, rank_ids = context
    add_settlement(
        factory,
        season_code="S2",
        user_id=user_id,
        rank_order=8,
        old_rank_id=rank_ids[8],
    )
    repository.define_season_title("human", "S2 称号", NOW)

    with factory.begin() as session:
        session.execute(
            COMPANY_SEASONS.insert().values(
                code="S3", applied_at=NOW + timedelta(days=30)
            )
        )
    add_settlement(
        factory,
        season_code="S3",
        user_id=user_id,
        rank_order=10,
        old_rank_id=rank_ids[10],
    )

    assert repository.current_season_title("human", NOW + timedelta(days=30)) is None
    assert repository.season_title_daily_reward("human", NOW + timedelta(days=30)) == 0
    repository.define_season_title("human", "S3 称号", NOW + timedelta(days=30))
    assert repository.current_season_title("human", NOW + timedelta(days=30)) == {
        "season_code": "S3",
        "title_name": "S3 称号",
        "daily_reward": 5,
    }


def test_future_season_does_not_activate_early(context):
    repository, factory, user_id, rank_ids = context
    add_settlement(
        factory,
        season_code="S2",
        user_id=user_id,
        rank_order=8,
        old_rank_id=rank_ids[8],
    )
    repository.define_season_title("human", "当前赛季", NOW)
    with factory.begin() as session:
        session.execute(
            COMPANY_SEASONS.insert().values(
                code="S3", applied_at=NOW + timedelta(days=30)
            )
        )
    add_settlement(
        factory,
        season_code="S3",
        user_id=user_id,
        rank_order=10,
        old_rank_id=rank_ids[10],
    )

    assert repository.current_season_title("human", NOW) == {
        "season_code": "S2",
        "title_name": "当前赛季",
        "daily_reward": 5,
    }


@pytest.mark.parametrize("name", ["", "   ", "换\n行", "a" * 21])
def test_title_name_validation(context, name):
    repository, factory, user_id, rank_ids = context
    add_settlement(
        factory,
        season_code="S2",
        user_id=user_id,
        rank_order=8,
        old_rank_id=rank_ids[8],
    )

    with pytest.raises(ValueError):
        repository.define_season_title("human", name, NOW)
