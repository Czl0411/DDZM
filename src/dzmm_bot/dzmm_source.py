import hashlib

from .models import ChatMessage


DEFAULT_SELECTORS = {
    "message_item": "div.pt-10.pb-4.px-2.flex-1.min-h-0.overflow-y-auto.overflow-x-hidden.relative > div > div",
    "sender": ".text-xs.font-medium.text-muted-foreground span",
    "message_text": "span.whitespace-pre-wrap.break-words.w-full, [class*='whitespace-pre-wrap']",
    "self_message": ".items-end,.justify-end,.ml-auto",
}

READ_MESSAGES_SCRIPT = """
(selectors) => [...document.querySelectorAll(selectors.message_item)].slice(-50).map((element, position) => {
  const texts = [...element.querySelectorAll(selectors.message_text)]
    .map((node) => node.innerText.trim()).filter(Boolean);
  return {
    source_index: element.getAttribute('data-index') || '',
    position,
    sender: element.querySelector(selectors.sender)?.innerText?.trim() || '',
    text: texts[texts.length - 1] || '',
    is_self: Boolean(element.querySelector(selectors.self_message)),
  };
})
"""


class DzmmMessageSource:
    def __init__(self, page, group_key: str = "main", selectors: dict[str, str] | None = None):
        self._page = page
        self._group_key = group_key
        self._selectors = {**DEFAULT_SELECTORS, **(selectors or {})}

    def read_new(self) -> list[ChatMessage]:
        messages = []
        for row in self._page.evaluate(READ_MESSAGES_SCRIPT, self._selectors):
            if row.get("is_self"):
                continue
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            sender = str(row.get("sender") or "").strip()
            source_index = str(row.get("source_index") or "").strip()
            messages.append(ChatMessage(self._message_id(source_index, row, sender, text), sender, text))
        return messages

    def _message_id(self, source_index: str, row: dict, sender: str, text: str) -> str:
        if source_index:
            return f"{self._group_key}:{source_index}"
        fallback = "|".join((self._group_key, str(row.get("position", "")), sender, text))
        return f"{self._group_key}:fallback:{hashlib.sha256(fallback.encode()).hexdigest()[:24]}"
