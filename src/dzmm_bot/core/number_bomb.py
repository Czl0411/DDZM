from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class NumberBombEntry:
    platform_id: str
    display_name: str
    number: int
    display_order: int


@dataclass(frozen=True)
class NumberBombStanding:
    entry: NumberBombEntry
    deviation_numerator: int
    result: str | None


@dataclass(frozen=True)
class NumberBombCalculation:
    total: int
    player_count: int
    target_numerator: int
    target_denominator: int
    standings: tuple[NumberBombStanding, ...]
    valid: bool


def calculate_number_bomb(
    entries: Sequence[NumberBombEntry],
) -> NumberBombCalculation:
    player_count = len(entries)
    if player_count == 0:
        raise ValueError("at least one entry is required")
    total = sum(entry.number for entry in entries)
    target_numerator = 4 * total
    target_denominator = 5 * player_count
    deviations = tuple(
        (
            entry,
            abs(target_denominator * entry.number - target_numerator),
        )
        for entry in entries
    )
    bands = sorted({deviation for _, deviation in deviations}, reverse=True)
    valid = len(bands) >= 3
    punished_band = bands[1] if valid else None
    winner_band = bands[-1] if valid else None

    standings = tuple(
        NumberBombStanding(
            entry=entry,
            deviation_numerator=deviation,
            result=(
                "punished"
                if deviation == punished_band
                else "winner"
                if deviation == winner_band
                else "neutral"
                if valid
                else None
            ),
        )
        for entry, deviation in sorted(
            deviations,
            key=lambda item: (-item[1], item[0].display_order),
        )
    )
    return NumberBombCalculation(
        total=total,
        player_count=player_count,
        target_numerator=target_numerator,
        target_denominator=target_denominator,
        standings=standings,
        valid=valid,
    )


def render_number_bomb_result(
    round_number: int,
    punishment_type: str,
    calculation: NumberBombCalculation,
) -> str:
    punishment = {"truth": "真心话", "dare": "大冒险"}[punishment_type]
    entries = sorted(
        (standing.entry for standing in calculation.standings),
        key=lambda entry: entry.display_order,
    )
    lines = [
        f"第 {round_number} 轮 - {punishment}",
        "1. 计算过程",
        *[f"{entry.display_name}：{entry.number}" for entry in entries],
        f"总和：{calculation.total}",
        f"人数：{calculation.player_count}",
        f"平均值：{_decimal(calculation.total, calculation.player_count)}",
        (
            "最终数 F："
            f"{_decimal(calculation.target_numerator, calculation.target_denominator)}"
        ),
        "2. 偏离值排序（从大到小）",
    ]
    for standing in calculation.standings:
        annotation = ""
        if standing.result == "punished":
            annotation = "（第二大偏离 → 受罚者）"
        elif standing.result == "winner":
            annotation = "（最小偏离 → 胜出者）"
        lines.append(
            f"{standing.entry.display_name}：{standing.entry.number}，"
            f"偏离值 {_decimal(standing.deviation_numerator, calculation.target_denominator)}"
            f"{annotation}"
        )
    lines.append("3. 最终游戏结果")
    if not calculation.valid:
        lines.append("本轮偏离值不足三个不同档位，本轮无效，请所有参与者重新报数。")
        return "\n".join(lines)

    winners = _result_names(calculation, "winner")
    punished = _result_names(calculation, "punished")
    lines.extend(
        [
            f"胜出者：{winners}",
            f"受罚者：{punished}",
            f"本轮为{punishment}轮，由胜出者监督，受罚者必须完成对应的惩罚。",
        ]
    )
    return "\n".join(lines)


def _result_names(calculation: NumberBombCalculation, result: str) -> str:
    selected = sorted(
        (
            standing.entry
            for standing in calculation.standings
            if standing.result == result
        ),
        key=lambda entry: entry.display_order,
    )
    return "、".join(
        f"{entry.display_name}（{entry.number}）" for entry in selected
    )


def _decimal(numerator: int, denominator: int) -> str:
    value = Decimal(numerator) / Decimal(denominator)
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
