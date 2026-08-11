from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class RandomSource(Protocol):
    def randrange(self, stop: int) -> int: ...

    def choice(self, values: Sequence[int]) -> int: ...

    def shuffle(self, values: list[int]) -> None: ...


@dataclass(frozen=True)
class RedPacketAllocation:
    shares: tuple[int, ...]
    has_empty: bool


def generate_red_packet_allocation(
    player_count: int,
    total_amount: int,
    empty_probability_percent: int,
    rng: RandomSource,
) -> RedPacketAllocation:
    _validate(player_count, total_amount, empty_probability_percent)
    forced_empty = (
        (player_count == 2 and total_amount == 2)
        or (player_count >= 3 and total_amount < player_count * 2)
    )
    has_empty = (
        forced_empty or rng.randrange(100) < empty_probability_percent
    )
    if has_empty:
        shares = [0, *([1] * (player_count - 2)), 2]
    elif player_count == 2:
        shares = [1, 2]
    else:
        shares = [1, *([2] * (player_count - 2)), 3]

    maximum_index = len(shares) - 1
    for _ in range(total_amount - sum(shares)):
        eligible = [
            maximum_index,
            *(
                index
                for index in range(1, maximum_index)
                if shares[index] + 1 < shares[maximum_index]
            ),
        ]
        shares[rng.choice(eligible)] += 1

    rng.shuffle(shares)
    _assert_invariants(shares, total_amount)
    return RedPacketAllocation(tuple(shares), has_empty)


def _validate(
    player_count: int,
    total_amount: int,
    empty_probability_percent: int,
) -> None:
    if (
        isinstance(player_count, bool)
        or not isinstance(player_count, int)
        or not 2 <= player_count <= 50
    ):
        raise ValueError("红包人数必须是 2 至 50 的整数")
    if (
        isinstance(total_amount, bool)
        or not isinstance(total_amount, int)
        or not player_count <= total_amount <= 99999
    ):
        raise ValueError("红包总金额必须是人数至 99999 的整数")
    if (
        isinstance(empty_probability_percent, bool)
        or not isinstance(empty_probability_percent, int)
        or not 0 <= empty_probability_percent <= 30
    ):
        raise ValueError("空包概率必须是 0 至 30 的整数")


def _assert_invariants(shares: list[int], total_amount: int) -> None:
    if sum(shares) != total_amount:
        raise RuntimeError("红包份额总额不一致")
    if shares.count(0) > 1:
        raise RuntimeError("红包空包数量超过一个")
    if shares.count(min(shares)) != 1 or shares.count(max(shares)) != 1:
        raise RuntimeError("红包最大值或最小值不唯一")
