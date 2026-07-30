import argparse
import json
from pathlib import Path

from .dzmm_source import DzmmMessageSource


def main() -> None:
    parser = argparse.ArgumentParser(description="Read recent DZMM messages without sending replies.")
    parser.add_argument("--config", type=Path, default=Path("config.local.json"))
    args = parser.parse_args()
    config = json.loads(args.config.read_text())

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            config["browser_profile_dir"], headless=False
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(config["group_url"], wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        source = DzmmMessageSource(
            page,
            group_key=config.get("group_key", "main"),
            selectors=config.get("selectors"),
        )
        for message in source.read_new():
            print(f"{message.message_id}\t{message.sender}\t{message.text}")
        context.close()
