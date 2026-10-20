import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright


ROOM_ID = "11111111-1111-4111-8111-111111111111"


def waiting_snapshot():
    now = datetime.now(timezone.utc)
    return {
        "id": ROOM_ID,
        "short_id": "MAHJONG88",
        "room_type": "casual",
        "match_mode": "east",
        "buy_in": 0,
        "prizes": [0, 0, 0, 0],
        "phase": "waiting",
        "version": 0,
        "seat": 0,
        "creator_seat": 0,
        "players": [
            {"name": "房主", "ready": False, "online": True},
            None, None, None,
        ],
        "code": "2468",
        "deadline": (now + timedelta(minutes=10)).isoformat(),
        "server_time": now.isoformat(),
        "messages": [],
        "settlement": None,
    }


def playing_snapshot():
    value = waiting_snapshot()
    value.update(phase="playing", version=5, code=None)
    value["players"] = [
        {"name": name, "ready": True, "online": True}
        for name in ("房主", "南风", "西风", "北风")
    ]
    value["game"] = {
        "mode": "east", "points": [25000] * 4, "dealer": 0,
        "round_wind": 27, "hand_number": 1, "honba": 0,
        "riichi_sticks": 0, "turn": 0,
        "melds": [[], [], [], []], "discards": [[], [], [], []],
        "riichi": [False] * 4, "result": None, "remaining": 69,
        "dora_indicators": [120], "hand": list(range(14)),
        "hand_counts": [14, 13, 13, 13],
        "actions": {"discard": list(range(14)), "riichi": [0]},
    }
    return value


@pytest.mark.parametrize(("width", "height"), [(320, 700), (390, 844), (844, 390), (1280, 720)])
def test_club_and_table_stay_in_one_viewport(width, height):
    publish = Path(__file__).resolve().parents[1] / "publish"
    state, actions = waiting_snapshot(), []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": width, "height": height})
        context.add_init_script(
            "window.clubEvents=[];window.dzmm={user:{info:async()=>({id:'host-user'})},"
            "getLaunchParams:async()=>({}),share:async value=>clubEvents.push(['share',value]),"
            "loading:{progress:value=>clubEvents.push(['progress',value]),ready:()=>clubEvents.push(['ready']),error:(...v)=>clubEvents.push(['error',v])}};"
        )

        def route(request):
            path = urlsplit(request.request.url).path
            headers = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"}
            if request.request.method == "OPTIONS":
                request.fulfill(status=204, headers=headers)
                return
            if "/api/club/mahjong/" in request.request.url:
                if path.endswith("/actions"):
                    body = request.request.post_data_json
                    actions.append(body)
                    state["version"] += 1
                    if body["action"] == "ready":
                        state["players"][0]["ready"] = True
                    request.fulfill(json=state, headers=headers)
                    return
                if path.endswith("/chat"):
                    body = request.request.post_data_json
                    state["messages"].append({"id": "m1", "name": "房主", "text": body["text"]})
                    request.fulfill(json=state["messages"][-1], headers=headers)
                    return
                if path.endswith("/rooms"):
                    request.fulfill(json=[{
                        "id": ROOM_ID, "short_id": "MAHJONG88", "room_type": "casual",
                        "match_mode": "east", "phase": state["phase"], "occupied": 1,
                        "mine": True, "names": ["房主"],
                    }], headers=headers)
                    return
                request.fulfill(json=state, headers=headers)
                return
            relative = path.strip("/") or "index.html"
            request.fulfill(path=str(publish / relative), headers=headers)

        context.route("**/*", route)
        page = context.new_page()
        page.goto("https://club.test/index.html")
        expect(page.locator("#club-home")).to_be_visible()
        expect(page.locator("#game-grid .game-card")).to_have_count(4)
        page.locator("#game-grid .game-card").first.click()
        expect(page.locator("#mahjong-lobby")).to_be_visible()
        page.locator("#rooms .room-card").click()
        expect(page.locator("#waiting")).to_be_visible()
        expect(page.locator("#fullscreen")).to_be_visible()
        expect(page.locator("#home")).not_to_be_visible()
        page.locator("#ready").click()
        expect(page.locator("#ready")).to_have_text("取消准备")
        page.locator("#share-room").click()
        expect(page.locator("#chat-toggle")).to_be_visible()
        page.locator("#chat-toggle").click()
        page.locator("#chat-input").fill("好好打牌")
        page.locator("#chat-send").click()
        expect(page.locator("#messages")).to_contain_text("好好打牌")

        state.clear()
        state.update(playing_snapshot())
        page.locator("#chat-close").click()
        page.wait_for_timeout(1200)
        expect(page.locator("#mahjong-table")).to_be_visible()
        expect(page.locator("#hand .tile")).to_have_count(14)
        expect(page.locator("#hand .tile").first).to_have_attribute("aria-label", "1萬")
        expect(page.locator("#hand .tile").first).to_have_text("🀇")
        expect(page.locator("#remaining-count")).to_have_text("余 69 张")
        expect(page.locator("#self-player")).to_contain_text("东风 · 14 张")
        tile_box = page.locator("#hand .tile").first.bounding_box()
        assert tile_box["y"] + tile_box["height"] <= height, tile_box
        assert tile_box["x"] >= 0, tile_box
        page.locator("#hand .tile").first.click()
        expect(page.locator("#action-bar")).to_contain_text("立直打出")
        layout = page.evaluate("""
            () => ({
              bodyHeight: document.body.scrollHeight,
              bodyWidth: document.body.scrollWidth,
              innerHeight,
              innerWidth,
              tableBottom: document.querySelector('.mahjong-table').getBoundingClientRect().bottom,
              tableScreenBottom: document.querySelector('.table-screen').getBoundingClientRect().bottom,
            })
        """)
        assert layout["bodyHeight"] <= layout["innerHeight"]
        assert layout["bodyWidth"] <= layout["innerWidth"]
        assert layout["tableBottom"] <= layout["innerHeight"] + 1
        assert layout["tableScreenBottom"] <= layout["innerHeight"] + 1
        assert any(event[0] == "ready" for event in page.evaluate("clubEvents"))
        assert actions[0]["action"] == "ready"
        browser.close()


def test_source_does_not_use_forbidden_storage_or_expand_the_page():
    publish = Path(__file__).resolve().parents[1] / "publish"
    source = "\n".join(path.read_text() for path in publish.iterdir() if path.suffix in {".js", ".css", ".html"})
    assert "localStorage" not in source
    assert "100dvh" in source
    assert "overflow:hidden" in source.replace(" ", "")
    for asset in (
        "club-hero-v2.webp", "game-mahjong.webp", "game-chess.webp",
        "game-doudizhu.webp", "game-drawguess.webp", "mahjong-table.webp",
    ):
        assert (publish / "assets" / asset).is_file()
        assert asset in source
