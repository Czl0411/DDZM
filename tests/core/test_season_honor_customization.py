"""Compatibility coverage for historical S1 honors after retiring their commands."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from .test_honors import INITIAL, context
from dzmm_bot.core.commands import GroupCommandHandler
from dzmm_bot.core.schema import (
    HonorAwardRecord,
    HonorConfigRecord,
    HonorSeasonRecord,
    RankRecord,
    UserRecord,
)
from dzmm_bot.runtime.contracts import InboundMessage


def seed_historical_s1_honor(
    context, *, rank="部门经理", rank_order=7, custom_name=None
):
    repository, factory = context
    user = repository.find_user("male-1")
    with factory.begin() as session:
        current_rank = session.scalar(
            select(RankRecord).where(RankRecord.sort_order == 1)
        )
        session.get(UserRecord, user.id).rank_id = current_rank.id
        session.add(
            HonorSeasonRecord(
                code="S1",
                issued_at=INITIAL,
                issued_by="historical-import",
                preview_digest="a" * 64,
                issued_count=1,
            )
        )
        original_title = f"S1赛季 · 技术部 · {rank}"
        details = {
            "rank": rank,
            "rank_order": rank_order,
            "department": "技术部",
            "actor": "historical-import",
        }
        if custom_name:
            details.update(
                custom_name=custom_name,
                customized_at=INITIAL.isoformat(),
                original_title=original_title,
            )
        award = HonorAwardRecord(
            title_key="season:S1",
            title_name=f"S1赛季 · {custom_name}" if custom_name else original_title,
            user_id=user.id,
            winner_name=user.display_name,
            valid_from=INITIAL,
            sort_order=1000,
            public_score=False,
            source="season",
            season_code="S1",
            source_details=details,
        )
        session.add(award)
        session.flush()
        return award.id


def chat(repository, content, identifier=None):
    return GroupCommandHandler(repository).handle(
        InboundMessage(
            identifier or str(uuid4()),
            "male-1",
            content,
            INITIAL,
            source_type="group",
            chatroom_id="group-main",
        )
    )


def test_historical_s1_honor_is_grandfathered_after_threshold_changes(context):
    repository, factory = context
    seed_historical_s1_honor(context)
    with factory.begin() as session:
        config = session.scalar(
            select(HonorConfigRecord).order_by(HonorConfigRecord.version.desc())
        )
        config.snapshot = {**config.snapshot, "season_minimum_rank_order": 11}

    assert "S1赛季 · 部门经理" in chat(repository, "/我的称号")
    assert repository.wear_honor("male-1", 1, INITIAL) == "S1赛季 · 部门经理"
    repository.run_honor_jobs(INITIAL)
    assert repository.get_equipped_honor("male-1", INITIAL) == "S1赛季 · 部门经理"
    history = repository.honor_history(
        INITIAL, user_id=repository.find_user("male-1").id
    )["items"]
    assert history[0]["active"]
    assert history[0]["season_info"]["status"] == "available"
    assert history[0]["season_info"]["qualification_note"] == "历史已发放，保留资格"


def test_historical_custom_name_and_closing_rank_snapshot_are_preserved(context):
    repository, _ = context
    seed_historical_s1_honor(
        context, rank="历史自定义职位", rank_order=8, custom_name="赛季老兵"
    )

    assert "S1赛季 · 赛季老兵" in chat(repository, "/我的称号")
    history = repository.honor_history(
        INITIAL, user_id=repository.find_user("male-1").id
    )["items"][0]
    assert history["name"] == "S1赛季 · 赛季老兵"
    assert history["source_details"]["original_title"] == "S1赛季 · 技术部 · 历史自定义职位"
    assert history["season_info"]["closing_rank"] == "历史自定义职位"
    assert history["season_info"]["rank_order"] == 8
    assert history["season_info"]["customized"]


def test_revoked_historical_s1_honor_stays_in_history_but_cannot_be_worn(context):
    repository, _ = context
    award_id = seed_historical_s1_honor(context)
    repository.wear_honor("male-1", 1, INITIAL)

    repository.revoke_permanent_honor(award_id, "历史纠错", "admin", INITIAL)

    assert repository.my_honors("male-1", INITIAL)["items"] == []
    assert repository.get_equipped_honor("male-1", INITIAL) is None
    with pytest.raises(ValueError, match="称号序号无效"):
        repository.wear_honor("male-1", 1, INITIAL)
    history = repository.honor_history(
        INITIAL, user_id=repository.find_user("male-1").id
    )["items"][0]
    assert history["revoked_at"] == INITIAL.isoformat()
    assert not history["active"]
    assert history["season_info"]["status"] == "revoked"


def test_retired_s1_commands_cannot_modify_historical_award(context):
    repository, factory = context
    award_id = seed_historical_s1_honor(context)

    assert chat(repository, "/赛季称号") is None
    assert chat(repository, "/修改赛季称号 不应修改") is None
    with factory() as session:
        assert session.get(HonorAwardRecord, award_id).title_name == (
            "S1赛季 · 技术部 · 部门经理"
        )
