import pytest

from mahjong.tile import TilesConverter

from dzmm_bot.core.mahjong_rules import (
    HandContext,
    chi_choices,
    hand_value,
    tile_name,
    waits,
)


def tiles(*, man="", pin="", sou="", honors=""):
    return list(
        TilesConverter.string_to_136_array(
            man=man, pin=pin, sou=sou, honors=honors, has_aka_dora=True,
        )
    )


def test_tile_names_include_red_fives_and_honors():
    assert tile_name(16) == "赤五万"
    assert tile_name(52) == "赤五筒"
    assert tile_name(88) == "赤五索"
    assert tile_name(108) == "东"
    assert tile_name(124) == "白"


def test_chi_choices_use_real_tiles_from_hand():
    hand = tiles(man="1245")
    discard = tiles(man="3")[0]
    choices = chi_choices(hand, discard)
    assert [[tile // 4 for tile in choice] for choice in choices] == [
        [0, 1], [1, 3], [3, 4],
    ]


def test_waits_detect_standard_and_seven_pairs_hands():
    standard = tiles(man="123456", pin="123", sou="123", honors="1")
    assert waits(standard, []) == {27}
    seven_pairs = tiles(man="112233", pin="445566", honors="1")
    assert waits(seven_pairs, []) == {27}


def test_hand_value_uses_standard_riichi_scoring_and_chinese_yaku_names():
    concealed = tiles(man="123456", pin="12355", sou="123")
    winning = next(tile for tile in concealed if tile // 4 == 13)
    value = hand_value(
        concealed,
        winning,
        [],
        HandContext(
            tsumo=True,
            riichi=True,
            player_wind=28,
            round_wind=27,
        ),
    )
    assert value.error is None
    assert value.han >= 2
    assert "立直" in value.yaku
    assert "门前清自摸和" in value.yaku
    assert value.total > 0


def test_open_hand_without_yaku_cannot_win():
    concealed = tiles(man="456", pin="12355", sou="789")
    meld = {
        "kind": "chi",
        "tiles": tiles(man="123"),
        "open": True,
        "called_tile": tiles(man="3")[0],
        "from": 3,
    }
    winning = next(tile for tile in concealed if tile // 4 == 13)
    value = hand_value(
        concealed,
        winning,
        [meld],
        HandContext(player_wind=28, round_wind=27),
    )
    assert value.error == "no_yaku"


def test_two_open_pons_are_included_in_winning_hand_and_scoring():
    # 4567788索 + 碰六索 + 碰六筒, 荣和八索。
    concealed = [84, 88, 92, 96, 97, 100, 101, 102]
    melds = [
        {"kind": "pon", "tiles": [93, 94, 95], "open": True, "called_tile": 95, "from": 3},
        {"kind": "pon", "tiles": [56, 57, 58], "open": True, "called_tile": 58, "from": 3},
    ]
    value = hand_value(concealed, 102, melds, HandContext())
    assert value.error is None
    assert "断幺九" in value.yaku
    assert value.total > 0


def test_chi_meld_is_included_when_scoring_open_tanyao():
    concealed = tiles(man="456", pin="23455", sou="678")
    meld = {"kind": "chi", "tiles": tiles(sou="234"), "open": True, "called_tile": 84, "from": 3}
    value = hand_value(concealed, concealed[-1], [meld], HandContext())
    assert value.error is None
    assert "断幺九" in value.yaku


@pytest.mark.parametrize("kind", ["kan", "ankan", "kakan"])
def test_quad_meld_keeps_all_four_tiles_for_scoring(kind):
    concealed = [84, 88, 92, 96, 97, 100, 101, 102]
    melds = [
        {"kind": kind, "tiles": [4, 5, 6, 7], "open": kind != "ankan", "called_tile": 7, "from": 3},
        {"kind": "pon", "tiles": [56, 57, 58], "open": True, "called_tile": 58, "from": 3},
    ]
    value = hand_value(concealed, 102, melds, HandContext())
    assert value.error is None
    assert "断幺九" in value.yaku
