import pytest

from dzmm_bot.core.number_bomb import (
    NUMBER_BOMB_MULTIPLIER_TENTHS,
    NumberBombEntry,
    calculate_number_bomb,
    render_number_bomb_result,
)


def entries(*values):
    return tuple(
        NumberBombEntry(f"p{index}", f"玩家{index}", number, index)
        for index, number in enumerate(values, 1)
    )


@pytest.mark.parametrize("multiplier_tenths", (8, 9, 10, 11, 12))
def test_calculation_uses_exact_integer_ratios_for_each_multiplier(multiplier_tenths):
    calculation = calculate_number_bomb(entries(10, 50, 90), multiplier_tenths)

    assert (calculation.total, calculation.player_count) == (150, 3)
    assert calculation.multiplier_tenths == multiplier_tenths
    assert (calculation.target_numerator, calculation.target_denominator) == (
        multiplier_tenths * 150,
        30,
    )
    for standing in calculation.standings:
        assert standing.deviation_numerator == abs(
            calculation.target_denominator * standing.entry.number
            - calculation.target_numerator
        )


def test_calculation_uses_distinct_exact_deviation_bands():
    calculation = calculate_number_bomb(entries(10, 50, 90), 8)

    assert calculation.valid is True
    assert [standing.entry.number for standing in calculation.standings] == [90, 10, 50]
    assert [standing.result for standing in calculation.standings] == [
        "neutral", "punished", "winner",
    ]


def test_calculation_rejects_unsupported_multiplier_values():
    assert NUMBER_BOMB_MULTIPLIER_TENTHS == (8, 9, 10, 11, 12)
    for multiplier in (7, 13, 8.0, True):
        with pytest.raises(ValueError, match="倍率"):
            calculate_number_bomb(entries(10, 50, 90), multiplier)


def test_calculation_marks_every_player_in_tied_winner_and_punished_bands():
    calculation = calculate_number_bomb(entries(1, 1, 50, 50, 100), 8)

    assert calculation.valid is True
    assert [standing.entry.number for standing in calculation.standings] == [
        100, 1, 1, 50, 50,
    ]
    assert [standing.result for standing in calculation.standings] == [
        "neutral", "punished", "punished", "winner", "winner",
    ]


def test_calculation_is_invalid_with_fewer_than_three_exact_deviation_bands():
    for values in ((10, 10, 50, 50), (20, 20, 20)):
        calculation = calculate_number_bomb(entries(*values), 8)
        assert calculation.valid is False
        assert all(standing.result is None for standing in calculation.standings)


def test_calculation_does_not_merge_exact_bands_that_display_the_same():
    calculation = calculate_number_bomb(
        entries(*tuple((index % 100) + 1 for index in range(181))), 8
    )

    displayed = [
        f"{standing.deviation_numerator / calculation.target_denominator:.2f}"
        for standing in calculation.standings
    ]
    exact_by_display = {}
    for display, standing in zip(displayed, calculation.standings, strict=True):
        exact_by_display.setdefault(display, set()).add(standing.deviation_numerator)
    assert calculation.valid is True
    assert any(len(exact_values) > 1 for exact_values in exact_by_display.values())


def test_render_result_contains_fixed_sections_sorting_and_truth_outcome():
    calculation = calculate_number_bomb(entries(10, 50, 90), 8)

    rendered = render_number_bomb_result(1, "truth", calculation)

    assert rendered.startswith("第 1 轮 - 真心话")
    assert "1. 计算过程" in rendered
    assert "玩家1：10" in rendered and "玩家2：50" in rendered and "玩家3：90" in rendered
    assert "总和：150" in rendered
    assert "人数：3" in rendered
    assert "平均值：50.00" in rendered
    assert "本轮随机倍率：×0.8" in rendered
    assert "最终数 F：平均值 × 0.8 = 40.00" in rendered
    assert "2. 偏离值排序（从大到小）" in rendered
    assert rendered.index("玩家3：90") < rendered.rindex("玩家1：10") < rendered.rindex("玩家2：50")
    assert "（第二大偏离 → 受罚者）" in rendered
    assert "（最小偏离 → 胜出者）" in rendered
    assert "3. 最终游戏结果" in rendered
    assert "胜出者：玩家2（50）" in rendered
    assert "受罚者：玩家1（10）" in rendered
    assert "本轮为真心话轮，由胜出者出题并监督，受罚者必须完成对应的惩罚。" in rendered


def test_render_result_lists_ties_and_dare_copy():
    rendered = render_number_bomb_result(
        3, "dare", calculate_number_bomb(entries(1, 1, 50, 50, 100), 10)
    )

    assert rendered.startswith("第 3 轮 - 大冒险")
    assert "本轮随机倍率：×1.0" in rendered
    assert "胜出者：玩家3（50）、玩家4（50）" in rendered
    assert "受罚者：玩家1（1）、玩家2（1）" in rendered
    assert "本轮为大冒险轮" in rendered


def test_render_invalid_result_requests_replay_without_annotations():
    rendered = render_number_bomb_result(
        2, "truth", calculate_number_bomb(entries(10, 10, 50, 50), 11)
    )

    assert "3. 最终游戏结果" in rendered
    assert "本轮随机倍率：×1.1" in rendered
    assert "本轮偏离值不足三个不同档位，本轮无效，请所有参与者重新私聊报数。" in rendered
    assert "受罚者）" not in rendered
    assert "胜出者）" not in rendered
