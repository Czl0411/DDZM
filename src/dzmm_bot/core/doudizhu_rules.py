"""Pure card classification and suggestions for classic three-player doudizhu."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations


@dataclass(frozen=True)
class Pattern:
    kind: str
    high: int
    length: int
    cards: tuple[int, ...]


def rank(card: int) -> int:
    if type(card) is not int or not 0 <= card < 54:
        raise ValueError("无效的牌")
    return card // 4 + 3 if card < 52 else card - 36


def _validated(cards):
    values = tuple(cards)
    for card in values:
        rank(card)
    if len(set(values)) != len(values):
        raise ValueError("不能重复出同一张牌")
    return tuple(sorted(values))


def _runs(counts, copies, minimum):
    for low in range(3, 15):
        for high in range(low, 15):
            if counts.get(high, 0) < copies:
                break
            if high - low + 1 >= minimum:
                yield tuple(range(low, high + 1))


def patterns(cards: tuple[int, ...]) -> tuple[Pattern, ...]:
    values = _validated(cards)
    counts = Counter(rank(c) for c in values)
    n = len(values)
    result = []

    def add(kind, high, length=1):
        result.append(Pattern(kind, high, length, values))

    if n == 0:
        return ()
    if n == 2 and set(counts) == {16, 17}:
        add('rocket', 17)
    if len(counts) == 1 and n <= 4:
        add({1: 'single', 2: 'pair', 3: 'triple', 4: 'bomb'}[n], max(counts))
    for high, count in counts.items():
        other = counts.copy()
        del other[high]
        if count == 3:
            if n == 4:
                add('triple_single', high)
            if n == 5 and sorted(other.values()) == [2]:
                add('triple_pair', high)
        if count == 4:
            if n == 6 and not {16, 17} <= set(other):
                add('four_single', high)
            if n == 8 and sorted(other.values()) == [2, 2]:
                add('four_pair', high)
    for copies, minimum, kind in ((1, 5, 'straight'), (2, 3, 'pair_straight'), (3, 2, 'airplane')):
        for body in _runs(counts, copies, minimum):
            length = len(body)
            if n == copies * length and all(counts[r] == copies for r in body):
                add(kind, body[-1], length)
            if copies != 3 or any(counts[r] != 3 for r in body):
                continue
            wings = {r: count for r, count in counts.items() if r not in body}
            if n == length * 4 and max(wings.values(), default=0) < 4 and not {16, 17} <= wings.keys():
                add('airplane_single', body[-1], length)
            if n == length * 5 and len(wings) == length and all(count == 2 for count in wings.values()):
                add('airplane_pair', body[-1], length)
    return tuple(result)


def _beats(play, previous):
    if previous is None:
        return True
    if previous.kind == 'rocket':
        return False
    if play.kind == 'rocket':
        return True
    if play.kind == 'bomb' and previous.kind != 'bomb':
        return True
    return (play.kind == previous.kind and play.length == previous.length
            and len(play.cards) == len(previous.cards) and play.high > previous.high)


def choose_pattern(cards: tuple[int, ...], previous: Pattern | None) -> Pattern:
    choices = [p for p in patterns(cards) if _beats(p, previous)]
    if not choices:
        raise ValueError("牌型不合法或不能压过上一手")
    return (min if previous else max)(choices, key=lambda p: (p.high, p.length, p.kind))


def _single_wings(available, size, prefix=()):
    """Enumerate bounded rank multisets, not physical-card subsets."""
    if size == 0:
        if not {16, 17} <= set(prefix):
            yield prefix
        return
    if not available:
        return
    (value, count), *rest = available
    for take in range(min(count, size, 3) + 1):
        yield from _single_wings(rest, size - take, prefix + (value,) * take)


def legal_plays(hand: tuple[int, ...], previous: Pattern | None) -> tuple[Pattern, ...]:
    values = _validated(hand)
    if len(values) > 20:
        raise ValueError("手牌不能超过 20 张")
    groups = defaultdict(list)
    for card in values:
        groups[rank(card)].append(card)
    counts = {r: len(group) for r, group in groups.items()}
    candidates = set()

    def add(ranks):
        used = Counter(ranks)
        candidates.add(tuple(sorted(c for r, count in used.items() for c in groups[r][:count])))

    for r, count in counts.items():
        for size in range(1, count + 1):
            add((r,) * size)
        if count >= 3:
            for wing, number in counts.items():
                if wing != r:
                    add((r,) * 3 + (wing,))
                    if number >= 2:
                        add((r,) * 3 + (wing,) * 2)
    if 16 in counts and 17 in counts:
        add((16, 17))
    bodies = []
    for copies, minimum in ((1, 5), (2, 3), (3, 2)):
        for body in _runs(counts, copies, minimum):
            ranks = tuple(r for r in body for _ in range(copies))
            add(ranks)
            if copies == 3:
                bodies.append((body, ranks, len(body)))
    for r, count in counts.items():
        if count == 4:
            bodies.append(((r,), (r,) * 4, 2))
    for body, ranks, wing_count in bodies:
        remaining = [(r, count) for r, count in counts.items() if r not in body]
        for wings in _single_wings(remaining, wing_count):
            add(ranks + wings)
        pairs = [r for r, count in remaining if count >= 2]
        for wings in combinations(pairs, wing_count):
            add(ranks + tuple(r for r in wings for _ in range(2)))
    result = set()
    for candidate in candidates:
        if previous is None:
            result.update(patterns(candidate))
        else:
            choices = [p for p in patterns(candidate) if _beats(p, previous)]
            if choices:
                result.add(min(choices, key=lambda p: (p.high, p.length, p.kind)))
    return tuple(sorted(result, key=lambda p: ({'bomb': 1, 'rocket': 2}.get(p.kind, 0), p.high, len(p.cards), p.cards, p.kind)))
