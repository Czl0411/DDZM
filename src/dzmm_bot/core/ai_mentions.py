BOT_MENTION_PREFIX = "@总监事"
BOT_PLATFORM_LABEL = "「Bot」"


def normalize_ai_mention(content: str) -> str:
    value = content.strip()
    if not value.startswith(BOT_MENTION_PREFIX):
        return value
    value = value[len(BOT_MENTION_PREFIX) :]
    if value.startswith(BOT_PLATFORM_LABEL):
        value = value[len(BOT_PLATFORM_LABEL) :]
    return value.strip()
