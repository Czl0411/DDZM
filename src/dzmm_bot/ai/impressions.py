import json
from dataclasses import dataclass
from typing import Literal
from uuid import UUID


IMPRESSION_CATEGORIES = (
    "expression_style",
    "group_interaction",
    "humor_style",
    "interests",
    "supervisor_interaction",
    "boundaries",
)

ImpressionAction = Literal[
    "new_candidate",
    "reinforce_candidate",
    "weaken_entry",
    "replace_entry",
    "keep",
]


@dataclass(frozen=True)
class AIImpressionOperation:
    action: ImpressionAction
    category: str | None = None
    content: str | None = None
    candidate_id: UUID | None = None
    entry_id: UUID | None = None


def parse_impression_operations(text: str) -> tuple[AIImpressionOperation, ...]:
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("印象操作必须是 JSON") from error
    if not isinstance(payload, dict) or set(payload) != {"operations"}:
        raise ValueError("印象操作顶层字段无效")
    items = payload["operations"]
    if not isinstance(items, list) or len(items) > 50:
        raise ValueError("印象操作数量无效")
    return tuple(_parse_operation(item) for item in items)


def _parse_operation(item: object) -> AIImpressionOperation:
    if not isinstance(item, dict) or not isinstance(item.get("action"), str):
        raise ValueError("印象操作无效")
    action = item["action"]
    fields = {
        "new_candidate": {"action", "category", "content"},
        "reinforce_candidate": {"action", "candidate_id"},
        "weaken_entry": {"action", "entry_id"},
        "replace_entry": {"action", "entry_id", "category", "content"},
        "keep": {"action"},
    }
    if action not in fields or set(item) != fields[action]:
        raise ValueError("印象操作字段无效")
    if action == "keep":
        return AIImpressionOperation(action="keep")
    if action == "reinforce_candidate":
        return AIImpressionOperation(
            action="reinforce_candidate",
            candidate_id=_parse_uuid(item["candidate_id"]),
        )
    if action == "weaken_entry":
        return AIImpressionOperation(
            action="weaken_entry", entry_id=_parse_uuid(item["entry_id"])
        )
    category = item["category"]
    content = item["content"]
    if category not in IMPRESSION_CATEGORIES:
        raise ValueError("印象分类无效")
    if not isinstance(content, str) or not 1 <= len(content.strip()) <= 240:
        raise ValueError("印象内容无效")
    if action == "new_candidate":
        return AIImpressionOperation(
            action="new_candidate", category=category, content=content.strip()
        )
    return AIImpressionOperation(
        action="replace_entry",
        entry_id=_parse_uuid(item["entry_id"]),
        category=category,
        content=content.strip(),
    )


def _parse_uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise ValueError("印象引用 ID 无效")
    try:
        return UUID(value)
    except ValueError as error:
        raise ValueError("印象引用 ID 无效") from error


def render_impression_prompt(
    extraction_prompt: str,
    *,
    stable_entries: list[tuple[UUID, str, str, bool]] | tuple[tuple[UUID, str, str, bool], ...],
    candidates: list[tuple[UUID, str, str, int, UUID | None]]
    | tuple[tuple[UUID, str, str, int, UUID | None], ...],
) -> str:
    stable_text = "\n".join(
        f"- id={entry_id}; category={category}; pinned={pinned}; content={content}"
        for entry_id, category, content, pinned in stable_entries
    ) or "- 无"
    candidate_text = "\n".join(
        f"- id={candidate_id}; category={category}; support_batches={support_batches}; "
        f"conflict_entry_id={conflict_entry_id or '无'}; content={content}"
        for candidate_id, category, content, support_batches, conflict_entry_id in candidates
    ) or "- 无"
    categories = "、".join(IMPRESSION_CATEGORIES)
    contract = (
        '{"operations":[{"action":"new_candidate","category":"interests",'
        '"content":"持续关注桌游"}]}'
    )
    return "\n\n".join(
        (
            extraction_prompt.strip(),
            "只分析本批普通群聊。不得记录指令、游戏过程、随机事件过程、一次性情绪、第三方描述、隐私、心理诊断、道德判断或负面人格标签。单批内容只能支持候选，不能自行声明稳定结论。仅输出 JSON，不输出 Markdown。",
            f"允许分类：{categories}",
            f"已有稳定印象：\n{stable_text}",
            f"已有候选印象：\n{candidate_text}",
            "字段契约（不得增减或改名）：keep 只能包含 action；new_candidate 只能包含 action、category、content；reinforce_candidate 只能包含 action、candidate_id；weaken_entry 只能包含 action、entry_id；replace_entry 只能包含 action、entry_id、category、content。引用已有项目时必须使用上方精确 ID，不得使用 id 字段代替 candidate_id 或 entry_id。",
            f"输出格式示例：{contract}",
        )
    )
