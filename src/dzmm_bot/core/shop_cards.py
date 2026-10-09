from dataclasses import dataclass


@dataclass(frozen=True)
class SystemShopItem:
    key: str
    name: str
    price: int
    effect_type: str
    description: str
    minimum_rank_order: int | None = None
    reward: int | None = None
    reward_range: tuple[int, int] | None = None
    recipient_count: int = 0
    duration_minutes: int | None = None


SYSTEM_SHOP_ITEMS = (
    SystemShopItem(
        "gift_basic",
        "初级赠送卡",
        3,
        "gift",
        "赠送目标员工 2 摸鱼币",
        2,
        reward=2,
        recipient_count=1,
    ),
    SystemShopItem(
        "gift_intermediate",
        "中级赠送卡",
        5,
        "gift",
        "赠送目标员工 4 摸鱼币",
        4,
        reward=4,
        recipient_count=1,
    ),
    SystemShopItem(
        "gift_advanced",
        "高级赠送卡",
        10,
        "gift",
        "赠送目标员工 8 摸鱼币",
        6,
        reward=8,
        recipient_count=1,
    ),
    SystemShopItem(
        "gift_platinum",
        "白金赠送卡",
        20,
        "gift",
        "赠送目标员工 15 摸鱼币",
        9,
        reward=15,
        recipient_count=1,
    ),
    SystemShopItem("ai_quota", "总监事对话卡", 2, "ai_quota", "当天总监事对话次数 +1"),
    SystemShopItem(
        "scratch_a",
        "刮刮卡 A",
        5,
        "scratch",
        "随机获得 1–10 摸鱼币",
        reward_range=(1, 10),
    ),
    SystemShopItem(
        "scratch_b",
        "刮刮卡 B",
        10,
        "scratch",
        "随机获得 5–15 摸鱼币",
        reward_range=(5, 15),
    ),
    SystemShopItem(
        "scratch_c",
        "刮刮卡 C",
        20,
        "scratch",
        "随机获得 10–30 摸鱼币",
        6,
        reward_range=(10, 30),
    ),
    SystemShopItem(
        "multiplayer_quota",
        "小游戏次数卡",
        3,
        "multiplayer_quota",
        "当天多人游戏发起次数 +1",
    ),
    SystemShopItem("adult_m", "M卡", 10, "adult_m", "发布自愿参与的场景公告"),
    SystemShopItem(
        "adult_flirt", "发骚卡", 20, "adult_scene", "双人授权场景", recipient_count=1
    ),
    SystemShopItem(
        "adult_training_invite",
        "调教邀请卡",
        30,
        "adult_scene",
        "邀请对方接受调教",
        recipient_count=1,
    ),
    SystemShopItem(
        "adult_trained_invite",
        "被调教邀请卡",
        30,
        "adult_scene",
        "邀请对方进行调教",
        recipient_count=1,
    ),
    SystemShopItem(
        "adult_love", "爱爱卡", 50, "adult_scene", "双人授权场景", recipient_count=1
    ),
    SystemShopItem(
        "adult_three", "3P卡", 80, "adult_scene", "三人授权场景", recipient_count=2
    ),
    SystemShopItem(
        "adult_four",
        "四人淫趴卡",
        100,
        "adult_scene",
        "四人授权场景",
        recipient_count=3,
    ),
    SystemShopItem(
        "adult_six", "六人淫趴卡", 150, "adult_scene", "六人授权场景", recipient_count=5
    ),
    SystemShopItem(
        "adult_sleep", "昏睡卡", 20, "adult_scene", "单目标授权场景", recipient_count=1
    ),
    SystemShopItem(
        "adult_gender_change",
        "性转卡",
        50,
        "adult_scene",
        "单目标授权场景",
        recipient_count=1,
    ),
    SystemShopItem(
        "adult_common_1h",
        "常识改变卡·1小时",
        50,
        "adult_common",
        "来源群临时设定 1 小时",
        recipient_count=1,
        duration_minutes=60,
    ),
    SystemShopItem(
        "adult_common_6h",
        "常识改变卡·6小时",
        80,
        "adult_common",
        "来源群临时设定 6 小时",
        recipient_count=1,
        duration_minutes=360,
    ),
    SystemShopItem(
        "adult_common_24h",
        "常识改变卡·24小时",
        100,
        "adult_common",
        "来源群临时设定 24 小时",
        recipient_count=1,
        duration_minutes=1440,
    ),
    SystemShopItem(
        "event_ad_slot",
        "优选投稿卡",
        8,
        "event_ad_slot",
        "把一件已审核的随机事件投稿锁定到今天指定场次的优选投稿位；能不能当选仍看投票",
    ),
)


_BY_KEY = {item.key: item for item in SYSTEM_SHOP_ITEMS}


def item_by_key(key: str) -> SystemShopItem:
    return _BY_KEY[key]


def adult_item(item: SystemShopItem) -> bool:
    return item.effect_type.startswith("adult_")


CATEGORY_GIFT = "礼物赠送"
CATEGORY_SCRATCH = "刮刮乐"
CATEGORY_FUNCTION = "功能道具"
CATEGORY_ADULT = "成人内容"
CATEGORY_COLLECTION = "收藏"
CATEGORY_OTHER = "其他"

# /商店 分区展示的固定组序，未分类商品归入 CATEGORY_OTHER
CATEGORY_DISPLAY_ORDER = (
    CATEGORY_GIFT,
    CATEGORY_SCRATCH,
    CATEGORY_FUNCTION,
    CATEGORY_ADULT,
)

_GIFT_DAILY_LIMIT = 2
_SCRATCH_DAILY_LIMIT = 3


def item_category(item: SystemShopItem) -> str | None:
    """系统商品的默认分类，与迁移 80 的回填值保持一致。"""
    if item.effect_type == "gift":
        return CATEGORY_GIFT
    if item.effect_type == "scratch":
        return CATEGORY_SCRATCH
    if item.effect_type == "event_ad_slot":
        return "event_ad_slot"
    if item.effect_type in ("ai_quota", "multiplayer_quota"):
        return CATEGORY_FUNCTION
    if item.effect_type.startswith("adult_"):
        return CATEGORY_ADULT
    return None


def item_daily_purchase_limit(item: SystemShopItem) -> int | None:
    """系统商品的默认每日限购次数，None 表示不限。"""
    if item.effect_type == "gift":
        return _GIFT_DAILY_LIMIT
    if item.effect_type == "scratch":
        return _SCRATCH_DAILY_LIMIT
    if item.effect_type == "event_ad_slot":
        return 1
    return None
