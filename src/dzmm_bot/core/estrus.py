"""/凿 发情值玩法的高潮文字生成：性别分路 prompt 与兜底文案。

性别取 users.gender（male / female / unknown），AI 生成只带昵称与性别、
不带入群聊上下文（与 dzmm_nuo 的 generate_heat_climax 差异点，用户拍板）。
AI 失败时按性别从兜底文案库随机选一条，保证必有输出。
"""

SYSTEM_MALE = (
    "你是摸鱼公司群聊的旁白，为「凿」玩法撰写发情值爆表的高潮片段。"
    "目标角色是一名男性员工。请用第三人称写一段 80~150 字的夸张、"
    "露骨的色情化高潮描写，贴合群聊摸鱼公司的搞笑氛围。"
    "直接输出正文，不要标题、不要引号、不要解释。"
)

SYSTEM_FEMALE = (
    "你是摸鱼公司群聊的旁白，为「凿」玩法撰写发情值爆表的高潮片段。"
    "目标角色是一名女性员工。请用第三人称写一段 80~150 字的夸张、"
    "露骨的色情化高潮描写，贴合群聊摸鱼公司的搞笑氛围。"
    "直接输出正文，不要标题、不要引号、不要解释。"
)

SYSTEM_UNKNOWN = (
    "你是摸鱼公司群聊的旁白，为「凿」玩法撰写发情值爆表的高潮片段。"
    "目标角色性别未知。请用第三人称写一段 80~150 字的夸张、暧昧、"
    "色情化的高潮描写，贴合群聊摸鱼公司的搞笑氛围，避免性别化措辞。"
    "直接输出正文，不要标题、不要引号、不要解释。"
)

_SYSTEMS = {
    "male": SYSTEM_MALE,
    "female": SYSTEM_FEMALE,
    "unknown": SYSTEM_UNKNOWN,
}

_GENDER_LABELS = {
    "male": "男",
    "female": "女",
    "unknown": "未知",
}

_FALLBACKS = {
    "male": (
        "{name}只觉一股热流从尾椎直冲天灵盖，浑身绷紧，喉结上下滚动，"
        "最后整个人瘫在工位上，半天憋出一句：「我……我还可以再被凿。」",
        "{name}被凿中要害，呼吸瞬间乱了节奏，手指死死抠住键盘，"
        "屏幕上的代码全都糊成了一片桃色， office 空调都压不住他发烫的脸。",
        "{name}膝盖一软扶住了饮水机，耳根红透，声音抖得不成样子："
        "「谁、谁再凿我一下试试……」全公司都听出了这句口是心非。",
    ),
    "female": (
        "{name}浑身一颤，脸颊烧得通红，扶着桌沿才勉强站稳，"
        "半晌才抬起水汪汪的眼睛瞪过来：「都、都怪你凿我……」声音软得不像话。",
        "{name}被凿的瞬间轻轻哼了一声，慌忙捂住嘴，可泛红的耳尖和湿润的眼角"
        "早把一切都出卖了，整个人像煮熟的虾子蜷在椅子上。",
        "{name}只觉得脑中一片空白，双腿发软，攥着裙角扭捏了半天，"
        "才小声嘟囔：「发情值满了……都怪你。」说完自己先红透了脸。",
    ),
    "unknown": (
        "{name}被凿得浑身一激灵，体温瞬间飙升高潮，"
        "趴在工位上大口喘气，半天才缓过劲来：「这、这也太猛了……」",
        "{name}只觉眼前一白，浑身酥麻，扶着墙才没滑下去，"
        "缓过来时整张脸红得能滴血，冲空气虚弱地挥了挥拳。",
        "{name}像被电流击中，僵在原地三秒，随后腿一软瘫回椅子，"
        "眼神迷离地喃喃：「发情值……满了啊。」",
    ),
}


def build_climax_messages(name: str, gender: str) -> tuple[str, str]:
    """按性别返回 (system_prompt, user_content)，不含群聊上下文。"""
    key = gender if gender in _SYSTEMS else "unknown"
    label = _GENDER_LABELS[key]
    system = _SYSTEMS[key]
    user = f"目标角色：{name}（性别：{label}）。请输出这段高潮描写。"
    return system, user


def fallback_climax_text(name: str, gender: str, rng) -> str:
    key = gender if gender in _FALLBACKS else "unknown"
    return rng.choice(_FALLBACKS[key]).format(name=name)
