from dataclasses import replace

from .shop_cards import SYSTEM_SHOP_ITEMS, SystemShopItem, item_by_key


EFFECT_LABELS = {
    "none": "无效果",
    "gift": "赠送币",
    "scratch": "随机奖励",
    "event_ad_slot": "优选投稿位",
    "ai_quota": "对话次数卡",
    "multiplayer_quota": "多人游戏次数卡",
    "adult_m": "自愿场景公告",
    "adult_scene": "授权场景",
    "adult_common": "临时状态",
}
EFFECT_FIELDS = {
    "none": (),
    "gift": ("reward",),
    "scratch": ("reward_min", "reward_max"),
    "event_ad_slot": (),
    "ai_quota": ("quota",),
    "multiplayer_quota": ("quota",),
    "adult_m": (),
    "adult_scene": ("template", "recipient_count"),
    "adult_common": ("template", "duration_minutes"),
}
PARAMETER_LABELS = {
    "reward": "赠送金额",
    "reward_min": "随机最小金额",
    "reward_max": "随机最大金额",
    "quota": "增加次数",
    "template": "场景模板",
    "recipient_count": "受邀人数",
    "duration_minutes": "持续分钟数",
}


def default_effect_config(effect_type, system_key=None):
    definition = next(
        (item for item in SYSTEM_SHOP_ITEMS if item.key == system_key), None
    )
    if definition is not None and definition.effect_type != effect_type:
        definition = None
    if effect_type == "gift":
        return {"reward": definition.reward if definition else 2}
    if effect_type == "scratch":
        low, high = definition.reward_range if definition else (1, 10)
        return {"reward_min": low, "reward_max": high}
    if effect_type in ("ai_quota", "multiplayer_quota"):
        return {"quota": 1}
    if effect_type == "adult_scene":
        return {
            "template": definition.key if definition else "adult_flirt",
            "recipient_count": definition.recipient_count if definition else 1,
        }
    if effect_type == "adult_common":
        return {
            "template": definition.key if definition else "adult_common_1h",
            "duration_minutes": definition.duration_minutes if definition else 60,
        }
    return {}


def validate_effect_config(effect_type, config):
    if effect_type is not None and not isinstance(effect_type, str):
        return [("effect_type", "效果类型格式无效", "从效果字典选择有效类型")]
    code = effect_type or "none"
    errors = []
    if not isinstance(code, str) or code not in EFFECT_FIELDS:
        return [("effect_type", "效果类型不受支持", "从效果字典选择有效类型")]
    if not isinstance(config, dict):
        return [("effect_config", "效果参数格式无效", "按效果类型填写对应参数")]
    required = set(EFFECT_FIELDS[code])
    for field in sorted(required - config.keys()):
        errors.append((field, "缺少必需的效果参数", f"填写{PARAMETER_LABELS[field]}"))
    for field in sorted(config.keys() - required):
        errors.append((field, "此效果不使用该参数", "清空不适用的效果参数"))
    ranges = {
        "reward": (0, 99999),
        "reward_min": (0, 99999),
        "reward_max": (0, 99999),
        "quota": (1, 999),
        "recipient_count": (1, 5),
        "duration_minutes": (1, 10080),
    }
    for field in required & config.keys():
        value = config[field]
        if field == "template":
            allowed = {
                item.key for item in SYSTEM_SHOP_ITEMS if item.effect_type == code
            }
            if not isinstance(value, str) or value not in allowed:
                errors.append((field, "模板与效果类型不匹配", "从效果字典选择同类型模板"))
        else:
            minimum, maximum = ranges[field]
            if type(value) is not int or not minimum <= value <= maximum:
                errors.append((field, "效果参数超出范围或不是整数", f"填写 {minimum}–{maximum} 的整数"))
    if (
        code == "scratch"
        and type(config.get("reward_min")) is int
        and type(config.get("reward_max")) is int
        and config["reward_min"] > config["reward_max"]
    ):
        errors.append(("reward_min", "最小金额大于最大金额", "调整为最小金额不大于最大金额"))
    return errors


def effective_config(item):
    return (
        dict(item.effect_config)
        if item.effect_config is not None
        else default_effect_config(item.effect_type, item.system_key)
    )


def effect_definition(item, snapshot=None):
    effect_type = snapshot["effect_type"] if snapshot else item.effect_type
    config = snapshot["effect_config"] if snapshot else effective_config(item)
    if effect_type in ("adult_scene", "adult_common"):
        definition = item_by_key(config["template"])
        return replace(
            definition,
            recipient_count=config.get("recipient_count", 1),
            duration_minutes=config.get("duration_minutes"),
        )
    return SystemShopItem(
        key="adult_m" if effect_type == "adult_m" else (item.system_key or "custom"),
        name=snapshot["name"] if snapshot else item.name,
        price=snapshot["price"] if snapshot else item.price,
        effect_type=effect_type or "none",
        description=item.description,
        reward=config.get("reward"),
        reward_range=(config["reward_min"], config["reward_max"]) if effect_type == "scratch" else None,
    )


def item_effect_snapshot(item):
    return {
        "name": item.name,
        "price": item.price,
        "effect_type": item.effect_type,
        "effect_config": effective_config(item),
    }


def effect_dictionary():
    return {
        "types": [
            {"code": code, "label": label, "fields": list(EFFECT_FIELDS[code]),
             "defaults": default_effect_config(None if code == "none" else code)}
            for code, label in EFFECT_LABELS.items()
        ],
        "templates": [
            {"code": item.key, "label": item.name, "effect_type": item.effect_type}
            for item in SYSTEM_SHOP_ITEMS if item.effect_type in ("adult_scene", "adult_common")
        ],
        "parameter_labels": PARAMETER_LABELS,
    }
