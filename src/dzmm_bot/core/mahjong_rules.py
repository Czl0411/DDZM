"""Small, deterministic helpers for four-player riichi mahjong.

Tile ids use the common 136-tile layout: ``tile_id // 4`` is the 34-tile
type.  The scoring calculation is delegated to the maintained ``mahjong``
package; room flow and money settlement remain in our own authoritative
server.
"""

from dataclasses import dataclass

from mahjong.agari import Agari
from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig, HandConstants, OptionalRules
from mahjong.meld import Meld
from mahjong.tile import TilesConverter


RED_FIVES = {16, 52, 88}
TERMINAL_HONOR_TYPES = {0, 8, 9, 17, 18, 26, *range(27, 34)}
WIND_TYPES = tuple(range(27, 31))

_HONORS = ("东", "南", "西", "北", "白", "发", "中")
_YAKU_ZH = {
    "Menzen Tsumo": "门前清自摸和",
    "Riichi": "立直",
    "Double Riichi": "两立直",
    "Ippatsu": "一发",
    "Pinfu": "平和",
    "Tanyao": "断幺九",
    "Iipeiko": "一杯口",
    "Ryanpeikou": "二杯口",
    "Yakuhai (wind of place)": "自风牌",
    "Yakuhai (wind of round)": "场风牌",
    "Yakuhai (haku)": "白",
    "Yakuhai (hatsu)": "发",
    "Yakuhai (chun)": "中",
    "Chiitoitsu": "七对子",
    "Toitoi": "对对和",
    "San Ankou": "三暗刻",
    "Sanshoku Doujun": "三色同顺",
    "Sanshoku Doukou": "三色同刻",
    "Ittsu": "一气通贯",
    "Chantai": "混全带幺九",
    "Junchan": "纯全带幺九",
    "Honroutou": "混老头",
    "Shou Sangen": "小三元",
    "Honitsu": "混一色",
    "Chinitsu": "清一色",
    "Sankantsu": "三杠子",
    "Rinshan Kaihou": "岭上开花",
    "Chankan": "抢杠",
    "Haitei Raoyue": "海底摸月",
    "Houtei Raoyui": "河底捞鱼",
    "Dora": "宝牌",
    "Aka Dora": "赤宝牌",
    "Ura Dora": "里宝牌",
    "Nagashi Mangan": "流局满贯",
    "Kokushi Musou": "国士无双",
    "Kokushi Musou 13 Men": "国士无双十三面",
    "Suu Ankou": "四暗刻",
    "Suu Ankou Tanki": "四暗刻单骑",
    "Daisangen": "大三元",
    "Shousuushii": "小四喜",
    "Daisuushii": "大四喜",
    "Tsuuiisou": "字一色",
    "Chinroutou": "清老头",
    "Ryuuiisou": "绿一色",
    "Chuuren Poutou": "九莲宝灯",
    "Junsei Chuuren Poutou": "纯正九莲宝灯",
    "Suu Kantsu": "四杠子",
    "Tenhou": "天和",
    "Chiihou": "地和",
}


@dataclass(frozen=True)
class HandContext:
    tsumo: bool = False
    riichi: bool = False
    double_riichi: bool = False
    ippatsu: bool = False
    rinshan: bool = False
    chankan: bool = False
    haitei: bool = False
    houtei: bool = False
    tenhou: bool = False
    chiihou: bool = False
    player_wind: int = 28
    round_wind: int = 27
    honba: int = 0
    riichi_sticks: int = 0
    dora_indicators: tuple[int, ...] = ()
    ura_indicators: tuple[int, ...] = ()


@dataclass(frozen=True)
class HandValue:
    han: int | None
    fu: int | None
    yaku: tuple[str, ...]
    main: int
    additional: int
    total: int
    limit: str | None
    error: str | None = None


def tile_type(tile: int) -> int:
    if type(tile) is not int or not 0 <= tile < 136:
        raise ValueError("无效麻将牌")
    return tile // 4


def tile_name(tile: int) -> str:
    kind = tile_type(tile)
    if tile in RED_FIVES:
        return ("赤五万", "赤五筒", "赤五索")[(kind // 9)]
    if kind < 27:
        number = kind % 9 + 1
        suit = ("万", "筒", "索")[kind // 9]
        return f"{number}{suit}"
    return _HONORS[kind - 27]


def tile_sort_key(tile: int) -> tuple[int, bool, int]:
    return tile_type(tile), tile not in RED_FIVES, tile


def _first_tiles_by_type(hand: list[int]) -> dict[int, list[int]]:
    result: dict[int, list[int]] = {}
    for tile in sorted(hand, key=tile_sort_key):
        result.setdefault(tile_type(tile), []).append(tile)
    return result


def chi_choices(hand: list[int], discarded: int) -> list[list[int]]:
    kind = tile_type(discarded)
    if kind >= 27:
        return []
    number = kind % 9
    suit_start = kind - number
    by_type = _first_tiles_by_type(hand)
    choices: list[list[int]] = []
    for start in (number - 2, number - 1, number):
        if not 0 <= start <= 6:
            continue
        needed = [suit_start + offset for offset in range(start, start + 3)]
        needed.remove(kind)
        if all(by_type.get(item) for item in needed):
            choices.append([by_type[item][0] for item in needed])
    return choices


def pon_choices(hand: list[int], discarded: int) -> list[list[int]]:
    matches = _first_tiles_by_type(hand).get(tile_type(discarded), [])
    return [matches[:2]] if len(matches) >= 2 else []


def open_kan_choices(hand: list[int], discarded: int) -> list[list[int]]:
    matches = _first_tiles_by_type(hand).get(tile_type(discarded), [])
    return [matches[:3]] if len(matches) >= 3 else []


def concealed_kan_types(hand: list[int]) -> set[int]:
    return {kind for kind, matches in _first_tiles_by_type(hand).items() if len(matches) == 4}


def _meld(value: dict) -> Meld:
    kind = value["kind"]
    meld_type = {
        "chi": Meld.CHI,
        "pon": Meld.PON,
        "kan": Meld.KAN,
        "ankan": Meld.KAN,
        "kakan": Meld.SHOUMINKAN,
    }[kind]
    return Meld(
        meld_type=meld_type,
        tiles=value["tiles"],
        opened=value.get("open", kind != "ankan"),
        called_tile=value.get("called_tile"),
        from_who=value.get("from"),
    )


def is_closed(melds: list[dict]) -> bool:
    return not any(meld.get("open", meld.get("kind") != "ankan") for meld in melds)


def _unused_tile_id(kind: int, used: set[int]) -> int | None:
    for tile in range(kind * 4, kind * 4 + 4):
        if tile not in used:
            return tile
    return None


def waits(hand: list[int], melds: list[dict]) -> set[int]:
    """Return structurally winning tile types; a yaku is not required."""
    used = set(hand)
    for meld in melds:
        used.update(meld["tiles"])
    result: set[int] = set()
    for kind in range(34):
        candidate = _unused_tile_id(kind, used)
        if candidate is None:
            continue
        counts = TilesConverter.to_34_array([*hand, candidate])
        if Agari.is_agari(counts):
            result.add(kind)
    return result


def hand_value(
    concealed: list[int],
    win_tile: int,
    melds: list[dict],
    context: HandContext,
) -> HandValue:
    if win_tile not in concealed:
        raise ValueError("和牌必须包含获胜牌")
    options = OptionalRules(
        has_open_tanyao=True,
        has_aka_dora=True,
        has_double_yakuman=True,
        kazoe_limit=HandConstants.KAZOE_LIMITED,
    )
    config = HandConfig(
        is_tsumo=context.tsumo,
        is_riichi=context.riichi,
        is_daburu_riichi=context.double_riichi,
        is_ippatsu=context.ippatsu,
        is_rinshan=context.rinshan,
        is_chankan=context.chankan,
        is_haitei=context.haitei,
        is_houtei=context.houtei,
        is_tenhou=context.tenhou,
        is_chiihou=context.chiihou,
        player_wind=context.player_wind,
        round_wind=context.round_wind,
        tsumi_number=0,
        kyoutaku_number=0,
        options=options,
    )
    response = HandCalculator.estimate_hand_value(
        concealed,
        win_tile,
        melds=[_meld(value) for value in melds],
        dora_indicators=context.dora_indicators,
        ura_dora_indicators=context.ura_indicators if context.riichi else (),
        config=config,
    )
    if response.error or response.cost is None:
        return HandValue(None, None, (), 0, 0, 0, None, response.error or "不能和牌")
    yaku = tuple(_YAKU_ZH.get(str(value), str(value)) for value in response.yaku or ())
    return HandValue(
        response.han,
        response.fu,
        yaku,
        int(response.cost["main"]),
        int(response.cost["additional"]),
        int(response.cost["total"]),
        response.cost.get("yaku_level"),
    )


def is_terminal_or_honor(tile: int) -> bool:
    return tile_type(tile) in TERMINAL_HONOR_TYPES


def distinct_terminal_honors(hand: list[int]) -> int:
    return len({tile_type(tile) for tile in hand if is_terminal_or_honor(tile)})
