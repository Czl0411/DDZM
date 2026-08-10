from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID


KNOWLEDGE_TOPICS = (
    "economy", "departments", "ranks", "shop", "checkin_activity",
    "random_events", "hide_and_seek", "memory_assessment", "undercover",
    "blame_bomb", "commands_help", "player_activity",
)

TOPIC_COMMANDS = {
    "economy": ("/余额", "/我", "/打卡", "/商店"),
    "departments": ("/部门", "/加入部门", "/切换部门", "/部门申请列表", "/同意部门", "/全部同意部门", "/拒绝部门", "/全部拒绝部门"),
    "ranks": ("/职位", "/晋升", "/晋升申请列表", "/同意", "/全部同意", "/拒绝", "/全部拒绝"),
    "shop": ("/商店", "/我的物品"),
    "checkin_activity": ("/打卡", "/我"),
    "random_events": ("/加入", "/退出"),
    "hide_and_seek": ("/摸鱼躲猫猫",),
    "memory_assessment": ("/记忆考核", "/继续", "/收手", "/投降"),
    "undercover": ("/谁是卧底", "/开始投票", "/投票", "/退出谁是卧底", "/结束游戏", "/加入", "/继续"),
    "blame_bomb": ("/甩锅游戏", "/甩锅", "/退出甩锅", "/加入", "/结束游戏"),
    "commands_help": (),
    "player_activity": ("/我",),
}

_TOPIC_ALIASES = {
    "economy": ("金币", "摸鱼币", "赚钱", "收入", "余额"),
    "departments": ("部门", "加入部门", "切换部门", "部门申请"),
    "ranks": ("职位", "职级", "晋升", "升职"),
    "shop": ("商店", "商品", "物品", "购买"),
    "checkin_activity": ("打卡", "活跃", "全勤", "连续打卡"),
    "random_events": ("随机事件", "角色报名"),
    "hide_and_seek": ("躲猫猫", "躲藏", "巡查"),
    "memory_assessment": ("记忆考核", "答案", "收手", "对战"),
    "undercover": ("谁是卧底", "卧底", "白板", "投票"),
    "blame_bomb": ("甩锅", "事故卡", "关键词"),
    "commands_help": ("指令", "命令", "帮助", "怎么操作"),
    "player_activity": ("战绩", "玩过", "赢过", "输了", "参加过"),
}

_COMMAND_ALIASES = {
    "/开始摸鱼躲藏": "hide_and_seek", "/躲": "hide_and_seek",
    "/答案": "memory_assessment",
}
for _topic, _commands in TOPIC_COMMANDS.items():
    for _command in _commands:
        _COMMAND_ALIASES.setdefault(_command, _topic)


@dataclass(frozen=True)
class AIKnowledgeCard:
    topic: str
    title: str
    keywords: tuple[str, ...]
    content: str
    enabled: bool
    priority: int
    id: UUID | None = None


def route_ai_topics(
    question: str, cards: Sequence[AIKnowledgeCard]
) -> tuple[str, ...]:
    normalized = question.strip().casefold()
    matched: set[str] = set()
    priorities = {topic: 10001 for topic in KNOWLEDGE_TOPICS}
    for card in cards:
        if not card.enabled or card.topic not in priorities:
            continue
        keywords = {keyword.strip().casefold() for keyword in card.keywords if keyword.strip()}
        if any(keyword in normalized for keyword in keywords):
            matched.add(card.topic)
            priorities[card.topic] = min(priorities[card.topic], card.priority)
    for topic, aliases in _TOPIC_ALIASES.items():
        if any(alias.casefold() in normalized for alias in aliases):
            matched.add(topic)
    command_token = normalized.split(maxsplit=1)[0] if normalized.startswith("/") else ""
    command_topic = _COMMAND_ALIASES.get(command_token)
    if command_topic:
        matched.add(command_topic)
    topic_order = {topic: index for index, topic in enumerate(KNOWLEDGE_TOPICS)}
    return tuple(sorted(matched, key=lambda topic: (priorities[topic], topic_order[topic])))


def select_knowledge_cards(
    topics: Sequence[str],
    cards: Sequence[AIKnowledgeCard],
    *,
    limit: int = 6,
) -> tuple[AIKnowledgeCard, ...]:
    selected_topics = set(topics)
    selected = [
        card for card in cards
        if card.enabled and card.topic in selected_topics
    ]
    return tuple(sorted(selected, key=lambda card: (card.priority, card.title, str(card.id or "")))[:limit])
