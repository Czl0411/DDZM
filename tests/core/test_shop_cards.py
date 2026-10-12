from dzmm_bot.core.shop_cards import (
    CATEGORY_ADULT,
    CATEGORY_FUNCTION,
    CATEGORY_GIFT,
    CATEGORY_SCRATCH,
    SYSTEM_SHOP_ITEMS,
    adult_item,
    item_by_key,
    item_category,
    item_daily_purchase_limit,
)


def test_system_shop_catalog_is_stable_and_complete() -> None:
    assert [item.key for item in SYSTEM_SHOP_ITEMS] == [
        "gift_basic",
        "gift_intermediate",
        "gift_advanced",
        "gift_platinum",
        "ai_quota",
        "scratch_a",
        "scratch_b",
        "scratch_c",
        "multiplayer_quota",
        "adult_m",
        "adult_flirt",
        "adult_training_invite",
        "adult_trained_invite",
        "adult_love",
        "adult_three",
        "adult_four",
        "adult_six",
        "adult_sleep",
        "adult_gender_change",
        "adult_common_1h",
        "adult_common_6h",
        "adult_common_24h",
        "event_ad_slot",
    ]
    assert len({item.name for item in SYSTEM_SHOP_ITEMS}) == len(SYSTEM_SHOP_ITEMS)


def test_fixed_prices_ranks_and_effect_parameters() -> None:
    assert (
        item_by_key("gift_basic").price,
        item_by_key("gift_basic").minimum_rank_order,
    ) == (3, 2)
    assert (
        item_by_key("gift_platinum").price,
        item_by_key("gift_platinum").minimum_rank_order,
    ) == (20, 9)
    assert item_by_key("gift_advanced").reward == 8
    assert item_by_key("scratch_a").reward_range == (1, 10)
    assert item_by_key("scratch_c").reward_range == (10, 30)
    assert item_by_key("adult_three").recipient_count == 2
    assert item_by_key("adult_six").recipient_count == 5
    assert item_by_key("adult_common_6h").duration_minutes == 360


def test_adult_and_purchase_categories() -> None:
    assert adult_item(item_by_key("adult_m")) is True
    assert adult_item(item_by_key("scratch_a")) is False
    assert item_category(item_by_key("gift_basic")) == CATEGORY_GIFT
    assert item_category(item_by_key("scratch_c")) == CATEGORY_SCRATCH
    assert item_category(item_by_key("ai_quota")) == CATEGORY_FUNCTION
    assert item_category(item_by_key("adult_m")) == CATEGORY_ADULT


def test_default_daily_purchase_limits() -> None:
    assert item_daily_purchase_limit(item_by_key("gift_basic")) == 2
    assert item_daily_purchase_limit(item_by_key("scratch_c")) == 3
    assert item_daily_purchase_limit(item_by_key("ai_quota")) is None
    assert item_daily_purchase_limit(item_by_key("adult_m")) is None
