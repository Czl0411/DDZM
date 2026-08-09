import os
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from dzmm_bot.core.schema import BEIJING
from dzmm_bot.runtime.contracts import InboundMessage, LoginState, WorkerHeartbeat


_UNDERCOVER_WORD_CATEGORIES = {
    "办公职场", "饮食饮品", "日常用品", "地点场景", "交通出行",
    "影视娱乐", "动物自然", "校园生活", "互联网科技",
}


def _undercover_word_migration_module():
    path = Path("migrations/versions/20260807_25_undercover_word_sets.py")
    spec = importlib.util.spec_from_file_location("undercover_word_sets_migration", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def now():
    return datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def inbound(now):
    return InboundMessage("platform-1", "sender-1", "hello", now)


@pytest.fixture
def session_factory():
    from dzmm_bot.core.schema import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def repository(session_factory):
    from dzmm_bot.core.repository import CoreRepository

    return CoreRepository(session_factory)


def test_duplicate_platform_message_returns_existing_record(repository, inbound):
    first, inserted = repository.accept_inbound(inbound)
    second, duplicate = repository.accept_inbound(inbound)

    assert inserted is True
    assert duplicate is False
    assert second.id == first.id


def test_random_event_settings_default_to_fixed_daily_times(repository):
    settings = repository.get_random_event_settings()

    assert settings.schedule_times == [
        "00:00",
        "02:00",
        "10:00",
        "14:00",
        "16:00",
        "20:00",
    ]
    assert "{可选身份}" in settings.signup_notice_template


def test_hide_and_seek_defaults_seed_ten_company_scenes(repository):
    settings = repository.get_hide_and_seek_settings()
    scenes, total = repository.list_hide_and_seek_scenes_page(1, 20)

    assert (
        settings.enabled,
        settings.entry_fee,
        settings.win_reward,
        settings.daily_limit,
        settings.selection_timeout_minutes,
    ) == (True, 1, 3, 2, 2)
    assert total == 10
    assert {scene.name for scene in scenes} >= {"公司前台", "茶水间", "公司天台"}


def test_memory_assessment_defaults_seed_five_levels(repository):
    settings = repository.get_memory_assessment_settings()

    assert settings.single_daily_limit == 1
    assert settings.duel_base_pool == 5
    assert [
        (rule.level, rule.answer_length, rule.reward)
        for rule in repository.list_memory_assessment_levels()
    ] == [(1, 5, 1), (2, 7, 2), (3, 9, 3), (4, 11, 4), (5, 13, 5)]


def test_ai_memory_schema_keeps_one_snapshot_per_player():
    from dzmm_bot.core.schema import (
        AIPlayerMemoryRecord,
        AIMemoryJobRecord,
        AIMemorySettingsRecord,
        Base,
    )

    assert {
        "ai_memory_settings",
        "ai_player_memories",
        "ai_memory_jobs",
    } <= set(Base.metadata.tables)
    assert {"user_id"} == {
        column.name for column in AIPlayerMemoryRecord.__table__.primary_key.columns
    }
    assert AIMemoryJobRecord.__table__.c.target_message_id.nullable is False
    assert AIMemorySettingsRecord.__tablename__ == "ai_memory_settings"


def test_ai_request_queues_one_memory_job_for_the_same_player(repository, now):
    from dzmm_bot.core.schema import AIAssistantSettingsRecord

    user, _ = repository.create_user("memory-player", "阿彻", now, 0)
    repository.get_ai_assistant_settings()
    with repository._session() as session:
        session.get(AIAssistantSettingsRecord, 1).enabled = True
        session.commit()

    result = repository.try_enqueue_ai_request(
        uuid4(), user.platform_id, "@总监事 我喜欢简短回复", now
    )

    assert result.state == "queued"
    claim = repository.claim_ai_memory_job("memory-worker", now, 30)
    assert claim is not None
    assert claim.user_id == user.id


def test_ai_memory_claim_reads_only_the_players_effective_messages(repository, now):
    from dzmm_bot.core.schema import AIAssistantSettingsRecord

    user, _ = repository.create_user("memory-context-player", "阿彻", now, 0)
    repository.get_ai_assistant_settings()
    with repository._session() as session:
        session.get(AIAssistantSettingsRecord, 1).enabled = True
        session.commit()
    repository.accept_inbound(
        InboundMessage("memory-1", user.platform_id, "我喜欢简短一点的回复", now)
    )
    repository.accept_inbound(
        InboundMessage("memory-2", user.platform_id, "/打卡", now + timedelta(seconds=1))
    )
    repository.accept_inbound(
        InboundMessage("memory-3", user.platform_id, "（围观一下）", now + timedelta(seconds=2))
    )
    trigger, _ = repository.accept_inbound(
        InboundMessage("memory-4", user.platform_id, "@总监事 我喜欢桌游", now + timedelta(seconds=3))
    )

    assert repository.try_enqueue_ai_request(
        trigger.id, user.platform_id, trigger.content, now + timedelta(seconds=3)
    ).state == "queued"
    claim = repository.claim_ai_memory_job("memory-worker", now + timedelta(seconds=4), 30)

    assert claim is not None
    assert claim.current_memory == ""
    assert claim.source_messages == ("我喜欢简短一点的回复", "@总监事 我喜欢桌游")


def test_ai_memory_completion_keeps_a_newer_trigger_pending(repository, now):
    from dzmm_bot.core.schema import (
        AIAssistantSettingsRecord,
        AIMemoryJobRecord,
        AIRankQuotaRecord,
    )

    user, _ = repository.create_user("memory-follow-up", "阿彻", now, 0)
    repository.get_ai_assistant_settings()
    with repository._session() as session:
        session.get(AIAssistantSettingsRecord, 1).enabled = True
        session.get(AIRankQuotaRecord, user.rank_id).daily_limit = 2
        session.commit()
    first, _ = repository.accept_inbound(
        InboundMessage("memory-follow-up-1", user.platform_id, "@总监事 我喜欢桌游", now)
    )
    assert repository.try_enqueue_ai_request(
        first.id, user.platform_id, first.content, now
    ).state == "queued"
    claim = repository.claim_ai_memory_job("memory-worker", now, 30)
    assert claim is not None
    second, _ = repository.accept_inbound(
        InboundMessage(
            "memory-follow-up-2",
            user.platform_id,
            "@总监事 也喜欢短回复",
            now + timedelta(seconds=1),
        )
    )
    assert repository.try_enqueue_ai_request(
        second.id, user.platform_id, second.content, now + timedelta(seconds=1)
    ).state == "queued"

    assert repository.complete_ai_memory_job(
        user.id,
        "memory-worker",
        claim.lease_token,
        claim.target_message_id,
        "喜欢桌游",
        now + timedelta(seconds=2),
    ) is True
    with repository._session() as session:
        job = session.get(AIMemoryJobRecord, user.id)
        assert job is not None
        assert job.target_message_id == second.id
        assert job.status == "pending"


def test_undercover_word_migration_seeds_nine_unique_categories():
    rows = _undercover_word_migration_module()._seed_rows()

    assert len(rows) == 900
    assert {row["category"] for row in rows} == _UNDERCOVER_WORD_CATEGORIES
    assert all(row["enabled"] for row in rows)
    assert all(
        sum(row["category"] == category for row in rows) == 100
        for category in _UNDERCOVER_WORD_CATEGORIES
    )
    assert all(
        row["civilian_word"].strip() and row["undercover_word"].strip()
        for row in rows
    )
    assert len(
        {
            tuple(sorted((row["civilian_word"], row["undercover_word"])))
            for row in rows
        }
    ) == 900


def test_undercover_schema_declares_game_persistence_contract():
    from dzmm_bot.core.schema import Base

    tables = Base.metadata.tables

    assert {
        "undercover_settings",
        "undercover_role_rules",
        "direct_chats",
        "undercover_sessions",
        "undercover_session_members",
        "undercover_games",
        "undercover_game_players",
        "undercover_votes",
    } <= set(tables)
    assert {"player_count"} == {
        column.name
        for column in tables["undercover_role_rules"].primary_key.columns
    }
    assert any(
        {"game_id", "round_number", "voter_user_id"}
        == {column.name for column in constraint.columns}
        for constraint in tables["undercover_votes"].constraints
    )


def test_ai_assistant_schema_declares_queue_and_daily_quota_contract():
    """Fails if duplicate inbound requests or a second daily counter can exist."""
    from dzmm_bot.core.schema import (
        AIAssistantSettingsRecord,
        AIRankQuotaRecord,
        AIRequestRecord,
        Base,
        DailyAIUsageRecord,
    )

    tables = Base.metadata.tables

    assert {
        "ai_assistant_settings",
        "ai_rank_quotas",
        "daily_ai_usage",
        "ai_requests",
    } <= set(tables)
    assert AIAssistantSettingsRecord.__tablename__ == "ai_assistant_settings"
    assert AIRankQuotaRecord.__tablename__ == "ai_rank_quotas"
    assert {"user_id", "usage_date"} == {
        column.name for column in DailyAIUsageRecord.__table__.primary_key.columns
    }
    assert AIRequestRecord.__table__.c.inbound_message_id.unique is True


def test_ai_request_quota_is_consumed_only_until_rank_limit(
    repository, session_factory, now
):
    """Fails if a second same-day request bypasses the configured rank limit."""
    from dzmm_bot.core.schema import AIAssistantSettingsRecord, AIRankQuotaRecord

    user, _ = repository.create_user("ai-user", "AI 员工", now, 0)
    repository.get_ai_assistant_settings()
    with session_factory.begin() as session:
        session.get(AIAssistantSettingsRecord, 1).enabled = True
        session.get(AIRankQuotaRecord, user.rank_id).daily_limit = 1
    first_inbound, _ = repository.accept_inbound(
        InboundMessage("ai-inbound-1", "ai-user", "@总监事 你好", now)
    )
    second_inbound, _ = repository.accept_inbound(
        InboundMessage("ai-inbound-2", "ai-user", "@总监事 在吗", now)
    )

    assert repository.try_enqueue_ai_request(
        first_inbound.id, "ai-user", "你好", now
    ).state == "queued"
    assert repository.try_enqueue_ai_request(
        second_inbound.id, "ai-user", "在吗", now
    ).state == "over_limit"


def test_completed_ai_request_enqueues_one_existing_outbound_message(
    repository, session_factory, now
):
    """Fails if a valid worker completion does not use the normal outbound queue."""
    from dzmm_bot.core.schema import AIAssistantSettingsRecord, OutboundRecord

    repository.create_user("ai-user", "AI 员工", now, 0)
    repository.get_ai_assistant_settings()
    with session_factory.begin() as session:
        session.get(AIAssistantSettingsRecord, 1).enabled = True
    inbound, _ = repository.accept_inbound(
        InboundMessage("ai-inbound-3", "ai-user", "@总监事 你好", now)
    )
    assert repository.try_enqueue_ai_request(
        inbound.id, "ai-user", "你好", now
    ).state == "queued"

    claimed = repository.claim_ai_request("ai-worker-1", now, 90)

    assert claimed is not None
    assert repository.complete_ai_request(
        claimed.id, "ai-worker-1", claimed.lease_token, "收到", now
    ) is True
    with session_factory() as session:
        assert session.scalar(select(OutboundRecord.text)) == "收到"


def test_ai_request_prompt_uses_live_profile_and_saved_memory(
    repository, session_factory, now
):
    from dzmm_bot.core.schema import AIAssistantSettingsRecord, AIPlayerMemoryRecord

    user, _ = repository.create_user("ai-profile", "阿彻", now, 23)
    repository.get_ai_assistant_settings()
    with session_factory.begin() as session:
        session.get(AIAssistantSettingsRecord, 1).enabled = True
        session.add(
            AIPlayerMemoryRecord(
                user_id=user.id,
                memory_text="偏好简短回复，喜欢桌游。",
                last_scanned_message_id=None,
                created_at=now,
                updated_at=now,
            )
        )
    inbound, _ = repository.accept_inbound(
        InboundMessage("ai-profile-inbound", user.platform_id, "@总监事 在吗", now)
    )
    assert repository.try_enqueue_ai_request(
        inbound.id, user.platform_id, inbound.content, now
    ).state == "queued"

    claim = repository.claim_ai_request("ai-worker", now, 90)

    assert claim is not None
    assert "昵称：阿彻" in claim.system_prompt
    assert "余额：23 摸鱼币" in claim.system_prompt
    assert "偏好简短回复，喜欢桌游。" in claim.system_prompt
    assert "核心玩法指引" in claim.system_prompt


def _prepare_undercover_players(repository, session_factory, now, count=4):
    from dzmm_bot.core.schema import UndercoverWordSetRecord

    with session_factory.begin() as session:
        session.add(
            UndercoverWordSetRecord(
                category="测试",
                civilian_word="咖啡",
                undercover_word="奶茶",
                enabled=True,
                created_at=now,
            )
        )
    platform_ids = [f"undercover-{number}" for number in range(1, count + 1)]
    for platform_id in platform_ids:
        repository.create_user(platform_id, platform_id, now, 0)
    repository.upsert_direct_chats(
        [(platform_id, f"direct-{platform_id}") for platform_id in platform_ids], now
    )
    return platform_ids


def _start_undercover_game(repository, session_factory, now, count=4):
    platform_ids = _prepare_undercover_players(repository, session_factory, now, count)
    first = repository.start_undercover_signup(platform_ids[0], count, now)
    for platform_id in platform_ids[1:]:
        result = repository.join_undercover(platform_id, now)
    assert result.status == "dealing"
    for platform_id in platform_ids:
        result = repository.record_undercover_card_delivery(
            result.game_id, platform_id, True, now
        )
    assert result.status == "speaking"
    return result, platform_ids


def test_undercover_requires_direct_chat_then_deals_configured_roles(
    repository, session_factory, now
):
    repository.create_user("undercover-1", "甲", now, 0)

    assert repository.start_undercover_signup("undercover-1", 4, now).status == "direct_chat_required"

    platform_ids = _prepare_undercover_players(repository, session_factory, now)
    assert repository.start_undercover_signup(platform_ids[0], 4, now).status == "signup_started"
    for platform_id in platform_ids[1:]:
        result = repository.join_undercover(platform_id, now)

    assert result.status == "dealing"
    assert result.player_count == 4
    assert sorted(result.roles) == ["civilian", "civilian", "civilian", "undercover"]


def test_undercover_cards_are_direct_and_group_opening_waits_for_delivery(
    repository, session_factory, now
):
    from dzmm_bot.core.schema import OutboundRecord, UndercoverGamePlayerRecord

    platform_ids = _prepare_undercover_players(repository, session_factory, now)
    repository.start_undercover_signup(platform_ids[0], 4, now)
    for platform_id in platform_ids[1:]:
        result = repository.join_undercover(platform_id, now)

    with session_factory() as session:
        cards = list(
            session.scalars(
                select(OutboundRecord)
                .where(OutboundRecord.delivery_kind == "undercover_card")
                .order_by(OutboundRecord.id)
            )
        )
        players = list(
            session.scalars(
                select(UndercoverGamePlayerRecord).where(
                    UndercoverGamePlayerRecord.game_id == result.game_id
                )
            )
        )

    assert {card.destination_chatroom_id for card in cards} == {
        f"direct-{platform_id}" for platform_id in platform_ids
    }
    assert len(cards) == len(players) == 4
    assert {player.card_outbound_message_id for player in players} == {card.id for card in cards}

    for index in range(4):
        claimed = repository.claim_outbound(f"worker-{index}", now, 30)
        assert claimed is not None
        assert repository.confirm_sent(
            claimed.id, f"worker-{index}", claimed.lease_token, f"sent-{index}", now
        )

    assert repository.undercover_session_summary().state == "speaking"
    opening = repository.claim_outbound("worker-group", now, 30)
    assert opening is not None
    assert opening.delivery_kind == "group"
    assert opening.destination_chatroom_id is None
    assert opening.text == "【谁是卧底】所有身份已私聊发放，请开始描述。"


def test_undercover_card_delivery_failure_restores_signup_without_public_cards(
    repository, session_factory, now
):
    from dzmm_bot.core.schema import OutboundRecord

    platform_ids = _prepare_undercover_players(repository, session_factory, now)
    repository.start_undercover_signup(platform_ids[0], 4, now)
    for platform_id in platform_ids[1:]:
        result = repository.join_undercover(platform_id, now)

    card = repository.claim_outbound("worker-a", now, 30)
    assert card is not None
    assert repository.mark_outbound_failed(card.id, "worker-a", card.lease_token, now)

    assert repository.undercover_session_summary().state == "signup"
    with session_factory() as session:
        pending_cards = list(
            session.scalars(
                select(OutboundRecord).where(OutboundRecord.delivery_kind == "undercover_card")
            )
        )
    assert {record.status for record in pending_cards} == {"failed"}
    notice = repository.claim_outbound("worker-group", now, 30)
    assert notice is not None
    assert notice.destination_chatroom_id is None
    assert "私聊发放失败" in notice.text


def test_undercover_tied_vote_requires_a_new_vote_round(repository, session_factory, now):
    result, platform_ids = _start_undercover_game(repository, session_factory, now)

    assert repository.start_undercover_vote(platform_ids[0], now).status == "voting"
    for voter, target_seat in zip(platform_ids, (2, 3, 2, 3), strict=True):
        result = repository.cast_undercover_vote(voter, target_seat, now)

    assert result.status == "tied"
    assert repository.start_undercover_vote(platform_ids[0], now).status == "voting"


def test_undercover_unique_vote_eliminates_then_awaits_continuation_on_win(
    repository, session_factory, now
):
    result, platform_ids = _start_undercover_game(repository, session_factory, now)
    role_by_platform_id = dict(zip(result.player_ids, result.roles, strict=True))
    undercover_platform_id = next(
        platform_id
        for platform_id, role in role_by_platform_id.items()
        if role == "undercover"
    )
    summary = repository.undercover_session_summary()
    undercover_seat = next(
        player.seat_number
        for player in summary.players
        if player.platform_id == undercover_platform_id
    )

    repository.start_undercover_vote(platform_ids[0], now)
    for voter in platform_ids:
        result = repository.cast_undercover_vote(voter, undercover_seat, now)

    assert result.status == "settled"
    assert result.winner == "civilian"
    assert repository.undercover_session_summary().state == "awaiting_continue"


def test_undercover_continuation_keeps_original_players_then_uses_queue(
    repository, session_factory, now
):
    result, platform_ids = _start_undercover_game(repository, session_factory, now)
    role_by_platform_id = dict(zip(result.player_ids, result.roles, strict=True))
    undercover_platform_id = next(
        platform_id
        for platform_id, role in role_by_platform_id.items()
        if role == "undercover"
    )
    undercover_seat = next(
        player.seat_number
        for player in repository.undercover_session_summary().players
        if player.platform_id == undercover_platform_id
    )
    repository.start_undercover_vote(platform_ids[0], now)
    for voter in platform_ids:
        repository.cast_undercover_vote(voter, undercover_seat, now)

    repository.create_user("undercover-5", "undercover-5", now, 0)
    repository.upsert_direct_chats([("undercover-5", "direct-undercover-5")], now)
    assert repository.join_undercover("undercover-5", now).status == "queued"

    result = repository.continue_undercover(platform_ids[0], now)

    assert result.status == "dealing"
    assert result.player_count == 5
    assert set(result.player_ids) == {*platform_ids, "undercover-5"}
    assert sorted(result.roles) == [
        "civilian", "civilian", "civilian", "undercover", "whiteboard"
    ]


def test_undercover_expires_awaiting_continuation_after_twenty_minutes(
    repository, session_factory, now
):
    result, platform_ids = _start_undercover_game(repository, session_factory, now)
    role_by_platform_id = dict(zip(result.player_ids, result.roles, strict=True))
    undercover_platform_id = next(
        platform_id
        for platform_id, role in role_by_platform_id.items()
        if role == "undercover"
    )
    undercover_seat = next(
        player.seat_number
        for player in repository.undercover_session_summary().players
        if player.platform_id == undercover_platform_id
    )
    repository.start_undercover_vote(platform_ids[0], now)
    for voter in platform_ids:
        repository.cast_undercover_vote(voter, undercover_seat, now)

    assert repository.run_undercover_jobs(now + timedelta(minutes=20)) == ["expired"]
    assert repository.undercover_session_summary().state is None


def test_daily_jobs_notifies_group_when_undercover_signup_expires(
    repository, session_factory, now
):
    from dzmm_bot.core.schema import OutboundRecord

    platform_ids = _prepare_undercover_players(repository, session_factory, now)
    assert repository.start_undercover_signup(platform_ids[0], 4, now).status == "signup_started"

    repository.run_daily_jobs(now + timedelta(minutes=2))

    with session_factory() as session:
        notice = session.scalar(
            select(OutboundRecord)
            .where(OutboundRecord.inbound_message_id.is_(None))
            .order_by(OutboundRecord.created_at.desc())
        )
    assert notice is not None
    assert notice.text == "【谁是卧底】报名超时，本局已关闭。"


def test_undercover_active_session_blocks_memory_assessment_duel(
    repository, session_factory, now
):
    _start_undercover_game(repository, session_factory, now)

    assert repository.start_memory_assessment_duel("undercover-1", now).status == "multiplayer_active"


def test_due_random_event_waits_while_undercover_signup_is_active(
    repository, session_factory, now
):
    platform_ids = _prepare_undercover_players(repository, session_factory, now)
    repository.create_random_event_scene("茶水间", "报名", ["开场"], 1, 1, [("员工", 1)])
    repository.set_random_event_settings(["20:00"], "可选身份：{可选身份}", 15, 5)
    repository.schedule_random_events(now)
    assert repository.start_undercover_signup(platform_ids[0], 4, now).status == "signup_started"

    repository.run_random_event_jobs(now)

    schedules = repository.list_today_random_event_schedules(now)
    assert schedules[0].status == "pending"
    assert repository.active_random_event_state() is None


def test_undercover_exit_rechecks_winner_and_manual_end_releases_session(
    repository, session_factory, now
):
    result, _ = _start_undercover_game(repository, session_factory, now)
    role_by_platform_id = dict(zip(result.player_ids, result.roles, strict=True))
    undercover_platform_id = next(
        platform_id
        for platform_id, role in role_by_platform_id.items()
        if role == "undercover"
    )

    result = repository.leave_undercover(undercover_platform_id, now)

    assert result.status == "settled"
    assert result.winner == "civilian"
    remaining_platform_id = next(
        platform_id for platform_id in result.player_ids if platform_id != undercover_platform_id
    )
    assert repository.end_undercover(remaining_platform_id, now).status == "ended"
    assert repository.undercover_session_summary().state is None


def test_undercover_signup_member_can_end_the_pending_game(repository, session_factory, now):
    platform_ids = _prepare_undercover_players(repository, session_factory, now)
    assert repository.start_undercover_signup(platform_ids[0], 4, now).status == "signup_started"
    assert repository.join_undercover(platform_ids[1], now).status == "joined_signup"

    result = repository.end_undercover(platform_ids[1], now)

    assert result.status == "ended"
    assert repository.undercover_session_summary().state is None


def test_new_employee_has_default_rank_and_department(repository, now):
    repository.create_user("employee-1", "小明", now, 0)

    profile = repository.get_user_profile("employee-1")

    assert profile.rank.name == "实习生"
    assert profile.rank.level_label == "LV1"
    assert profile.department.name == "未分配部门"


def test_department_application_changes_department_only_after_eligible_approval(
    repository, session_factory, now
):
    from dzmm_bot.core.schema import DepartmentRecord, RankRecord, UserRecord

    applicant, _ = repository.create_user("employee-1", "小明", now, 0)
    approver, _ = repository.create_user("employee-2", "小红", now, 0)
    with session_factory.begin() as session:
        target = session.scalar(
            select(DepartmentRecord).where(DepartmentRecord.name == "核心技术部")
        )
        rank_two = session.scalar(select(RankRecord).where(RankRecord.sort_order == 2))
        approver_record = session.get(UserRecord, approver.id)
        assert target is not None
        assert rank_two is not None
        assert approver_record is not None
        approver_record.department_id = target.id
        approver_record.rank_id = rank_two.id

    request = repository.request_department_change("employee-1", "核心技术部", now)

    assert request.status == "requested"
    assert repository.get_user_profile("employee-1").department.name == "未分配部门"
    assert [result.status for result in repository.decide_department_requests(
        "employee-2", [request.number], "approved", now
    )] == ["approved"]
    assert repository.get_user_profile("employee-1").department.name == "核心技术部"


def test_department_application_enforces_approver_eligibility_and_expiry(
    repository, session_factory, now
):
    from dzmm_bot.core.schema import DepartmentRecord, RankRecord, UserRecord

    for platform_id in ("applicant", "same-rank", "other-department", "eligible"):
        repository.create_user(platform_id, platform_id, now, 0)
    with session_factory.begin() as session:
        target = session.scalar(
            select(DepartmentRecord).where(DepartmentRecord.name == "核心技术部")
        )
        other = session.scalar(
            select(DepartmentRecord).where(DepartmentRecord.name == "学院")
        )
        rank_two = session.scalar(select(RankRecord).where(RankRecord.sort_order == 2))
        assert target is not None
        assert other is not None
        assert rank_two is not None
        for platform_id in ("other-department", "eligible"):
            employee = session.scalar(
                select(UserRecord).where(UserRecord.platform_id == platform_id)
            )
            assert employee is not None
            employee.rank_id = rank_two.id
        session.scalar(select(UserRecord).where(UserRecord.platform_id == "same-rank")).department_id = target.id
        session.scalar(select(UserRecord).where(UserRecord.platform_id == "other-department")).department_id = other.id
        session.scalar(select(UserRecord).where(UserRecord.platform_id == "eligible")).department_id = target.id

    request = repository.request_department_change("applicant", "核心技术部", now)
    assert repository.decide_department_requests("same-rank", [request.number], "approved", now)[0].status == "not_authorized"
    assert repository.decide_department_requests("other-department", [request.number], "approved", now)[0].status == "not_authorized"
    assert repository.decide_department_requests("eligible", [request.number], "rejected", now)[0].status == "rejected"
    assert repository.get_user_profile("applicant").department.name == "未分配部门"

    expired = repository.request_department_change("applicant", "核心技术部", now)
    later = now + timedelta(hours=24)
    assert repository.decide_department_requests("eligible", [expired.number], "approved", later)[0].status == "expired"
    assert repository.get_user_profile("applicant").department.name == "未分配部门"


def test_board_member_changes_department_without_creating_an_approval_request(
    repository, session_factory, now
):
    from dzmm_bot.core.schema import DepartmentRequestRecord, RankRecord, UserRecord

    board_member, _ = repository.create_user("board", "董事", now, 0)
    with session_factory.begin() as session:
        board_rank = session.scalar(select(RankRecord).where(RankRecord.is_board.is_(True)))
        board_record = session.get(UserRecord, board_member.id)
        assert board_rank is not None
        assert board_record is not None
        board_record.rank_id = board_rank.id

    result = repository.request_department_change("board", "核心技术部", now)

    assert result.status == "joined"
    assert repository.get_user_profile("board").department.name == "核心技术部"
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(DepartmentRequestRecord)) == 0


def test_board_member_can_list_and_decide_cross_department_requests(
    repository, session_factory, now
):
    from dzmm_bot.core.schema import RankRecord, UserRecord

    repository.create_user("applicant", "小明", now, 0)
    board_member, _ = repository.create_user("board", "董事", now, 0)
    with session_factory.begin() as session:
        board_rank = session.scalar(select(RankRecord).where(RankRecord.is_board.is_(True)))
        board_record = session.get(UserRecord, board_member.id)
        assert board_rank is not None
        assert board_record is not None
        board_record.rank_id = board_rank.id

    request = repository.request_department_change("applicant", "核心技术部", now)
    assert request.status == "requested"

    approvable = repository.list_approvable_department_requests("board", now)
    assert [item.number for item in approvable] == [request.number]
    assert [result.status for result in repository.decide_department_requests(
        "board", [request.number], "approved", now
    )] == ["approved"]
    assert repository.get_user_profile("applicant").department.name == "核心技术部"


def test_existing_board_department_request_is_completed_without_approval(
    repository, session_factory, now
):
    from dzmm_bot.core.schema import RankRecord, UserRecord

    board_member, _ = repository.create_user("board", "董事", now, 0)
    request = repository.request_department_change("board", "核心技术部", now)
    assert request.status == "requested"
    with session_factory.begin() as session:
        board_rank = session.scalar(select(RankRecord).where(RankRecord.is_board.is_(True)))
        board_record = session.get(UserRecord, board_member.id)
        assert board_rank is not None
        assert board_record is not None
        board_record.rank_id = board_rank.id

    assert repository.reconcile_board_department_requests(now) == 1
    assert repository.get_user_profile("board").department.name == "核心技术部"


def test_eligible_approval_charges_once_and_records_audit(repository, session_factory, now):
    from dzmm_bot.core.schema import PromotionApprovalRecord, RankRecord, UserRecord

    applicant, _ = repository.create_user("employee-1", "小明", now, 0)
    approver, _ = repository.create_user("employee-2", "小红", now, 0)
    with session_factory.begin() as session:
        applicant_record = session.get(UserRecord, applicant.id)
        approver_record = session.get(UserRecord, approver.id)
        rank_two = session.scalar(select(RankRecord).where(RankRecord.sort_order == 2))
        assert applicant_record is not None
        assert approver_record is not None
        assert rank_two is not None
        applicant_record.balance = 80
        approver_record.rank_id = rank_two.id

    request = repository.request_promotion("employee-1", now)
    results = repository.decide_promotions("employee-2", [request.number], "approved", now)

    assert [result.status for result in results] == ["approved"]
    assert repository.find_user("employee-1").balance == 0
    assert repository.get_user_profile("employee-1").rank.sort_order == 2
    with session_factory() as session:
        assert session.scalar(select(PromotionApprovalRecord)) is not None


def test_memory_assessment_rejects_whitespace_character_set(repository):
    from dzmm_bot.core.repository import MemoryAssessmentLevelRule

    with pytest.raises(ValueError, match="字符集不能包含空白字符"):
        repository.set_memory_assessment_settings(
            single_daily_limit=1,
            single_recall_seconds=3,
            duel_recall_seconds=3,
            duel_difficulty_level=5,
            duel_base_pool=5,
            duel_wrong_freeze=1,
            duel_wrong_limit=10,
            duel_answer_timeout_minutes=10,
            character_set="Ab 1",
            levels=[
                MemoryAssessmentLevelRule(1, 5, 1),
                MemoryAssessmentLevelRule(2, 7, 2),
                MemoryAssessmentLevelRule(3, 9, 3),
                MemoryAssessmentLevelRule(4, 11, 4),
                MemoryAssessmentLevelRule(5, 13, 5),
            ],
        )


def test_memory_assessment_single_requires_recall_then_cash_out(repository, monkeypatch):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    user, _ = repository.create_user("u1", "小明", now, 0)
    monkeypatch.setattr("dzmm_bot.core.repository.choice", lambda _: "A")

    started = repository.start_memory_assessment_single("u1", now)
    before_recall = repository.answer_memory_assessment("u1", "AAAAA", now)
    repository.mark_memory_assessment_round_recalled(started.round_id, now)
    correct = repository.answer_memory_assessment("u1", "AAAAA", now)
    cashed_out = repository.cash_out_memory_assessment("u1", now)

    assert started.status == "started"
    assert started.level == 1
    assert started.answer == "AAAAA"
    assert before_recall.status == "answer_not_ready"
    assert correct.status == "correct"
    assert cashed_out.status == "cashed_out"
    assert cashed_out.reward == 1
    assert repository.find_user("u1").balance == 1
    assert repository.today_income(user.id, now) == 1
    assert repository.start_memory_assessment_single("u1", now).status == "daily_limit"


def test_memory_assessment_single_continues_and_loses_unclaimed_reward(
    repository, monkeypatch
):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)
    monkeypatch.setattr("dzmm_bot.core.repository.choice", lambda _: "A")

    first_round = repository.start_memory_assessment_single("u1", now)
    repository.mark_memory_assessment_round_recalled(first_round.round_id, now)
    repository.answer_memory_assessment("u1", first_round.answer, now)
    second_round = repository.continue_memory_assessment("u1", now)
    repository.mark_memory_assessment_round_recalled(second_round.round_id, now)
    failed = repository.answer_memory_assessment("u1", "wrong", now)

    assert second_round.status == "continued"
    assert second_round.level == 2
    assert second_round.answer == "AAAAAAA"
    assert failed.status == "failed"
    assert repository.find_user("u1").balance == 0


def test_memory_assessment_duel_freezes_pool_and_awards_first_exact_answer(
    repository, monkeypatch
):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)
    repository.create_user("u2", "小红", now, 0)
    monkeypatch.setattr("dzmm_bot.core.repository.choice", lambda _: "A")

    waiting = repository.start_memory_assessment_duel("u1", now)
    started = repository.join_memory_assessment_duel("u2", now)
    repository.mark_memory_assessment_round_recalled(started.round_id, now)
    won = repository.answer_memory_assessment("u2", started.answer, now)

    assert waiting.status == "waiting_opponent"
    assert started.status == "duel_started"
    assert started.answer == "A" * 13
    assert repository.find_user("u1").balance == -5
    assert won.status == "duel_won"
    assert won.reward == 10
    assert repository.find_user("u2").balance == 5


def test_memory_assessment_duel_with_missing_round_ignores_answers(repository, monkeypatch):
    from dzmm_bot.core.schema import MemoryAssessmentRoundRecord

    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)
    repository.create_user("u2", "小红", now, 0)
    monkeypatch.setattr("dzmm_bot.core.repository.choice", lambda _: "A")

    repository.start_memory_assessment_duel("u1", now)
    repository.join_memory_assessment_duel("u2", now)
    with repository._session() as session:
        session.delete(session.scalar(select(MemoryAssessmentRoundRecord)))

    assert repository.answer_memory_assessment("u1", "AAAAA", now).status == "answer_not_ready"


def test_memory_assessment_duel_surrender_awards_remaining_player(repository, monkeypatch):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)
    repository.create_user("u2", "小红", now, 0)
    monkeypatch.setattr("dzmm_bot.core.repository.choice", lambda _: "A")

    repository.start_memory_assessment_duel("u1", now)
    repository.join_memory_assessment_duel("u2", now)
    surrendered = repository.surrender_memory_assessment_duel("u1", now)

    assert surrendered.status == "duel_won"
    assert surrendered.display_name == "小红"
    assert surrendered.reward == 10
    assert repository.find_user("u1").balance == -5
    assert repository.find_user("u2").balance == 5


def test_memory_assessment_duel_disqualification_keeps_other_player_answering(
    repository, monkeypatch
):
    from dzmm_bot.core.repository import MemoryAssessmentLevelRule

    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)
    repository.create_user("u2", "小红", now, 0)
    repository.set_memory_assessment_settings(
        single_daily_limit=1,
        single_recall_seconds=3,
        duel_recall_seconds=3,
        duel_difficulty_level=5,
        duel_base_pool=5,
        duel_wrong_freeze=1,
        duel_wrong_limit=1,
        duel_answer_timeout_minutes=10,
        character_set="ABC123",
        levels=[MemoryAssessmentLevelRule(level, level * 2 + 3, level) for level in range(1, 6)],
    )
    monkeypatch.setattr("dzmm_bot.core.repository.choice", lambda _: "A")

    repository.start_memory_assessment_duel("u1", now)
    started = repository.join_memory_assessment_duel("u2", now)
    repository.mark_memory_assessment_round_recalled(started.round_id, now)

    disqualified = repository.answer_memory_assessment("u1", "wrong", now)
    won = repository.answer_memory_assessment("u2", started.answer, now)

    assert disqualified.status == "duel_disqualified"
    assert won.status == "duel_won"
    assert won.display_name == "小红"


def test_memory_assessment_duel_timeout_collects_the_pool(repository, monkeypatch):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)
    repository.create_user("u2", "小红", now, 0)
    monkeypatch.setattr("dzmm_bot.core.repository.choice", lambda _: "A")

    repository.start_memory_assessment_duel("u1", now)
    repository.join_memory_assessment_duel("u2", now)
    expired = repository.expire_memory_assessment_duels(now + timedelta(minutes=10))

    assert [result.status for result in expired] == ["duel_collected"]
    assert repository.find_user("u1").balance == -5
    assert repository.find_user("u2").balance == -5


@pytest.mark.parametrize("state", ["signup", "in_progress"])
def test_memory_assessment_cannot_start_during_active_random_event(repository, state):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)
    repository.create_user("u2", "小红", now, 0)
    repository.create_random_event_scene("茶水间", "报名", ["开场"], 1, 1, [("员工", 1)])
    repository.set_random_event_settings(["10:00"], "可选身份：{可选身份}", 15, 5)
    repository.schedule_random_events(now)
    repository.run_random_event_jobs(now)
    if state == "in_progress":
        assert repository.join_random_event("u2", "员工", now) == "started"

    assert repository.start_memory_assessment_single("u1", now).status == "random_event_active"
    assert repository.start_memory_assessment_duel("u1", now).status == "random_event_active"


def test_random_event_waits_while_memory_assessment_duel_is_active(repository):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)
    repository.create_user("u2", "小红", now, 0)
    repository.create_user("u3", "小李", now, 0)
    waiting = repository.start_memory_assessment_duel("u1", now)
    repository.create_random_event_scene("茶水间", "报名", ["开场"], 1, 2, [("员工", 2)])
    repository.set_random_event_settings(["10:00"], "可选身份：{可选身份}", 15, 5)
    repository.schedule_random_events(now)
    repository.run_random_event_jobs(now)
    assert waiting.status == "waiting_opponent"
    assert repository.active_random_event_state() is None
    assert repository.list_today_random_event_schedules(now)[0].status == "pending"
    assert repository.join_memory_assessment_duel("u2", now).status == "duel_started"


def test_due_outbound_recall_marks_memory_assessment_round_ready(repository, now):
    from dzmm_bot.core.schema import MemoryAssessmentRoundRecord

    repository.create_user("u1", "小明", now, 0)
    started = repository.start_memory_assessment_single("u1", now)
    outbound = repository.enqueue_system_outbound(
        "考题", recall_after_seconds=3, memory_round_id=started.round_id
    )
    sent = repository.claim_outbound("worker-a", now, 30)

    assert repository.confirm_sent(
        outbound.id, "worker-a", sent.lease_token, "platform-answer", now
    )
    assert repository.claim_outbound_recall("worker-a", now + timedelta(seconds=2), 30) is None
    recall = repository.claim_outbound_recall("worker-a", now + timedelta(seconds=3), 30)
    assert recall.platform_sent_id == "platform-answer"
    assert repository.confirm_outbound_recalled(
        outbound.id, "worker-a", recall.recall_lease_token, now + timedelta(seconds=3)
    )
    with repository._session() as session:
        assert session.get(MemoryAssessmentRoundRecord, started.round_id).state == "awaiting_answer"


def test_hide_and_seek_scene_name_must_be_unique(repository):
    repository.get_hide_and_seek_settings()

    with pytest.raises(ValueError, match="地点名称已存在"):
        repository.create_hide_and_seek_scene("茶水间")


def test_hide_and_seek_rewards_unpatrolled_scene_without_opening_charge(repository, monkeypatch):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    user, _ = repository.create_user("u1", "小明", now, 0)
    monkeypatch.setattr("dzmm_bot.core.repository.randbelow", lambda _: 0)

    started = repository.start_hide_and_seek("u1", now)
    assert repository.find_user("u1").balance == 0
    finished = repository.choose_hide_and_seek("u1", 7, now)

    assert started.status == "started"
    assert len(started.candidates) == 7
    assert finished.status == "won"
    assert finished.patrol_numbers == (1, 2, 3, 4, 5)
    assert repository.find_user("u1").balance == 3
    assert repository.today_income(user.id, now) == 3


def test_hide_and_seek_found_charges_frozen_penalty(repository, monkeypatch):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)
    monkeypatch.setattr("dzmm_bot.core.repository.randbelow", lambda _: 0)

    started = repository.start_hide_and_seek("u1", now)
    assert repository.find_user("u1").balance == 0
    finished = repository.choose_hide_and_seek("u1", 1, now)

    assert finished.status == "found"
    assert finished.entry_fee == started.entry_fee == 1
    assert finished.patrol_numbers == (1, 2, 3)
    assert repository.find_user("u1").balance == -1


def test_hide_and_seek_runs_second_patrol_when_first_round_misses(repository, monkeypatch):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)
    monkeypatch.setattr("dzmm_bot.core.repository.randbelow", lambda _: 0)

    repository.start_hide_and_seek("u1", now)
    finished = repository.choose_hide_and_seek("u1", 4, now)

    assert finished.status == "found"
    assert finished.patrol_numbers == (1, 2, 3, 4, 5)
    assert len(set(finished.patrol_numbers)) == 5


def test_hide_and_seek_timeout_returns_daily_play_without_balance_change(repository):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)
    repository.start_hide_and_seek("u1", now)

    cancelled = repository.expire_hide_and_seek_games(now + timedelta(minutes=2))
    restarted = repository.start_hide_and_seek("u1", now + timedelta(minutes=2, seconds=1))

    assert [game.status for game in cancelled] == ["cancelled"]
    assert repository.find_user("u1").balance == 0
    assert restarted.status == "started"
    assert repository.expire_hide_and_seek_games(now + timedelta(minutes=3)) == []


def test_daily_jobs_enqueue_one_hide_and_seek_cancellation_message(
    repository, session_factory
):
    from dzmm_bot.core.schema import OutboundRecord

    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)
    repository.start_hide_and_seek("u1", now)

    repository.run_daily_jobs(now + timedelta(minutes=2))
    repository.run_daily_jobs(now + timedelta(minutes=3))

    with session_factory() as session:
        texts = list(session.scalars(select(OutboundRecord.text)))
    assert sum("躲猫猫" in text and "已取消" in text for text in texts) == 1


def test_hide_and_seek_limits_active_game_and_invalid_scene(repository):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)

    assert repository.start_hide_and_seek("u1", now).status == "started"
    assert repository.start_hide_and_seek("u1", now).status == "already_active"
    assert repository.choose_hide_and_seek("u1", 8, now).status == "invalid_scene"
    assert repository.find_user("u1").balance == 0


def test_hide_and_seek_daily_limit_is_beijing_scoped(repository):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)

    repository.start_hide_and_seek("u1", now)
    repository.choose_hide_and_seek("u1", 1, now)
    repository.start_hide_and_seek("u1", now)
    repository.choose_hide_and_seek("u1", 1, now)

    assert repository.start_hide_and_seek("u1", now).status == "daily_limit"


@pytest.mark.parametrize("state", ["signup", "in_progress"])
def test_hide_and_seek_cannot_start_during_active_random_event(repository, state):
    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_user("u1", "小明", now, 0)
    repository.create_random_event_scene("茶水间", "报名", ["开场"], 1, 1, [("员工", 1)])
    repository.set_random_event_settings(["10:00"], "可选身份：{可选身份}", 15, 5)
    repository.schedule_random_events(now)
    repository.run_random_event_jobs(now)
    if state == "in_progress":
        repository.create_user("u2", "小红", now, 0)
        assert repository.join_random_event("u2", "员工", now) == "started"

    assert repository.start_hide_and_seek("u1", now).status == "random_event_active"


def test_random_event_settings_reject_duplicate_fixed_times(repository):
    with pytest.raises(ValueError, match="固定场次"):
        repository.set_random_event_settings(
            ["10:00", "10:00"], "{可选身份}", 15, 5
        )


def test_random_event_schedule_uses_fixed_times(repository):
    from dzmm_bot.core.schema import BEIJING

    now = datetime(2026, 8, 6, 0, 0, tzinfo=BEIJING)
    repository.set_random_event_settings(["10:00", "14:00", "20:00"], "{可选身份}", 15, 5)

    schedules = repository.schedule_random_events(now)

    assert [schedule.scheduled_at.strftime("%H:%M") for schedule in schedules] == [
        "10:00",
        "14:00",
        "20:00",
    ]


def test_fixed_schedule_skips_times_missed_before_first_daily_run(repository):
    from dzmm_bot.core.schema import BEIJING

    now = datetime(2026, 8, 6, 12, 0, tzinfo=BEIJING)
    repository.set_random_event_settings(["10:00", "14:00"], "{可选身份}", 15, 5)

    schedules = repository.schedule_random_events(now)

    assert [schedule.status for schedule in schedules] == ["skipped", "pending"]


def test_today_random_event_can_be_added_and_pending_event_removed(repository):
    from dzmm_bot.core.schema import BEIJING

    now = datetime(2026, 8, 6, 12, 0, tzinfo=BEIJING)
    scene = repository.create_random_event_scene(
        "茶水间",
        "报名公告。",
        [{"name": "咖啡事故", "opening_text": "咖啡洒了。"}],
        3,
        10,
        [("主持", 1), ("员工", 2)],
    )

    schedule = repository.create_today_random_event(
        scene.id, "咖啡事故", datetime(2026, 8, 6, 14, 0, tzinfo=BEIJING), now
    )

    assert schedule.scene_name == "茶水间"
    assert schedule.event_name == "咖啡事故"
    assert repository.delete_today_random_event(schedule.id, now) is True
    assert repository.list_today_random_event_schedules(now) == []


def test_random_event_scene_returns_named_event_templates(repository):
    scene = repository.create_random_event_scene(
        "茶水间",
        "报名",
        [{"name": "咖啡事故", "opening_text": "{主持}打翻咖啡。"}],
        3,
        10,
        [("主持", 1)],
    )

    assert scene.events[0].name == "咖啡事故"
    assert scene.events[0].opening_text == "{主持}打翻咖啡。"


def test_random_event_lifecycle_rewards_only_completed_participant(
    repository, session_factory
):
    from dzmm_bot.core.schema import BEIJING, OutboundRecord, UserRecord

    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_random_event_scene(
        "午休室",
        "午休铃响了，大家各就各位。",
        ["午休铃响了，大家各就各位。"],
        3,
        2,
        [("员工", 2)],
    )
    repository.set_random_event_settings(["10:00"], "{可选身份}", 15, 5)
    first, _ = repository.create_user("u1", "小明", now, 0)
    second, _ = repository.create_user("u2", "小红", now, 0)

    repository.schedule_random_events(now)
    repository.run_random_event_jobs(now)

    assert repository.join_random_event("u1", "员工", now) == "joined"
    assert repository.join_random_event("u2", "员工", now) == "started"
    repository.record_random_event_round("u1", now, "第一轮")
    repository.record_random_event_round("u1", now, "第二轮")

    assert repository.leave_random_event("u1", now) == "rewarded"
    assert repository.leave_random_event("u2", now) == "left_without_reward"

    with session_factory() as session:
        assert session.get(UserRecord, first.id).balance == 3
        assert session.get(UserRecord, second.id).balance == 0
        assert session.scalars(select(OutboundRecord)).first() is not None


def test_full_random_event_sends_a_frozen_formal_opening(
    repository, session_factory
):
    from dzmm_bot.core.schema import (
        BEIJING,
        OutboundRecord,
        RandomEventRecord,
    )

    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_random_event_scene(
        "茶水间",
        "今天的公司茶水间随机事件来啦，快点加入吧。",
        ["咖啡洒了一桌，主持人正在组织抢救。"],
        3,
        1,
        [("主持", 1), ("员工", 1)],
    )
    repository.set_random_event_settings(["10:00"], "{可选身份}", 15, 5)
    repository.create_user("u1", "小明", now, 0)
    repository.create_user("u2", "小红", now, 0)
    repository.schedule_random_events(now)
    repository.run_random_event_jobs(now)

    assert repository.join_random_event("u1", "主持", now) == "joined"
    assert repository.join_random_event("u2", "员工", now) == "started"

    with session_factory() as session:
        event = session.scalar(select(RandomEventRecord))
        latest_outbound = session.scalar(
            select(OutboundRecord).order_by(OutboundRecord.created_at.desc())
        )

    assert event.formal_opening_text == "咖啡洒了一桌，主持人正在组织抢救。"
    assert latest_outbound.text.endswith("咖啡洒了一桌，主持人正在组织抢救。")


def test_full_random_event_renders_role_variables(repository, session_factory):
    from dzmm_bot.core.schema import BEIJING, RandomEventRecord

    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_random_event_scene(
        "茶水间",
        "今天的公司茶水间随机事件来啦，快点加入吧。",
        ["{主持}端着咖啡走进茶水间，对{员工}说开始。"],
        3,
        1,
        [("主持", 1), ("员工", 2)],
    )
    repository.set_random_event_settings(["10:00"], "{可选身份}", 15, 5)
    repository.create_user("u1", "小明", now, 0)
    repository.create_user("u2", "小红", now, 0)
    repository.create_user("u3", "小李", now, 0)
    repository.schedule_random_events(now)
    repository.run_random_event_jobs(now)

    assert repository.join_random_event("u1", "主持", now) == "joined"
    assert repository.join_random_event("u2", "员工", now + timedelta(seconds=1)) == "joined"
    assert repository.join_random_event("u3", "员工", now + timedelta(seconds=2)) == "started"

    with session_factory() as session:
        event = session.scalar(select(RandomEventRecord))

    assert event.formal_opening_text == "小明端着咖啡走进茶水间，对小红、小李说开始。"


def test_random_event_records_participant_details_and_can_trigger(repository):
    from dzmm_bot.core.schema import BEIJING

    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_random_event_scene(
        "茶水间", "报名", [{"name": "咖啡事故", "opening_text": "开始。"}], 1, 1, [("员工", 1)]
    )
    repository.set_random_event_settings(["10:00"], "{可选身份}", 15, 5)
    repository.create_user("u1", "小明", now, 0)
    schedule = repository.schedule_random_events(now)[0]

    assert repository.trigger_random_event(schedule.id, now).status == "signup"
    assert repository.join_random_event("u1", "员工", now) == "started"
    assert repository.record_random_event_round("u1", now, "开始收拾") == "participant"
    assert repository.record_random_event_round("observer", now, "（路过）") == "observer_valid"
    assert repository.list_random_event_details(schedule.id) == [("小明", "开始收拾", now)]


def test_scene_rejects_unknown_formal_opening_role(repository):
    with pytest.raises(ValueError, match="不存在的角色变量"):
        repository.create_random_event_scene(
            "茶水间", "快点加入吧。", ["{未知}来了。"], 1, 1, [("主持", 1)]
        )


def test_in_progress_random_event_classifies_observer_parentheses(repository):
    from dzmm_bot.core.schema import BEIJING

    now = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_random_event_scene(
        "茶水间", "快点加入吧。", ["正式开始。"], 1, 1, [("员工", 1)]
    )
    repository.set_random_event_settings(["10:00"], "{可选身份}", 15, 5)
    repository.create_user("player", "小明", now, 0)
    repository.schedule_random_events(now)
    repository.run_random_event_jobs(now)
    assert repository.join_random_event("player", "员工", now) == "started"

    assert (
        repository.classify_random_event_message("observer", " （ 你好，你们在干什么 ） ")
        == "observer_valid"
    )
    assert (
        repository.classify_random_event_message("observer", "( 你好，你们在干什么 )")
        == "observer_valid"
    )
    assert (
        repository.classify_random_event_message("observer", "你好，你们在干什么")
        == "observer_invalid"
    )


def test_cross_day_active_random_event_skips_next_days_due_schedule(repository):
    from dzmm_bot.core.schema import BEIJING

    first_day = datetime(2026, 8, 6, 10, 0, tzinfo=BEIJING)
    repository.create_random_event_scene(
        "会议室", "会议还没结束。", ["会议还没结束。"], 1, 10, [("主持", 1)]
    )
    repository.set_random_event_settings(["10:00"], "{可选身份}", 15, 5)
    repository.create_user("u1", "小明", first_day, 0)
    repository.schedule_random_events(first_day)
    repository.run_random_event_jobs(first_day)
    assert repository.join_random_event("u1", "主持", first_day) == "started"

    second_day = first_day + timedelta(days=1)
    repository.schedule_random_events(second_day)
    repository.run_random_event_jobs(second_day)

    schedules = repository.list_today_random_event_schedules(second_day)
    assert [event.status for event in schedules] == ["in_progress", "skipped"]
    assert schedules[0].is_cross_day is True


def test_random_event_scene_can_be_updated_and_deleted(repository):
    scene = repository.create_random_event_scene(
        "旧会议室", "旧报名公告。", ["旧正式开场。"], 1, 1, [("员工", 1)]
    )

    updated = repository.update_random_event_scene(
        scene.id,
        "新会议室",
        "新报名公告。",
        ["新正式开场。"],
        2,
        3,
        [("主持", 1), ("员工", 2)],
        False,
    )

    assert updated.name == "新会议室"
    assert updated.signup_text == "新报名公告。"
    assert updated.openings == ["新正式开场。"]
    assert updated.enabled is False
    assert [(seat.role, seat.capacity) for seat in updated.seats] == [
        ("主持", 1),
        ("员工", 2),
    ]
    assert repository.delete_random_event_scene(scene.id) is True
    assert repository.list_random_event_scenes() == []


def test_expired_lease_can_be_claimed_once_by_another_worker(
    repository, inbound, now
):
    stored, _ = repository.accept_inbound(inbound)
    outbound = repository.enqueue_outbound(stored.id, "reply")

    assert repository.claim_outbound("a", now, 30).id == outbound.id
    assert (
        repository.claim_outbound("b", now + timedelta(seconds=31), 30).id
        == outbound.id
    )
    assert repository.claim_outbound("c", now + timedelta(seconds=32), 30) is None


def test_outbound_replies_for_one_inbound_are_claimed_in_reply_order(
    repository, inbound, now
):
    stored, _ = repository.accept_inbound(inbound)
    first = repository.enqueue_outbound(stored.id, "第一轮巡查", 0)
    second = repository.enqueue_outbound(stored.id, "第二轮巡查", 1)

    claimed_first = repository.claim_outbound("worker-a", now, 30)
    assert claimed_first.id == first.id
    assert repository.confirm_sent(
        first.id, "worker-a", claimed_first.lease_token, "sent-1", now
    )

    claimed_second = repository.claim_outbound("worker-a", now, 30)
    assert claimed_second.id == second.id


def test_outbound_reply_preserves_message_below_platform_limits(
    repository, session_factory, inbound
):
    from dzmm_bot.core.schema import OutboundRecord

    stored, _ = repository.accept_inbound(inbound)
    text = "\n".join([f"第{index}行" for index in range(1, 8)])
    repository.enqueue_outbound(stored.id, text)

    with session_factory() as session:
        records = list(
            session.scalars(
                select(OutboundRecord)
                .order_by(OutboundRecord.reply_index, OutboundRecord.created_at)
            )
        )
    assert [record.text for record in records] == [text]
    assert [record.reply_index for record in records] == [0]


def test_system_outbound_splits_a_line_over_one_thousand_characters(
    repository, session_factory
):
    from dzmm_bot.core.schema import OutboundRecord

    repository.enqueue_system_outbound("字" * 1001)

    with session_factory() as session:
        records = list(
            session.scalars(
                select(OutboundRecord)
                .order_by(OutboundRecord.reply_index, OutboundRecord.created_at)
            )
        )
    assert [record.text for record in records] == ["字" * 1000, "字"]


def test_system_outbound_splits_after_ten_newlines(repository, session_factory):
    from dzmm_bot.core.schema import OutboundRecord

    text = "\n".join(f"第{index}行" for index in range(1, 13))
    repository.enqueue_system_outbound(text)

    with session_factory() as session:
        records = list(
            session.scalars(
                select(OutboundRecord).order_by(OutboundRecord.reply_index)
            )
        )
    assert [record.text for record in records] == [
        "\n".join(f"第{index}行" for index in range(1, 12)),
        "第12行",
    ]


def test_system_outbound_keeps_exactly_ten_newlines_in_one_message(
    repository, session_factory
):
    from dzmm_bot.core.schema import OutboundRecord

    text = "\n".join(f"第{index}行" for index in range(1, 12))
    repository.enqueue_system_outbound(text)

    with session_factory() as session:
        records = list(session.scalars(select(OutboundRecord)))
    assert [record.text for record in records] == [text]


def test_second_reply_waits_until_the_first_reply_is_sent(repository, inbound, now):
    stored, _ = repository.accept_inbound(inbound)
    first = repository.enqueue_outbound(stored.id, "第一轮巡查", 0)
    second = repository.enqueue_outbound(stored.id, "第二轮巡查", 1)

    claimed_first = repository.claim_outbound("worker-a", now, 30)
    assert claimed_first.id == first.id
    assert repository.claim_outbound("worker-b", now, 30) is None

    assert repository.confirm_sent(
        first.id, "worker-a", claimed_first.lease_token, "sent-1", now
    )
    assert repository.claim_outbound("worker-b", now, 30).id == second.id


def test_confirmed_outbound_is_not_claimed_again(
    repository, session_factory, inbound, now
):
    from dzmm_bot.core.schema import OutboundRecord

    stored, _ = repository.accept_inbound(inbound)
    outbound = repository.enqueue_outbound(stored.id, "reply")
    claimed = repository.claim_outbound("worker-a", now, 30)

    confirmed = repository.confirm_sent(
        outbound.id, "worker-a", claimed.lease_token, "sent-1", now
    )

    assert confirmed is True
    with session_factory() as session:
        persisted = session.get(OutboundRecord, outbound.id)
        assert persisted.status == "sent"
        assert persisted.platform_sent_id == "sent-1"
    assert repository.claim_outbound("worker-b", now + timedelta(seconds=31), 30) is None


def test_failed_outbound_is_not_claimed_again(repository, session_factory, inbound, now):
    from dzmm_bot.core.schema import OutboundRecord

    stored, _ = repository.accept_inbound(inbound)
    outbound = repository.enqueue_outbound(stored.id, "reply")
    claimed = repository.claim_outbound("worker-a", now, 30)

    assert repository.mark_outbound_failed(
        outbound.id, "worker-a", claimed.lease_token, now
    )
    with session_factory() as session:
        persisted = session.get(OutboundRecord, outbound.id)
        assert persisted.status == "failed"
        assert persisted.lease_worker_id is None
        assert persisted.lease_token is None
    assert repository.claim_outbound("worker-b", now + timedelta(seconds=31), 30) is None


def test_stale_outbound_confirmation_is_rejected_after_reclaim(
    repository, session_factory, inbound, now
):
    from dzmm_bot.core.schema import OutboundRecord

    stored, _ = repository.accept_inbound(inbound)
    outbound = repository.enqueue_outbound(stored.id, "reply")
    first = repository.claim_outbound("worker-a", now, 30)
    second = repository.claim_outbound("worker-b", now + timedelta(seconds=31), 30)

    assert second.lease_token != first.lease_token
    assert (
        repository.confirm_sent(
            outbound.id,
            "worker-a",
            first.lease_token,
            "sent-by-a",
            now + timedelta(seconds=31),
        )
        is False
    )
    assert (
        repository.confirm_sent(
            outbound.id,
            "worker-b",
            second.lease_token,
            "sent-by-b",
            now + timedelta(seconds=32),
        )
        is True
    )
    with session_factory() as session:
        persisted = session.get(OutboundRecord, outbound.id)
        assert persisted.platform_sent_id == "sent-by-b"


def test_outbound_confirmation_requires_owner_token_and_live_lease(
    repository, inbound, now
):
    stored, _ = repository.accept_inbound(inbound)
    outbound = repository.enqueue_outbound(stored.id, "reply")
    claimed = repository.claim_outbound("worker-a", now, 30)

    assert (
        repository.confirm_sent(
            outbound.id, "worker-b", claimed.lease_token, "sent-1", now
        )
        is False
    )
    assert (
        repository.confirm_sent(
            outbound.id, "worker-a", uuid4(), "sent-1", now
        )
        is False
    )
    assert (
        repository.confirm_sent(
            outbound.id,
            "worker-a",
            claimed.lease_token,
            "sent-1",
            now + timedelta(seconds=30),
        )
        is False
    )


def test_worker_command_is_claimed_once_then_acknowledged(repository, now):
    command = repository.enqueue_worker_command("start_auth")
    claimed = repository.claim_worker_command("worker-a", now, 30)
    completed = repository.complete_worker_command(
        claimed.id, "worker-a", claimed.lease_token, "succeeded", now
    )

    assert claimed.id == command.id
    assert completed is True
    assert repository.claim_worker_command("worker-b", now + timedelta(seconds=31), 30) is None


def test_stale_worker_command_completion_is_rejected_after_reclaim(repository, now):
    command = repository.enqueue_worker_command("start_auth")
    first = repository.claim_worker_command("worker-a", now, 30)
    second = repository.claim_worker_command(
        "worker-b", now + timedelta(seconds=31), 30
    )

    assert second.lease_token != first.lease_token
    assert (
        repository.complete_worker_command(
            command.id,
            "worker-a",
            first.lease_token,
            "succeeded",
            now + timedelta(seconds=31),
        )
        is False
    )
    assert (
        repository.complete_worker_command(
            command.id,
            "worker-b",
            second.lease_token,
            "succeeded",
            now + timedelta(seconds=32),
        )
        is True
    )


def test_worker_command_completion_requires_owner_token_and_live_lease(
    repository, now
):
    command = repository.enqueue_worker_command("start_auth")
    claimed = repository.claim_worker_command("worker-a", now, 30)

    assert (
        repository.complete_worker_command(
            command.id, "worker-b", claimed.lease_token, "succeeded", now
        )
        is False
    )
    assert (
        repository.complete_worker_command(
            command.id, "worker-a", uuid4(), "succeeded", now
        )
        is False
    )
    assert (
        repository.complete_worker_command(
            command.id,
            "worker-a",
            claimed.lease_token,
            "succeeded",
            now + timedelta(seconds=30),
        )
        is False
    )


def test_worker_heartbeat_is_persisted(repository, now):
    heartbeat = WorkerHeartbeat("worker-a", LoginState.READY, now, listening=True)

    first = repository.record_worker_heartbeat(heartbeat)
    repository.enqueue_worker_command("pause_listening")
    second = repository.record_worker_heartbeat(
        WorkerHeartbeat(
            "worker-a",
            LoginState.AUTH_REQUIRED,
            now + timedelta(seconds=5),
            listening=False,
        )
    )

    assert second.id == first.id
    assert second.login_state == LoginState.AUTH_REQUIRED.value
    assert second.listening is False
    assert second.listening_desired is False
    assert second.recorded_at == now + timedelta(seconds=5)


def test_resume_listener_command_persists_enabled_choice(repository, now):
    repository.record_worker_heartbeat(
        WorkerHeartbeat("worker-a", LoginState.READY, now, listening=False)
    )
    repository.enqueue_worker_command("pause_listening")

    repository.enqueue_worker_command("resume_listening")
    updated = repository.record_worker_heartbeat(
        WorkerHeartbeat(
            "worker-a",
            LoginState.READY,
            now + timedelta(seconds=5),
            listening=True,
        )
    )

    assert updated.listening is True
    assert updated.listening_desired is True


def test_reply_template_defaults_seed_once_and_preserve_an_edit(repository):
    """Fails if a later default seed overwrites an administrator's template."""
    repository.ensure_reply_templates()
    repository.set_reply_template("/余额", "shown", "{昵称} 有 {余额} 币。")
    repository.ensure_reply_templates()

    assert (
        repository.get_reply_template("/余额", "shown").template
        == "{昵称} 有 {余额} 币。"
    )


def test_game_settings_default_to_the_initial_economy(repository):
    settings = repository.get_game_settings()

    assert (
        settings.currency_name,
        settings.onboarding_bonus,
        settings.checkin_reward,
        settings.weekly_attendance_reward,
    ) == (
        "摸鱼币",
        0,
        5,
        5,
    )


def test_weekly_attendance_rewards_a_complete_previous_beijing_week_once(
    repository, session_factory
):
    from dzmm_bot.core.schema import BEIJING, BalanceTransactionRecord

    monday = datetime(2026, 8, 10, 0, 0, tzinfo=BEIJING)
    user, _ = repository.create_user(
        "u1", "小明", monday - timedelta(days=8), 0
    )
    for offset in range(7, 0, -1):
        repository.check_in(user, monday - timedelta(days=offset), 0)

    repository.run_daily_jobs(monday)
    repository.run_daily_jobs(monday + timedelta(minutes=1))

    assert repository.find_user("u1").balance == 5
    with session_factory() as session:
        rewards = list(
            session.scalars(
                select(BalanceTransactionRecord).where(
                    BalanceTransactionRecord.user_id == user.id,
                    BalanceTransactionRecord.source == "weekly_attendance",
                )
            )
        )
    assert [reward.amount for reward in rewards] == [5]


def test_weekly_attendance_requires_every_day_of_the_previous_beijing_week(repository):
    from dzmm_bot.core.schema import BEIJING

    monday = datetime(2026, 8, 10, 0, 0, tzinfo=BEIJING)
    user, _ = repository.create_user(
        "u1", "小明", monday - timedelta(days=8), 0
    )
    for offset in (7, 6, 5, 4, 2, 1):
        repository.check_in(user, monday - timedelta(days=offset), 0)

    repository.run_daily_jobs(monday)

    assert repository.find_user("u1").balance == 0


def test_consecutive_checkins_count_from_today_or_yesterday(repository):
    from dzmm_bot.core.schema import BEIJING

    now = datetime(2026, 8, 6, 12, 0, tzinfo=BEIJING)
    user, _ = repository.create_user("u1", "小明", now - timedelta(days=3), 0)
    repository.check_in(user, now - timedelta(days=2), 0)
    repository.check_in(user, now - timedelta(days=1), 0)

    assert repository.consecutive_checkin_days(user.id, now) == 2

    repository.check_in(user, now, 0)

    assert repository.consecutive_checkin_days(user.id, now) == 3


def test_activity_settings_default_to_the_initial_rules(repository):
    settings = repository.get_activity_settings()

    assert settings.report_times == ["12:00", "16:00", "20:00", "23:59"]
    assert [
        (rule.level, rule.character_threshold, rule.reward) for rule in settings.rules
    ] == [
        (1, 10, 1),
        (2, 25, 2),
        (3, 60, 3),
        (4, 90, 4),
        (5, 140, 5),
        (6, 190, 6),
        (7, 250, 7),
        (8, 330, 8),
        (9, 410, 9),
        (10, 500, 10),
    ]


def test_system_outbound_can_be_claimed(repository, now):
    outbound = repository.enqueue_system_outbound("系统推送")
    claimed = repository.claim_outbound("worker-a", now, 30)

    assert claimed.id == outbound.id
    assert claimed.inbound_message_id is None


def test_activity_counts_joined_non_command_text_without_whitespace(repository, now):
    repository.create_user("u1", "小明", now, 0)

    repository.record_activity("u1", now, "你 好\n！")
    repository.record_activity("u1", now, "/我")
    repository.record_activity("unknown", now, "一二三四五六七八九十")
    repository.record_activity("u1", now, "甲乙丙丁戊己庚")

    assert repository.personal_activity("u1", now).level == 1


def test_user_page_returns_newest_records_and_total(repository, now):
    for index in range(21):
        repository.create_user(
            f"u-{index}", f"员工{index}", now + timedelta(minutes=index), 0
        )

    users, total = repository.list_users_page(1, 20)
    final_page, final_total = repository.list_users_page(2, 20)

    assert total == 21
    assert [user.display_name for user in users] == [
        f"员工{index}" for index in range(20, 0, -1)
    ]
    assert final_total == 21
    assert [user.display_name for user in final_page] == ["员工0"]


def test_item_page_returns_newest_records_and_total(repository, session_factory, now):
    from dzmm_bot.core.schema import ItemRecord

    with session_factory.begin() as session:
        for index in range(21):
            session.add(
                ItemRecord(
                    name=f"物品{index}",
                    description="说明",
                    price=index,
                    stock=1,
                    enabled=True,
                    created_at=now + timedelta(minutes=index),
                )
            )

    items, total = repository.list_active_items_page(2, 20)

    assert total == 21
    assert [item.name for item in items] == ["物品0"]


def test_daily_jobs_backfill_current_day_history_and_legacy_checkin_income(
    repository, session_factory
):
    from dzmm_bot.core.schema import BEIJING, DailyCheckinRecord, UserRecord

    joined_at = datetime(2026, 8, 5, 9, 0, tzinfo=BEIJING)
    checkin_at = datetime(2026, 8, 5, 10, 0, tzinfo=BEIJING)
    now = datetime(2026, 8, 5, 19, 45, tzinfo=BEIJING)
    user, _ = repository.create_user("u1", "小明", joined_at, 0)
    repository.accept_inbound(
        InboundMessage("historic-text", "u1", "一二三四五六七八九十", checkin_at)
    )
    with session_factory.begin() as session:
        session.get(UserRecord, user.id).balance = 5
        session.add(
            DailyCheckinRecord(
                id=uuid4(),
                user_id=user.id,
                checkin_date=checkin_at.date(),
                checked_in_at=checkin_at,
            )
        )

    repository.run_daily_jobs(now)

    assert repository.personal_activity("u1", now).level == 1
    assert repository.today_income(user.id, now) == 5
    repository.run_daily_jobs(now + timedelta(minutes=1))
    assert repository.find_user("u1").balance == 5
    assert repository.today_income(user.id, now) == 5


def test_activity_settings_reject_non_increasing_thresholds(repository):
    from dzmm_bot.core.repository import ActivityLevelRule

    with pytest.raises(ValueError, match="门槛"):
        repository.set_activity_settings(
            [ActivityLevelRule(level, 10, level) for level in range(1, 11)],
            ["12:00"],
        )


def test_activity_settlement_is_once_and_negative_does_not_reduce_today_income(
    repository,
):
    from dzmm_bot.core.schema import BEIJING

    yesterday = datetime(2026, 8, 5, 23, 59, tzinfo=BEIJING)
    today = datetime(2026, 8, 6, 0, 0, tzinfo=BEIJING)
    user, _ = repository.create_user("u1", "小明", yesterday, 0)
    repository.record_activity("u1", yesterday, "一二三四五六七八九十")

    repository.run_daily_jobs(today)
    repository.record_balance_change(
        user.id, -4, "penalty", datetime(2026, 8, 6, 1, 0, tzinfo=BEIJING)
    )

    assert repository.find_user("u1").balance == -3
    assert repository.today_income(
        user.id, datetime(2026, 8, 6, 2, 0, tzinfo=BEIJING)
    ) == 1
    repository.run_daily_jobs(today + timedelta(minutes=1))
    assert repository.find_user("u1").balance == -3


def test_due_income_report_is_queued_once_and_empty_slot_is_skipped(repository, now):
    from dzmm_bot.core.schema import BEIJING

    repository.run_daily_jobs(datetime(2026, 8, 5, 12, 0, tzinfo=BEIJING))
    assert repository.claim_outbound("worker-a", now, 30) is None

    repository.create_user(
        "u1", "小明", datetime(2026, 8, 5, 13, 0, tzinfo=BEIJING), 3
    )
    repository.run_daily_jobs(datetime(2026, 8, 5, 16, 0, tzinfo=BEIJING))

    assert repository.claim_outbound("worker-a", now, 30).text.startswith("今日收益榜")
    repository.run_daily_jobs(datetime(2026, 8, 5, 16, 1, tzinfo=BEIJING))
    assert repository.claim_outbound("worker-b", now, 30) is None


@pytest.mark.parametrize(
    "currency_name,onboarding_bonus,checkin_reward,weekly_attendance_reward",
    [
        ("", 0, 5, 5),
        (" " * 13, 0, 5, 5),
        ("工分", -1, 5, 5),
        ("工分", 0, 1000, 5),
        ("工分", 0, 5, 1000),
    ],
)
def test_game_settings_reject_invalid_values(
    repository, currency_name, onboarding_bonus, checkin_reward, weekly_attendance_reward
):
    with pytest.raises(ValueError):
        repository.set_game_settings(
            currency_name, onboarding_bonus, checkin_reward, weekly_attendance_reward
        )


def test_template_validation_rejects_a_variable_unavailable_to_its_scenario():
    """Fails if a shop-only variable can leak into a balance reply."""
    from dzmm_bot.core.reply_templates import validate_template

    with pytest.raises(ValueError, match="不支持"):
        validate_template("/余额", "shown", "{商店列表}")


def test_manual_login_lease_is_exclusive_and_expires(repository):
    from dzmm_bot.core.repository import ManualLoginBusyError
    from dzmm_bot.core.schema import BEIJING

    now = datetime(2026, 8, 5, 12, tzinfo=BEIJING)
    lease = repository.start_manual_login("alice-id", "alice", now)

    assert lease.operator_name == "alice"
    with pytest.raises(ManualLoginBusyError):
        repository.start_manual_login("bob-id", "bob", now)

    start = repository.claim_worker_command("worker", now, 30)
    assert start.command == "start_auth"
    assert repository.complete_worker_command(
        start.id, "worker", start.lease_token, "completed", now
    )
    assert repository.manual_login_lease(now + timedelta(seconds=181)) is None
    command = repository.claim_worker_command("worker", now + timedelta(seconds=181), 30)
    assert command.command == "cancel_auth"


@pytest.fixture
def migrated_postgres_url():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not set")

    schema = f"test_runtime_{uuid4().hex}"
    admin_engine = create_engine(database_url)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    test_url = make_url(database_url).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", test_url.render_as_string(hide_password=False))
    command.upgrade(config, "head")
    try:
        yield test_url
    finally:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


def test_migration_creates_all_runtime_tables(migrated_postgres_url):
    engine = create_engine(migrated_postgres_url)
    inspector = inspect(engine)

    assert {
        "inbound_messages",
        "outbound_messages",
        "worker_instances",
        "worker_commands",
        "login_sessions",
        "audit_events",
        "command_definitions",
        "command_reply_templates",
        "game_settings",
        "users",
        "daily_checkins",
        "items",
        "user_items",
        "admin_accounts",
        "admin_sessions",
        "admin_idempotency_records",
        "admin_config_revisions",
        "manual_login_leases",
        "random_event_settings",
        "random_event_scenes",
        "random_event_scene_seats",
        "random_event_schedules",
        "random_events",
        "random_event_seats",
        "random_event_participants",
        "ranks",
        "departments",
        "promotion_requests",
        "promotion_approvals",
        "department_requests",
        "department_approvals",
        "undercover_word_sets",
    } <= set(inspector.get_table_names())
    assert "ux_inbound_messages_platform_message_id" in {
        index["name"] for index in inspector.get_indexes("inbound_messages")
    }
    assert "ix_outbound_messages_claim" in {
        index["name"] for index in inspector.get_indexes("outbound_messages")
    }


def test_migration_seeds_undercover_word_library(migrated_postgres_url):
    engine = create_engine(migrated_postgres_url)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT category, civilian_word, undercover_word, enabled "
                "FROM undercover_word_sets"
            )
        ).mappings().all()

    assert len(rows) == 900
    assert {row["category"] for row in rows} == _UNDERCOVER_WORD_CATEGORIES
    assert all(row["enabled"] for row in rows)
    assert all(
        sum(row["category"] == category for row in rows) == 100
        for category in _UNDERCOVER_WORD_CATEGORIES
    )
    assert len(
        {
            tuple(sorted((row["civilian_word"], row["undercover_word"])))
            for row in rows
        }
    ) == 900


def test_undercover_migration_creates_game_tables_and_defaults(migrated_postgres_url):
    engine = create_engine(migrated_postgres_url)
    inspector = inspect(engine)

    assert {
        "undercover_settings",
        "undercover_role_rules",
        "direct_chats",
        "undercover_sessions",
        "undercover_session_members",
        "undercover_games",
        "undercover_game_players",
        "undercover_votes",
    } <= set(inspector.get_table_names())
    assert "ux_undercover_one_active_session" in {
        index["name"] for index in inspector.get_indexes("undercover_sessions")
    }
    assert {"destination_chatroom_id", "delivery_kind"} <= {
        column["name"] for column in inspector.get_columns("outbound_messages")
    }
    with engine.connect() as connection:
        rules = connection.execute(
            text(
                "SELECT player_count, civilian_count, undercover_count, whiteboard_count "
                "FROM undercover_role_rules ORDER BY player_count"
            )
        ).all()

    assert rules == [(4, 3, 1, 0), (5, 3, 1, 1), (6, 4, 1, 1), (7, 4, 2, 1), (8, 5, 2, 1)]
    assert "ix_worker_commands_claim" in {
        index["name"] for index in inspector.get_indexes("worker_commands")
    }
    assert "lease_token" in {
        column["name"] for column in inspector.get_columns("outbound_messages")
    }
    assert "reply_index" in {
        column["name"] for column in inspector.get_columns("outbound_messages")
    }
    assert {"inbound_message_id"} not in {
        set(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("outbound_messages")
    }
    assert "lease_token" in {
        column["name"] for column in inspector.get_columns("worker_commands")
    }
    assert {"command", "scenario"} in {
        set(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("command_reply_templates")
    }
    with engine.connect() as connection:
        template_count = connection.scalar(
            text("SELECT count(*) FROM command_reply_templates")
        )
        help_command = connection.scalar(
            text("SELECT command FROM command_definitions WHERE command = '/帮助'")
        )
    assert template_count >= 15
    assert help_command == "/帮助"


def test_postgres_enforces_uniqueness_and_atomic_enqueue(
    migrated_postgres_url, inbound, now
):
    from dzmm_bot.core.repository import CoreRepository
    from dzmm_bot.core.schema import InboundRecord, OutboundRecord

    factory = sessionmaker(create_engine(migrated_postgres_url), expire_on_commit=False)
    repository = CoreRepository(factory)

    with pytest.raises(RuntimeError):
        with repository.transaction():
            stored, _ = repository.accept_inbound(inbound)
            repository.enqueue_outbound(stored.id, "reply")
            raise RuntimeError("roll back")

    with factory() as session:
        assert session.scalar(select(InboundRecord)) is None
        assert session.scalar(select(OutboundRecord)) is None

    first, inserted = repository.accept_inbound(inbound)
    duplicate, duplicate_inserted = repository.accept_inbound(inbound)
    assert inserted is True
    assert duplicate_inserted is False
    assert duplicate.id == first.id

    outbound = repository.enqueue_outbound(first.id, "reply")
    first_claim = repository.claim_outbound("worker-a", now, 30)
    assert first_claim.id == outbound.id
    claimed = repository.claim_outbound("worker-b", now + timedelta(seconds=31), 30)
    assert claimed.id == outbound.id
    assert repository.claim_outbound("worker-c", now + timedelta(seconds=32), 30) is None
    assert (
        repository.confirm_sent(
            outbound.id,
            "worker-a",
            first_claim.lease_token,
            "stale-send",
            now + timedelta(seconds=31),
        )
        is False
    )
    assert (
        repository.confirm_sent(
            outbound.id,
            "worker-b",
            claimed.lease_token,
            "sent-1",
            now + timedelta(seconds=32),
        )
        is True
    )
    assert repository.claim_outbound("worker-c", now + timedelta(seconds=62), 30) is None

    heartbeat = repository.record_worker_heartbeat(
        WorkerHeartbeat("worker-a", LoginState.READY, now)
    )
    updated = repository.record_worker_heartbeat(
        WorkerHeartbeat(
            "worker-a", LoginState.AUTH_REQUIRED, now + timedelta(seconds=5)
        )
    )
    assert updated.id == heartbeat.id
    assert updated.recorded_at == now + timedelta(seconds=5)


def test_postgres_concurrent_claims_and_upserts_are_atomic(
    migrated_postgres_url, inbound, now
):
    from dzmm_bot.core.repository import CoreRepository

    factory = sessionmaker(create_engine(migrated_postgres_url), expire_on_commit=False)
    repository = CoreRepository(factory)

    duplicate_barrier = Barrier(2)

    def accept_inbound():
        duplicate_barrier.wait()
        return repository.accept_inbound(inbound)

    with ThreadPoolExecutor(max_workers=2) as executor:
        accepted = list(executor.map(lambda _: accept_inbound(), range(2)))
    assert sorted(inserted for _, inserted in accepted) == [False, True]
    assert len({record.id for record, _ in accepted}) == 1

    inbound_record = accepted[0][0]
    outbound = repository.enqueue_outbound(inbound_record.id, "reply")
    claim_barrier = Barrier(2)

    def claim_outbound(worker_id):
        claim_barrier.wait()
        return repository.claim_outbound(worker_id, now, 30)

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim_outbound, ("worker-a", "worker-b")))
    assert [claim.id for claim in claims if claim is not None] == [outbound.id]

    heartbeat_barrier = Barrier(2)

    def record_heartbeat(state):
        heartbeat_barrier.wait()
        return repository.record_worker_heartbeat(
            WorkerHeartbeat("worker-a", state, now)
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        heartbeats = list(
            executor.map(record_heartbeat, (LoginState.READY, LoginState.AUTH_REQUIRED))
        )
    assert len({heartbeat.id for heartbeat in heartbeats}) == 1
