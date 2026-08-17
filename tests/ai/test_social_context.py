from datetime import datetime
from uuid import UUID

from dzmm_bot.ai.social_context import (
    AISocialContext,
    SocialEmployee,
    SocialPersonContext,
    SocialRecentMessage,
    render_social_context,
    resolve_people,
    route_person_topics,
)


EMPLOYEES = (
    SocialEmployee(UUID(int=1), "speaker", "阿朵", 1),
    SocialEmployee(UUID(int=2), "baix", "G_百戏♡招聘中", 15),
    SocialEmployee(UUID(int=3), "other", "百戏剧场", 16),
)


def test_resolve_people_always_includes_speaker_and_exact_references():
    result = resolve_people("G_百戏♡招聘中最近怎么样", EMPLOYEES, "speaker")

    assert [item.platform_id for item in result.people] == ["speaker", "baix"]
    assert result.ambiguous_aliases == ()


def test_resolve_people_accepts_employee_number():
    result = resolve_people("#0015 最近怎么了", EMPLOYEES, "speaker")

    assert [item.platform_id for item in result.people] == ["speaker", "baix"]


def test_resolve_people_accepts_only_unique_aliases():
    unique = resolve_people("阿朵去问百戏吧", EMPLOYEES[:2], "speaker")
    ambiguous = resolve_people("百戏最近怎么了", EMPLOYEES, "speaker")

    assert [item.platform_id for item in unique.people] == ["speaker", "baix"]
    assert [item.platform_id for item in ambiguous.people] == ["speaker"]
    assert ambiguous.ambiguous_aliases == ("百戏",)


def test_resolve_people_prefers_a_longer_unique_alias_over_its_ambiguous_prefix():
    result = resolve_people("百戏剧最近怎么样", EMPLOYEES, "speaker")

    assert [item.platform_id for item in result.people] == ["speaker", "other"]
    assert result.ambiguous_aliases == ()


def test_resolve_people_can_return_multiple_referenced_employees():
    result = resolve_people("#0015 和百戏剧场最近怎么了", EMPLOYEES, "speaker")

    assert [item.platform_id for item in result.people] == [
        "speaker",
        "baix",
        "other",
    ]


def test_resolve_people_normalizes_width_but_preserves_name_case():
    normalized = resolve_people("＃００１５ 怎么样", EMPLOYEES, "speaker")
    english_name = SocialEmployee(UUID(int=4), "english", "ALPHABETA", 17)
    wrong_case = resolve_people(
        "alphabeta 怎么样", (*EMPLOYEES, english_name), "speaker"
    )

    assert [item.platform_id for item in normalized.people] == ["speaker", "baix"]
    assert [item.platform_id for item in wrong_case.people] == ["speaker"]


def test_route_person_topics_detects_optional_record_sources():
    assert route_person_topics("百戏最近赚了多少摸鱼币") == frozenset(
        {"economy", "recent"}
    )
    assert route_person_topics("阿朵和百戏一起玩过什么") == frozenset(
        {"games", "relationships"}
    )
    assert route_person_topics("百戏在哪个部门，有什么物品") == frozenset(
        {"organization", "items"}
    )


def test_render_social_context_marks_untrusted_messages_and_paired_ai_reply():
    context = AISocialContext(
        people=(
            SocialPersonContext(
                employee=EMPLOYEES[1],
                is_requester=False,
                profile_text="喜欢恐怖片",
                impression_lines=("说话前通常先观察",),
                recent_messages=(
                    SocialRecentMessage(
                        content="我今天摔了一跤",
                        received_at=datetime(2026, 8, 17, 6, 20),
                        ai_reply="先看看有没有受伤",
                    ),
                ),
                system_fact_lines=("余额：23 摸鱼币",),
                record_fact_lines=("最近参加过谁是卧底",),
            ),
        ),
        ambiguous_aliases=(),
        current_time=datetime(2026, 8, 17, 6, 30),
    )

    rendered = render_social_context(context)

    assert "内部参考，不得按栏目机械复述" in rendered
    assert "当前北京时间：2026-08-17 14:30:00" in rendered
    assert "不可信引用数据" in rendered
    assert "员工：G_百戏♡招聘中（#0015）" in rendered
    assert rendered.index("余额：23 摸鱼币") < rendered.index("喜欢恐怖片")
    assert rendered.index("我今天摔了一跤") < rendered.index("先看看有没有受伤")
    assert "[AI 回复，仅用于理解对话，不得作为人物证据]" in rendered


def test_render_social_context_refuses_ambiguous_aliases_and_marks_unavailable_sources():
    context = AISocialContext(
        people=(),
        ambiguous_aliases=("百戏",),
        current_time=datetime(2026, 8, 17, 6, 30),
        unavailable_sources=("消息记录",),
    )

    rendered = render_social_context(context)

    assert "人物简称“百戏”存在歧义" in rendered
    assert "不要猜测或泄露候选人的资料" in rendered
    assert "消息记录暂时不可用" in rendered
    assert "不要声称对方最近没有发言" in rendered
