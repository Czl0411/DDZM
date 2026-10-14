"""Authoritative Mistrealm card catalogue; exported to the browser at build time."""

_ROWS = [
    ("neutral_mercenary", "荒境佣兵", "unit", "any", 7, "none", "无部署效果。"),
    ("neutral_guard", "铁盾卫士", "unit", "front", 5, "armor", "部署：自身获得3护甲。"),
    ("neutral_crossbow", "山隘弩手", "unit", "back", 4, "damage3", "部署：对一个敌人造成3伤害。"),
    ("neutral_medic", "随军医师", "unit", "back", 2, "revive", "部署：可复活弃牌堆中一个基础战力不超过5的非医师单位。恢复基础战力，不触发部署；任意战列单位优先进入前列。"),
    ("neutral_mobilize", "战地动员", "tactic", "any", 0, "buff3two", "使至多两个不同友军各获得3增益。"),
    ("neutral_pierce", "破甲弩矢", "tactic", "any", 0, "pierce", "移除一个敌人的全部护甲与高于基础战力的增益，再造成3伤害。"),
    ("raven_knight", "雾鸦骑士", "unit", "front", 7, "damage2", "部署：对一个敌人造成2伤害。"),
    ("raven_hunter", "灰羽猎手", "unit", "back", 5, "hunter", "部署：存在受伤敌人时，自身获得3增益。"),
    ("raven_assassin", "断誓刺客", "unit", "front", 4, "assassin", "部署：对一个敌人造成2伤害；目标已受伤则改为4。"),
    ("raven_guide", "鸦群引路人", "unit", "back", 3, "recall", "部署：可将一个其他友军收回手牌，移除其增益、伤害与护甲。再次打出时可触发部署技能。"),
    ("crown_infantry", "烬冠步兵", "unit", "front", 5, "infantry", "部署：本列有其他友军时，自身获得3增益。"),
    ("crown_banner", "王旗执掌者", "unit", "any", 3, "banner", "持续：每当你从手牌向本列部署其他单位，使该单位获得1增益。复活不触发；多面王旗可叠加。"),
    ("crown_guard", "誓约守卫", "unit", "front", 6, "protect", "部署：使一个其他友军获得2增益及2护甲。"),
    ("crown_commander", "灰烬统领", "unit", "front", 5, "commander", "部署：本列至少有两个其他友军时，使其中两个各获得2增益。"),
    ("raven_king", "无冠鸦王", "leader", "any", 0, "damage3", "整场一次：对一个敌人造成3伤害，消耗行动。"),
    ("crown_regent", "余烬摄政", "leader", "any", 0, "regent", "整场一次：使一个友军获得3增益及2护甲，消耗行动。"),
]
CARDS = {
    key: dict(id=key, name=name, faction=key.split("_")[0], type=kind,
              row=row, power=power, effect=effect, text=text,
              art=f"assets/art/{key.replace('_', '-')}.webp")
    for key, name, kind, row, power, effect, text in _ROWS
}


def deck(faction, seat):
    if faction not in ("raven", "crown"):
        raise ValueError("阵营不正确")
    return [
        {"id": f"{seat}:{key}:{copy}", "key": key}
        for key, card in CARDS.items()
        if card["faction"] in ("neutral", faction) and card["type"] != "leader"
        for copy in range(2)
    ]
