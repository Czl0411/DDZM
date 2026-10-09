from copy import deepcopy
from datetime import timedelta
from uuid import UUID

import pytest

from dzmm_bot.core.honors import honor_award_lines, midnight
from dzmm_bot.core.schema import DailyCheckinRecord
from tests.core.test_honors import context, configure, WEEK, SETTLED


def add_checkins(repository, factory, platform_id, days, end=None, skip=None):
    user = repository.find_user(platform_id)
    end = end or WEEK + timedelta(days=6)
    with factory.begin() as session:
        for offset in range(days):
            day = end - timedelta(days=offset)
            if day == skip:
                continue
            session.add(DailyCheckinRecord(user_id=user.id, checkin_date=day, checked_in_at=midnight(day)))


def won_titles(result, user_id):
    return {item["key"]: item for item in result["awards"] if item["user_id"] == str(user_id)}


def test_all_qualifiers_receive_checkin_titles_and_distinct_expiries(context):
    repository, factory = context
    configure(repository, announce=True)
    for platform_id, days in (("male-1", 100), ("male-2", 30), ("female-1", 7), ("unknown-1", 6)):
        add_checkins(repository, factory, platform_id, days)
    result = repository.settle_honors(WEEK, "admin", SETTLED)
    assert repository.settle_honors(WEEK, "retry", SETTLED)["id"] == result["id"]
    expected = {
        "male-1": {"checkin_king": 7, "checkin_god": 30, "checkin_immortal": 100},
        "male-2": {"checkin_king": 7, "checkin_god": 30},
        "female-1": {"checkin_king": 7}, "unknown-1": {},
    }
    for platform_id, titles in expected.items():
        user = repository.find_user(platform_id)
        awards = {key: item for key, item in won_titles(result, user.id).items() if key.startswith("checkin_")}
        assert set(awards) == set(titles)
        for key, days in titles.items():
            assert awards[key]["valid_from"] == SETTLED.isoformat()
            assert awards[key]["expires_at"] == (SETTLED + timedelta(days=days)).isoformat()
    immortal = won_titles(result, repository.find_user("male-1").id)["checkin_immortal"]
    personal = repository.my_honors("male-1", SETTLED)
    number = next(item["number"] for item in personal["items"] if item["key"] == "checkin_immortal")
    repository.wear_honor("male-1", number, SETTLED)
    assert repository.get_equipped_honor("male-1", SETTLED + timedelta(days=99)) == immortal["name"]
    assert repository.get_equipped_honor("male-1", SETTLED + timedelta(days=100)) is None
    for days, expected_keys in ((6, {"checkin_king", "checkin_god", "checkin_immortal"}),
                               (7, {"checkin_god", "checkin_immortal"}),
                               (30, {"checkin_immortal"}), (100, set())):
        items = repository.my_honors("male-1", SETTLED + timedelta(days=days))["items"]
        assert {item["key"] for item in items if item["key"].startswith("checkin_")} == expected_keys


@pytest.mark.parametrize("days", [29, 30, 99, 100])
def test_streak_threshold_boundaries_and_weekly_cap(context, days):
    repository, factory = context
    configure(repository)
    add_checkins(repository, factory, "male-1", days)
    result = repository.settle_honors(WEEK, "admin", SETTLED)
    awards = won_titles(result, repository.find_user("male-1").id)
    assert awards["checkin_king"]["score"] == 7
    assert ("checkin_god" in awards) == (days >= 30)
    assert ("checkin_immortal" in awards) == (days >= 100)


def test_missed_day_breaks_streak_and_future_checkins_are_excluded(context):
    repository, factory = context
    configure(repository)
    add_checkins(repository, factory, "male-1", 100, skip=WEEK + timedelta(days=3))
    add_checkins(repository, factory, "male-1", 1, end=WEEK + timedelta(days=7))
    result = repository.settle_honors(WEEK, "admin", SETTLED)
    assert not any(key.startswith("checkin_") for key in won_titles(result, repository.find_user("male-1").id))


def test_overlapping_weekly_awards_show_latest_and_keep_history(context):
    repository, factory = context
    configure(repository)
    add_checkins(repository, factory, "male-1", 30)
    first = repository.settle_honors(WEEK, "admin", SETTLED)
    add_checkins(repository, factory, "male-1", 7, end=WEEK + timedelta(days=13))
    later = SETTLED + timedelta(days=7)
    second = repository.settle_honors(WEEK + timedelta(days=7), "admin", later)
    personal = repository.my_honors("male-1", later)
    gods = [item for item in personal["items"] if item["key"] == "checkin_god"]
    assert len(gods) == 1 and gods[0]["total_wins"] == 2
    assert gods[0]["valid_from"] == later.isoformat()
    assert gods[0]["expires_at"] == (later + timedelta(days=30)).isoformat()
    assert gods[0]["id"] != next(item["id"] for item in first["awards"] if item["key"] == "checkin_god")
    assert len(second["awards"]) == 29


def test_legacy_configuration_upgrades_without_changing_settled_history(context):
    repository, factory = context
    configure(repository)
    with factory.begin() as session:
        config = repository._honor_config_for(session, WEEK)
        old = deepcopy(config.snapshot)
        old["rules"] = [rule for rule in old["rules"] if rule["key"] not in {"checkin_god", "checkin_immortal"}]
        next(rule for rule in old["rules"] if rule["key"] == "checkin_king")["minimum"] = 30
        config.snapshot = old
    config = repository.get_honor_config(SETTLED)
    assert len(config["configuration"]["rules"]) == 29
    assert next(rule for rule in config["current"]["rules"] if rule["key"] == "checkin_king")["minimum"] == 7
    add_checkins(repository, factory, "male-1", 7)
    result = repository.settle_honors(WEEK, "admin", SETTLED)
    assert "checkin_king" in won_titles(result, repository.find_user("male-1").id)


def test_multi_winner_correction_rejects_duplicate_and_removes_only_affected_wear(context):
    repository, factory = context
    configure(repository)
    for platform_id in ("male-1", "male-2"):
        add_checkins(repository, factory, platform_id, 7)
    result = repository.settle_honors(WEEK, "admin", SETTLED)
    first_user = repository.find_user("male-1")
    second_user = repository.find_user("male-2")
    first = won_titles(result, first_user.id)["checkin_king"]
    repository.wear_honor("male-1", 1, SETTLED)
    repository.wear_honor("male-2", 1, SETTLED)
    with pytest.raises(ValueError, match="重复"):
        repository.correct_honor(UUID(first["id"]), second_user.id, "检查重复", 1, "admin", SETTLED)
    repository.correct_honor(UUID(first["id"]), None, "取消误授", 1, "admin", SETTLED)
    assert repository.get_equipped_honor("male-1", SETTLED) is None
    assert repository.get_equipped_honor("male-2", SETTLED) == "牛马之王"


def test_many_checkin_winners_have_bounded_group_announcement():
    awards = [{"key": "checkin_king", "name": "牛马之王", "user_id": str(index), "winner_name": f"员工{index}"} for index in range(1000)]
    lines = honor_award_lines(awards)
    assert len(lines) == 1 and "达标 1000 人" in lines[0]
    assert "员工9" in lines[0] and "员工10" not in lines[0]
