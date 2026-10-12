from html import escape
from pathlib import Path


def _card_html(payload: dict[str, str]) -> str:
    display_name = escape(payload["display_name"])
    rank_name = escape(payload["rank_name"])
    text = escape(payload["text"]).replace("\n", "<br>")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: transparent; font-family: -apple-system, BlinkMacSystemFont,
  "PingFang SC", "Microsoft YaHei", sans-serif; }}
.card {{ width: 760px; padding: 34px 38px 38px; border: 1px solid #ddd;
  border-radius: 28px; background: #fff; color: #111; }}
.header {{ display: flex; justify-content: space-between; align-items: center;
  gap: 24px; margin-bottom: 30px; }}
.name {{ font-size: 25px; font-weight: 700; }}
.rank {{ font-weight: 600; color: #555; }}
.album {{ flex: none; color: #8b8b8b; font-size: 20px; font-weight: 650; }}
.quote {{ border-left: 5px solid #d9d9d9; padding-left: 22px; font-size: 31px;
  line-height: 1.48; font-weight: 650; overflow-wrap: anywhere; white-space: normal; }}
</style></head><body>
<article class="card">
  <div class="header">
    <div class="name">@{display_name} <span class="rank">【{rank_name}】</span></div>
    <div class="album">黑历史册</div>
  </div>
  <div class="quote">{text}</div>
</article>
</body></html>"""


def render_black_history_card(payload: dict[str, str], output_path: Path) -> None:
    from playwright.sync_api import Error, sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Error:
            browser = playwright.chromium.launch(headless=True, channel="chrome")
        try:
            page = browser.new_page(viewport={"width": 820, "height": 800})
            page.set_content(_card_html(payload), wait_until="load")
            page.locator(".card").screenshot(path=str(output_path))
        finally:
            browser.close()
