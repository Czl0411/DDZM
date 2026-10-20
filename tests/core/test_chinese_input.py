from dzmm_bot.core.chinese_input import (
    canonicalize_command_content,
    canonicalize_command_name,
    canonicalize_fixed_option,
    traditional_to_simplified,
)
from opencc import OpenCC
from dzmm_bot.core.commands import (
    _COMMANDS,
    _COMMAND_ALIASES,
    _DARK_MARKET_QUERY_ALIASES,
)
from dzmm_bot.core.group_games import GROUP_GAME_COMMANDS
from dzmm_bot.core.random_event_submissions import SUBMISSION_COMMANDS
from dzmm_bot.core.service import (
    _DIRECT_COMMANDS,
    _RANDOM_EVENT_INDEPENDENT_COMMANDS,
)


def test_command_name_converts_traditional_to_simplified():
    assert canonicalize_command_name("/刪除黑歷史") == "/删除黑历史"


def test_command_content_preserves_whitespace_and_free_text():
    assert canonicalize_command_content(" /ban 違規發言 ") == " /ban 違規發言 "
    assert canonicalize_command_content("/幫助 遊戲") == "/帮助 遊戲"
    assert canonicalize_command_content("普通繁體聊天") == "普通繁體聊天"


def test_fixed_option_only_uses_a_canonical_allowed_value():
    allowed = {"下一页", "确认"}
    assert canonicalize_fixed_option("下一頁", allowed) == "下一页"
    assert canonicalize_fixed_option("自由內容", allowed) == "自由內容"


def test_shared_text_conversion_normalizes_width_and_traditional_script():
    assert traditional_to_simplified("ＡＢＣ蘋果") == "ABC苹果"


def test_every_registered_chinese_command_accepts_its_traditional_form():
    commands = (
        set(_COMMANDS)
        | set(_COMMAND_ALIASES)
        | set(_DARK_MARKET_QUERY_ALIASES)
        | set(GROUP_GAME_COMMANDS)
        | set(SUBMISSION_COMMANDS)
        | set(_DIRECT_COMMANDS)
        | set(_RANDOM_EVENT_INDEPENDENT_COMMANDS)
    )
    to_traditional = OpenCC("s2t")

    for command in commands:
        assert canonicalize_command_name(to_traditional.convert(command)) == command
