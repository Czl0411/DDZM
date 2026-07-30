import json

from .models import ChatMessage


DEFAULT_SELECTORS = {
    "message_item": "div.pt-10.pb-4.px-2.flex-1.min-h-0.overflow-y-auto.overflow-x-hidden.relative > div > div",
    "sender": ".text-xs.font-medium.text-muted-foreground span",
    "message_text": "span.whitespace-pre-wrap.break-words.w-full, [class*='whitespace-pre-wrap']",
    "self_message": ".items-end,.justify-end,.ml-auto",
    "message_id": "",
}

READ_MESSAGES_SCRIPT = """
(selectors) => {
const rows = [...document.querySelectorAll(selectors.message_item)].map((element, position) => {
  const texts = [...element.querySelectorAll(selectors.message_text)]
    .map((node) => node.innerText.trim()).filter(Boolean);
  const identityNode = selectors.message_id ? element.querySelector(selectors.message_id) : null;
  return {
    source_index: element.getAttribute('data-message-id') || element.getAttribute('data-id') || element.getAttribute('data-index') || identityNode?.getAttribute('data-message-id') || identityNode?.getAttribute('data-id') || identityNode?.getAttribute('datetime') || identityNode?.innerText?.trim() || '',
    position,
    sender: element.querySelector(selectors.sender)?.innerText?.trim() || '',
    text: texts[texts.length - 1] || '',
    is_self: Boolean(element.querySelector(selectors.self_message)),
  };
});
const occurrences = new Map();
for (const row of rows) {
  const base = JSON.stringify([row.sender, row.text]);
  const occurrence = (occurrences.get(base) || 0) + 1;
  occurrences.set(base, occurrence);
  row.fallback_key = JSON.stringify([row.sender, row.text, occurrence]);
}
return rows.slice(-50);
}
"""


class DzmmMessageSource:
    def __init__(self, page, group_key: str = "main", selectors: dict[str, str] | None = None):
        self._page = page
        self._group_key = group_key
        self._selectors = {**DEFAULT_SELECTORS, **(selectors or {})}

    def read_new(self) -> list[ChatMessage]:
        messages = []
        fallback_occurrences: dict[str, int] = {}
        for row in self._page.evaluate(READ_MESSAGES_SCRIPT, self._selectors):
            if row.get("is_self"):
                continue
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            sender = str(row.get("sender") or "").strip()
            source_index = str(row.get("source_index") or "").strip()
            if source_index:
                message_id = f"{self._group_key}:stable:{source_index}"
            else:
                fallback_key = str(row.get("fallback_key") or "")
                if not fallback_key:
                    base = json.dumps([sender, text], ensure_ascii=False, separators=(",", ":"))
                    occurrence = fallback_occurrences.get(base, 0) + 1
                    fallback_occurrences[base] = occurrence
                    fallback_key = json.dumps([sender, text, occurrence], ensure_ascii=False, separators=(",", ":"))
                message_id = f"{self._group_key}:fallback:{fallback_key}"
            messages.append(ChatMessage(message_id, sender, text))
        return messages
