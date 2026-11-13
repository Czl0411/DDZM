"""Bull table: rendered controls through the actual HTTP payload validator and rules."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from random import Random
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

from dzmm_bot.core.club_api import club_router
from dzmm_bot.core.club_card_games import apply_action, new_hand, public_view


@pytest.mark.parametrize("size", [(390, 844), (844, 390), (1280, 720)])
def test_bull_selection_spectator_and_settlement(size):
    publish = Path(__file__).resolve().parents[1] / "publish"
    state = new_hand("niuniu", list("abcdef"), 10, Random(12), banker="b")
    state["hands"]["a"] = [["spades", r] for r in [14, 2, 7, 10, 13]]
    state["turn_deadline"] = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
    players = [{"id": raw, "name": f"牌友{raw}"} for raw in state["players"]]
    room = {"id": "11111111-1111-4111-8111-111111111111", "game": "niuniu", "phase": "playing", "creator_id": "a",
            "room_type": "coin", "stake": 10, "players": players, "ready": [], "me": players[0],
            "version": 1, "hand_number": 1, "messages": []}
    errors = []

    def apply_request(game, room_id, uid, version, request_id, action, payload, now):
        assert game == "niuniu" and action == "reveal"
        assert payload["hand_number"] == 1
        apply_action(game, state, "a", action, payload)
        for raw in list("bcdef"):
            apply_action(game, state, raw, "reveal", {})
        room["version"] += 1
        room["phase"] = state["phase"]
        return {**room, "state": public_view(game, state, "a")}

    app = FastAPI()
    app.include_router(club_router(SimpleNamespace(club_card_action=apply_request), lambda: None))
    client = TestClient(app)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": size[0], "height": size[1]})
        context.add_init_script("""
          window.dzmm={user:{info:async()=>({id:'test-user'})},loading:{ready(){},error(){}}};
          const fetchOriginal=window.fetch;
          window.fetch=(url,options)=>String(url).endsWith('/events')
            ? Promise.resolve(new Response(new ReadableStream({start(){}}),{headers:{'Content-Type':'text/event-stream'}}))
            : fetchOriginal(url,options);
        """)
        def route(request):
            path = urlsplit(request.request.url).path
            headers = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"}
            if request.request.method == "OPTIONS":
                request.fulfill(status=204, headers=headers)
            elif path.endswith("/api/club/economy-settings"):
                request.fulfill(json=[{"game": "niuniu", "coin_stakes": [5, 10, 20], "rake_percent": 20}], headers=headers)
            elif path.endswith("/api/club/session"):
                request.fulfill(json=room["me"], headers=headers)
            elif path.endswith("/api/club/cards/niuniu/rooms"):
                request.fulfill(json=[{"id": room["id"], "game": "niuniu", "mine": True}], headers=headers)
            elif "/api/club/cards/niuniu/rooms/" in path:
                if path.endswith("/actions"):
                    response = client.post(path, headers={"Authorization": "ClubUid test-user"}, json=request.request.post_data_json)
                    request.fulfill(status=response.status_code, json=response.json(), headers=headers)
                else:
                    request.fulfill(json={**room, "state": public_view("niuniu", state, room["me"]["id"])}, headers=headers)
            else:
                request.fulfill(path=str(publish / path.lstrip("/")), headers=headers)
        context.route("**/*", route)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("https://club.test/games/card-table/index.html?game=niuniu")
        expect(page.locator("#dealer")).to_contain_text("牌友b")
        expect(page.locator(".niu-seat-cards .back")).to_have_count(30)
        expect(page.get_by_role("button", name="亮牌", exact=True)).to_be_disabled()
        page.screenshot(path=f"/tmp/niuniu-{size[0]}-initial.png")
        for i in range(3):
            page.locator(".niu-card-button").nth(i).click()
        expect(page.locator('.niu-card-button[aria-pressed="true"]')).to_have_count(3)
        expect(page.get_by_role("button", name="亮牌", exact=True)).to_be_enabled()
        page.locator(".niu-card-button").nth(0).click()
        expect(page.get_by_role("button", name="亮牌", exact=True)).to_be_disabled()
        page.get_by_role("button", name="自动配牛", exact=True).click()
        expect(page.get_by_role("button", name="亮牌", exact=True)).to_be_enabled()
        # Core controls must fit and remain directly hittable, not behind seat overlays.
        for selector in ("#actions", "#my-cards"):
            bounds = page.locator(selector).bounding_box()
            assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= size[0]
            assert bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= size[1]
        page.screenshot(path=f"/tmp/niuniu-{size[0]}-playing.png")
        page.get_by_role("button", name="规则", exact=True).click()
        expect(page.locator("#niu-rules-dialog")).to_contain_text("牛牛且赢庄")
        page.get_by_role("button", name="知道了", exact=True).click()
        page.get_by_role("button", name="亮牌", exact=True).click()
        expect(page.locator("#result")).to_be_visible()
        expect(page.locator(".niu-payments")).to_contain_text("下一局庄家")
        expect(page.locator(".showdown-row")).to_have_count(6)
        expect(page.get_by_role("button", name="准备下一手", exact=True)).to_be_visible()
        page.screenshot(path=f"/tmp/niuniu-{size[0]}-result.png")
        room["me"] = {"id": "spectator", "name": "旁观者"}
        page.reload()
        expect(page.locator("#my-cards .card")).to_have_count(0)
        expect(page.get_by_role("button", name="亮牌", exact=True)).to_have_count(0)
        assert not errors
        browser.close()
