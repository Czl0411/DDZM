from random import Random

import pytest

from dzmm_bot.core.red_packet import generate_red_packet_allocation


class StubRandom:
    def __init__(self, roll: int = 99) -> None:
        self.roll = roll

    def randrange(self, stop: int) -> int:
        assert stop == 100
        return self.roll

    def choice(self, values):
        return values[-1]

    def shuffle(self, values) -> None:
        values.reverse()


def assert_allocation_invariants(result, player_count: int, total_amount: int):
    assert len(result.shares) == player_count
    assert sum(result.shares) == total_amount
    assert all(isinstance(amount, int) and amount >= 0 for amount in result.shares)
    assert result.shares.count(0) <= 1
    assert result.shares.count(min(result.shares)) == 1
    assert result.shares.count(max(result.shares)) == 1


def test_five_players_five_coins_forces_one_empty_and_unique_extrema():
    result = generate_red_packet_allocation(5, 5, 5, StubRandom())

    assert sorted(result.shares) == [0, 1, 1, 1, 2]
    assert result.has_empty is True
    assert_allocation_invariants(result, 5, 5)


@pytest.mark.parametrize(("players", "total"), [(2, 2), (3, 3), (5, 9)])
def test_low_totals_force_empty(players, total):
    result = generate_red_packet_allocation(players, total, 0, StubRandom())

    assert result.has_empty is True
    assert result.shares.count(0) == 1
    assert_allocation_invariants(result, players, total)


def test_configured_probability_controls_optional_empty_share():
    with_empty = generate_red_packet_allocation(5, 10, 5, StubRandom(4))
    without_empty = generate_red_packet_allocation(5, 10, 5, StubRandom(5))

    assert with_empty.has_empty is True
    assert without_empty.has_empty is False
    assert_allocation_invariants(with_empty, 5, 10)
    assert_allocation_invariants(without_empty, 5, 10)


def test_generated_allocations_preserve_sum_and_unique_extrema():
    for players in (2, 3, 5, 50):
        for total in (players, max(players + 1, players * 2), 99999):
            result = generate_red_packet_allocation(players, total, 5, Random(7))

            assert_allocation_invariants(result, players, total)
            assert result.has_empty is (
                (players == 2 and total == 2)
                or (players >= 3 and total < players * 2)
                or result.shares.count(0) == 1
            )


def test_seeded_random_source_reproduces_share_order():
    first = generate_red_packet_allocation(8, 80, 5, Random(31))
    second = generate_red_packet_allocation(8, 80, 5, Random(31))

    assert first == second


@pytest.mark.parametrize(
    ("players", "total", "probability"),
    [
        (True, 5, 5),
        (1, 5, 5),
        (51, 51, 5),
        (5, True, 5),
        (5, 4, 5),
        (5, 100000, 5),
        (5, 5, True),
        (5, 5, -1),
        (5, 5, 31),
    ],
)
def test_invalid_allocation_parameters_are_rejected(players, total, probability):
    with pytest.raises(ValueError):
        generate_red_packet_allocation(
            players, total, probability, StubRandom()
        )
