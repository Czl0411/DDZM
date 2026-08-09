BOT_GROUP_MAX_CHARS = 1000
BOT_GROUP_MAX_NEWLINES = 10


def requires_bot_group_sender(text: str) -> bool:
    return (
        len(text) > BOT_GROUP_MAX_CHARS
        or text.count("\n") > BOT_GROUP_MAX_NEWLINES
    )
