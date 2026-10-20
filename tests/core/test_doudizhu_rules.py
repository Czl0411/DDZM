from collections import Counter
from itertools import combinations
import random

import pytest

from dzmm_bot.core.doudizhu_rules import choose_pattern, legal_plays, patterns, rank


def cards(*ranks):
    counts = Counter()
    result = []
    for value in ranks:
        result.append((value - 3) * 4 + counts[value] if value < 16 else value + 36)
        counts[value] += 1
    return tuple(result)


@pytest.mark.parametrize(('values', 'kind'), [
    ([3], 'single'), ([4, 4], 'pair'), ([5, 5, 5], 'triple'),
    ([6, 6, 6, 7], 'triple_single'), ([6, 6, 6, 7, 7], 'triple_pair'),
    ([3, 4, 5, 6, 7], 'straight'), ([3, 3, 4, 4, 5, 5], 'pair_straight'),
    ([3, 3, 3, 4, 4, 4], 'airplane'),
    ([3, 3, 3, 4, 4, 4, 5, 5], 'airplane_single'),
    ([3, 3, 3, 4, 4, 4, 5, 5, 6, 6], 'airplane_pair'),
    ([3, 3, 3, 3, 4, 4], 'four_single'),
    ([3, 3, 3, 3, 4, 4, 5, 5], 'four_pair'),
    ([3, 3, 3, 3], 'bomb'), ([16, 17], 'rocket'),
    ([10, 11, 12, 13, 14], 'straight'),
])
def test_all_patterns_and_boundaries(values, kind):
    assert choose_pattern(cards(*values), None).kind == kind


@pytest.mark.parametrize('values', [
    [], [3, 4, 5, 6], [11, 12, 13, 14, 15], [13, 14, 15, 16, 17],
    [3, 3, 4, 4], [3, 3, 3, 5, 5, 5],
    [3, 3, 3, 4, 4, 4, 16, 17],
    [3, 3, 3, 4, 4, 4, 5, 5, 5, 5],
    [3, 3, 3, 3, 16, 17], [3, 3, 3, 3, 4, 4, 4, 4],
    [3, 3, 3, 3, 4, 4, 4, 5],
])
def test_invalid_shapes(values):
    with pytest.raises(ValueError):
        choose_pattern(cards(*values), None)


def test_wings_and_ambiguous_airplanes():
    hand = cards(3, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 6)
    wings = [p for p in patterns(hand) if p.kind == 'airplane_single']
    assert {p.high for p in wings} == {5, 6}
    previous = choose_pattern(cards(3, 3, 3, 4, 4, 4, 5, 5, 5, 7, 8, 9), None)
    assert choose_pattern(hand, previous).high == 6
    assert choose_pattern(hand, None).high == 6


@pytest.mark.parametrize('bad', [(-1,), (54,), (0, 0), (True,), ('3',), (1.0,)])
def test_illegal_card_ids_and_duplicates(bad):
    with pytest.raises(ValueError):
        patterns(bad)


def test_comparison_requires_same_type_and_length():
    pair = choose_pattern(cards(3, 3), None)
    assert choose_pattern(cards(4, 4), pair).high == 4
    for values in ([3, 3], [17], [4, 4, 4]):
        with pytest.raises(ValueError):
            choose_pattern(cards(*values), pair)
    bomb = choose_pattern(cards(4, 4, 4, 4), pair)
    assert choose_pattern(cards(16, 17), bomb).kind == 'rocket'
    with pytest.raises(ValueError):
        choose_pattern(cards(3, 3, 3, 3), bomb)
    with pytest.raises(ValueError):
        choose_pattern(cards(4, 5, 6, 7, 8, 9), choose_pattern(cards(3, 4, 5, 6, 7), None))


def test_suggestions_are_legal_subsets():
    rng = random.Random(91)
    previous = choose_pattern(cards(3, 3), None)
    for _ in range(20):
        hand = tuple(rng.sample(range(54), 20))
        result = legal_plays(hand, previous)
        assert result == legal_plays(hand, previous)
        for play in result:
            assert set(play.cards) <= set(hand)
            assert choose_pattern(play.cards, previous) == play
            assert play.kind in ('pair', 'bomb', 'rocket')


def test_suggestions_cover_every_rank_shape_in_small_hand():
    hand = cards(3, 3, 3, 4, 4, 4, 5, 5, 6, 7, 16, 17)
    expected = set()
    for size in range(1, len(hand) + 1):
        for subset in combinations(hand, size):
            for play in patterns(subset):
                expected.add((play.kind, play.high, tuple(sorted(rank(c) for c in subset))))
    actual = {(p.kind, p.high, tuple(sorted(rank(c) for c in p.cards))) for p in legal_plays(hand, None)}
    assert actual == expected
