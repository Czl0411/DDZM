"""Exercise the rendered controls against the actual card-game rules."""
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


@pytest.mark.parametrize("size", [(390, 844), (844, 390)])
@pytest.mark.parametrize("game,stake,look,short", [
    *[("zhajinhua", stake, look, False) for stake in (0, 5, 10, 20) for look in (False, True)],
    ("zhajinhua", 5, True, True),
    ("texas", 0, False, False),
    ("blackjack", 0, False, False),
])
def test_real_card_rules_and_rendered_actions(size, game, stake, look, short):
    publish = Path(__file__).resolve().parents[1] / "publish"
    state = new_hand(game, ["a", "b"], stake, Random(3))
    actor = state["turn"]
    if short:
        state = apply_action(game, state, actor, "call", {})
        state = apply_action(game, state, state["turn"], "call", {})
    players = [{"id": "a", "name": "房主"}, {"id": "b", "name": "牌友"}]
    room = {"id": "11111111-1111-4111-8111-111111111111", "game": game, "phase": "playing", "creator_id": "a",
            "room_type": "coin" if stake else "casual", "stake": stake, "players": players,
            "ready": [], "me": next(p for p in players if p["id"] == actor),
            "version": 1, "hand_number": 1, "messages": []}
    actions, errors = [], []

    def apply_request(request_game, room_id, uid, version, request_id, action, payload, now):
        nonlocal state
        assert request_game == game and str(room_id) == room["id"]
        assert version == room["version"]
        state = apply_action(game, state, actor, action, payload)
        actions.append(action)
        room["version"] += 1
        room["phase"] = state["phase"]
        return {**room, "state": public_view(game, state, actor)}

    app = FastAPI()
    app.include_router(club_router(SimpleNamespace(club_card_action=apply_request), lambda: None))
    client = TestClient(app)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": size[0], "height": size[1]})
        context.add_init_script("""
          window.dzmm={user:{info:async()=>({id:'test-user'})},loading:{ready(){},error(){}}};
          const originalFetch=window.fetch;
          window.fetch=(url,options)=>String(url).endsWith('/events')
            ? Promise.resolve(new Response(new ReadableStream({start(){}}),{headers:{'Content-Type':'text/event-stream'}}))
            : originalFetch(url,options);
        """)

        def route(request):
            path = urlsplit(request.request.url).path
            headers = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"}
            if request.request.method == "OPTIONS":
                request.fulfill(status=204, headers=headers)
            elif path.endswith("/api/club/economy-settings"):
                request.fulfill(json=[{"game": game, "coin_stakes": [5, 10, 20], "rake_percent": 20}], headers=headers)
            elif path.endswith("/api/club/session"):
                request.fulfill(json=room["me"], headers=headers)
            elif path.endswith(f"/api/club/cards/{game}/rooms"):
                request.fulfill(json=[{"id": room["id"], "game": game, "mine": True}], headers=headers)
            elif f"/api/club/cards/{game}/rooms/" in path:
                if path.endswith("/actions"):
                    response = client.post(path, headers={"Authorization": "ClubUid test-user"}, json=request.request.post_data_json)
                    request.fulfill(status=response.status_code, json=response.json(), headers=headers)
                else:
                    request.fulfill(json={**room, "state": public_view(game, state, actor)}, headers=headers)
            else:
                request.fulfill(path=str(publish / path.lstrip("/")), headers=headers)

        context.route("**/*", route)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"https://club.test/games/card-table/index.html?game={game}")
        expect(page.locator("#table")).to_be_visible()
        expect(page.locator("#my-cards .back")).to_have_count(3 if game == "zhajinhua" else 0)
        if game == "zhajinhua":
            if look:
                page.get_by_role("button", name="看牌", exact=True).click()
                expect(page.locator("#my-cards .back")).to_have_count(0)
                expect(page.get_by_role("button", name="看牌", exact=True)).to_have_count(0)
            amount = 4 if look else 2
            if short:
                expect(page.get_by_role("button", name="跟注 2", exact=True)).to_be_enabled()
                button = page.get_by_role("button", name="加注 4 · 不足", exact=True)
                expect(button).to_be_disabled()
                expect(button).to_have_attribute("title", "需 4 筹码，剩余 3，筹码不足")
                page.get_by_role("button", name="跟注 2", exact=True).click()
                expect(page.locator("#last-action")).to_contain_text("跟注 2")
            else:
                before = state["chips"][actor]
                page.get_by_role("button", name=f"加注 {amount}", exact=True).click()
                expect(page.locator("#last-action")).to_contain_text(f"加注 {amount}")
                assert state["base_bet"] == 2
                assert state["chips"][actor] == before - amount
                assert actions == (["look"] if look else []) + ["raise"]
            page.reload()
            expect(page.locator("#table")).to_be_visible()
            expect(page.locator("#my-cards .back")).to_have_count(0 if look else 3)
        elif game == "texas":
            amount = state["current_bet"] + state["minimum_raise"]
            button = page.get_by_role("button", name=f"加注至 {amount}", exact=True)
            expect(button).to_be_enabled()
            button.click()
            expect(page.locator("#last-action")).to_contain_text(f"加注至 {amount}")
            assert actions == ["raise"]
        else:
            expect(page.get_by_role("button", name="要牌", exact=True)).to_be_enabled()
            page.get_by_role("button", name="停牌", exact=True).click()
            expect(page.locator("#last-action")).to_contain_text("停牌")
            assert actions == ["stand"]
        assert not errors
        browser.close()
