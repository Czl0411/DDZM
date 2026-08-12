from uuid import uuid4

import pytest


def test_parse_impression_operations_accepts_only_the_contract():
    from dzmm_bot.ai.impressions import parse_impression_operations

    text = (
        '{"operations":[{"action":"new_candidate","category":"interests",'
        '"content":"持续关注桌游"}]}'
    )

    assert parse_impression_operations(text)[0].content == "持续关注桌游"


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        '```json\n{"operations":[]}\n```',
        '{"operations":[{"action":"new_candidate","category":"diagnosis","content":"焦虑"}]}',
        '{"operations":[{"action":"new_candidate","category":"interests","content":""}]}',
        '{"operations":[{"action":"reinforce_candidate","candidate_id":"bad"}]}',
        '{"operations":[{"action":"keep","extra":true}]}',
        '{"operations":[],"extra":true}',
    ],
)
def test_parse_impression_operations_rejects_invalid_or_unsafe_payloads(payload):
    from dzmm_bot.ai.impressions import parse_impression_operations

    with pytest.raises(ValueError):
        parse_impression_operations(payload)


def test_render_impression_prompt_names_ids_and_prohibited_inferences():
    from dzmm_bot.ai.impressions import render_impression_prompt

    entry_id = uuid4()
    candidate_id = uuid4()

    prompt = render_impression_prompt(
        "只提取稳定倾向",
        stable_entries=[(entry_id, "interests", "持续关注桌游", False)],
        candidates=[(candidate_id, "expression_style", "偏好简短回复", 1, None)],
    )

    assert str(entry_id) in prompt
    assert str(candidate_id) in prompt
    assert "心理诊断" in prompt
    assert "单批内容只能支持候选" in prompt
    assert "仅输出 JSON，不输出 Markdown" in prompt
    assert "reinforce_candidate 只能包含 action、candidate_id" in prompt
    assert "weaken_entry 只能包含 action、entry_id" in prompt
    assert "不得使用 id 字段代替 candidate_id 或 entry_id" in prompt
