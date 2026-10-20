"""Curated, local words and exact-match normalization for draw-and-guess."""

from dataclasses import dataclass

from .chinese_input import traditional_to_simplified


@dataclass(frozen=True)
class Word:
    id: str
    answer: str
    aliases: tuple[str, ...] = ()


_ANSWERS = (
    "苹果", "香蕉", "西瓜", "草莓", "葡萄", "菠萝", "橘子", "桃子", "梨", "樱桃",
    "猫", "狗", "兔子", "熊猫", "长颈鹿", "大象", "狮子", "老虎", "猴子", "企鹅",
    "自行车", "汽车", "公交车", "火车", "飞机", "轮船", "摩托车", "出租车", "救护车", "消防车",
    "雨伞", "帽子", "眼镜", "手表", "书包", "钥匙", "剪刀", "牙刷", "杯子", "台灯",
    "房子", "学校", "医院", "超市", "公园", "桥", "城堡", "灯塔", "帐篷", "游乐园",
    "太阳", "月亮", "星星", "彩虹", "云朵", "闪电", "雪人", "火山", "海浪", "树",
    "跑步", "游泳", "跳舞", "唱歌", "拍照", "钓鱼", "做饭", "睡觉", "刷牙", "踢足球",
    "医生", "老师", "警察", "厨师", "画家", "宇航员", "消防员", "司机", "农民", "魔术师",
    "钢琴", "吉他", "小提琴", "鼓", "麦克风", "篮球", "足球", "羽毛球", "风筝", "滑板",
    "蛋糕", "冰淇淋", "汉堡", "披萨", "面条", "饺子", "棒棒糖", "爆米花", "巧克力", "三明治",
    "机器人", "火箭", "皇冠", "礼物", "气球", "蜡烛", "闹钟", "电话", "电脑", "相机",
)

WORDS = tuple(
    Word(f"w{index:03d}", answer, ("脚踏车",) if answer == "自行车" else ())
    for index, answer in enumerate(_ANSWERS, 1)
)
_BY_ID = {word.id: word for word in WORDS}


def normalize_guess(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("答案必须是文字")
    return traditional_to_simplified(text).strip().casefold()


def word_by_id(word_id: str) -> Word:
    try:
        return _BY_ID[word_id]
    except KeyError as error:
        raise ValueError("词语不存在") from error


def word_matches(word_id: str, text: str) -> bool:
    word = word_by_id(word_id)
    candidate = normalize_guess(text)
    return candidate in {normalize_guess(word.answer), *(normalize_guess(alias) for alias in word.aliases)}


def validate_candidates(candidates: list[str], used_ids: set[str]) -> list[str]:
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError("每轮必须提供三个候选词")
    if len(set(candidates)) != 3:
        raise ValueError("候选词不能重复")
    if any(word_id not in _BY_ID for word_id in candidates):
        raise ValueError("候选词不存在")
    if set(candidates) & set(used_ids):
        raise ValueError("候选词已经在本局使用")
    return list(candidates)
