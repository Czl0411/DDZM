"""Offline opponent profiles and ordinary V3 decks for queue fallback."""
from copy import deepcopy
from uuid import uuid4

from . import mistrealm_v3_state as v3
from .mistrealm_v3_cards import STARTER_DECKS
from .mistrealm_story import drive

MATCH_WAIT_MS = 10_000
AVATAR_COUNT = 32
NAMES = (
    '雾里听风', '迟来的月光', '渡鸦来信', '半杯热茶', '雪落无声', '城南旧事', '晚风过境', '星河拾荒者',
    '青灯夜读', '白榆', '山海有归期', '月下行舟', '灰羽', '不眠旅人', '拾光者', '北岸来客',
    '猫与旧书', '松间明月', '霜叶', '落日邮差', '微雨归舟', '三分糖', '听雨客', '远山青',
    '一枕星河', '林间晚照', '暮色温柔', '小岛来信', '风中余烬', '白塔守望', '长街灯火', '小满',
    '旧港灯塔', '云边散步', '沉默的橡树', '余温', '星屿', '霜桥', '风铃与猫', '雾海寻灯',
    '月亮迟到', '纸船', '一颗松果', '青石巷', '听雪', '橘子汽水', '薄荷晚风', '山川慢慢',
    '借一盏灯', '花间酒', '候鸟归来', '夜航星', '落叶有声', '南窗', '长夜未央', '墨色黎明',
    '半夏微凉', '不落的星', '镜湖过客', '执灯人', '拾起一片海', '长风入林', '晚安群山', '归途有光',
)


def new_match(uid, player_deck, now_ms, rng):
    state = v3.new_state(uid, player_deck, now_ms)
    state.update(mode='bot', bot=dict(
        name=rng.choice(NAMES), avatar=f'../assets/bots/lorelei-{rng.randrange(1, AVATAR_COUNT+1):02}.svg',
    ))
    state = v3.apply_action(state, 1, 'join', dict(
        uid=f'mistrealm-bot-{uuid4()}', deck=deepcopy(rng.choice(STARTER_DECKS)),
    ), now_ms, rng)
    state = v3.apply_action(state, 0, 'lock', {}, now_ms, rng)
    state = v3.apply_action(state, 1, 'lock', {}, now_ms, rng)
    return drive(state, now_ms, rng)


def rematch(state, now_ms, rng):
    """The human already accepted; the bot accepts and locks both existing decks."""
    profile = deepcopy(state['bot'])
    state = v3.apply_action(state, 1, 'rematch', {}, now_ms, rng)
    state.update(mode='bot', bot=profile)
    state = v3.apply_action(state, 0, 'lock', {}, now_ms, rng)
    state = v3.apply_action(state, 1, 'lock', {}, now_ms, rng)
    return drive(state, now_ms, rng)
