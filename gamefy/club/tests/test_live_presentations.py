"""Real renderer checks with public game snapshots, not just empty layout shells."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

ROOM = "11111111-1111-4111-8111-111111111111"


def live_snapshot(game):
    now = datetime.now(timezone.utc)
    if game == "chess":
        return {"role": "red", "messages": [], "server_time": now.isoformat(), "game": {
            "id": ROOM, "status": "playing", "version": 1, "red_name": "红方玩家", "black_name": "黑方玩家",
            "red_remaining_ms": 900000, "black_remaining_ms": 900000, "turn_started_at": now.isoformat(),
            "position": {"turn": "red", "board": ["rheakaehr", ".........", ".c.....c.", "p.p.p.p.p", ".........", ".........", "P.P.P.P.P", ".C.....C.", ".........", "RHEAKAEHR"]},
            "events": [{"seq": 1, "kind": "move", "ply": 1, "color": "red", "piece": "P", "from_xy": [0, 6], "to_xy": [0, 5]}],
        }}
    if game == "doudizhu":
        return {"id": ROOM, "creator_name": "房主", "round_id": ROOM, "version": 1, "phase": "playing", "seat": 0,
                "players": [{"name": name, "ready": True, "count": 17, "trustee": False, "online": True} for name in ["自己", "牌友", "另一位牌友"]],
                "hand": list(range(17)), "bottom": [20, 21, 22], "turn": 0, "landlord": 0, "bid": 3,
                "multiplier": 1, "previous": None, "table": [None, {"kind": "pass"}, None], "result": None,
                "events": [{"seq": 1, "seat": 1, "kind": "pass"}], "messages": [], "server_time": now.isoformat(),
                "deadline": (now + timedelta(seconds=25)).isoformat()}
    return {"room_id": ROOM, "creator_name": "画手", "self_seat": 1, "canvas": [], "messages": [], "cursor": 0,
            "server_time_ms": int(now.timestamp() * 1000), "state": {
                "phase": "drawing", "version": 1, "match_id": 1, "turn_id": 1, "turn_index": 0, "drawer_seat": 0,
                "deadline_ms": int((now + timedelta(seconds=80)).timestamp() * 1000), "word_length": 2,
                "players": [{"name": name, "ready": True, "score": 100 if i == 2 else 0, "is_host": i == 0, "guessed": i == 2} for i, name in enumerate(["画手", "自己", "猜中的玩家"])],
            }}


@pytest.mark.parametrize("game", ["chess", "doudizhu", "drawguess"])
@pytest.mark.parametrize("size", [(390, 844), (844, 390)])
def test_actual_game_snapshots_render_action_cues(game, size):
    publish = Path(__file__).resolve().parents[1] / "publish"
    snapshot = live_snapshot(game)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": size[0], "height": size[1]})
        context.add_init_script("window.dzmm={user:{info:async()=>({id:'test-player'})},getLaunchParams:async()=>({}),kv:{get:async()=>({value:null}),put:async()=>{}},loading:{ready(){},progress(){},error(){}}};")

        def route(request):
            path = urlsplit(request.request.url).path
            headers = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"}
            if request.request.method == "OPTIONS":
                request.fulfill(status=204, headers=headers)
            elif "/api/" in path:
                if path.endswith("/events"):
                    request.fulfill(body="", content_type="text/event-stream", headers=headers)
                elif path.endswith("/rooms"):
                    request.fulfill(json=[{"id": ROOM, "room_id": ROOM, "creator_name": "房主", "phase": "playing", "status": "playing", "occupied": 3, "capacity": 8}], headers=headers)
                else:
                    request.fulfill(json=snapshot, headers=headers)
            else:
                request.fulfill(path=str(publish / path.lstrip("/")), headers=headers)

        context.route("**/*", route)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"https://club.test/games/{game}/index.html?club=1&room={ROOM}")
        if game == "chess":
            expect(page.locator("#board .cell")).to_have_count(90)
            expect(page.locator(".last-from")).to_have_count(1)
            expect(page.locator(".last-to")).to_have_count(1)
            expect(page.locator("#status")).to_contain_text("进行中")
        elif game == "doudizhu":
            expect(page.locator("#hand .card")).to_have_count(17)
            expect(page.locator("#opponents")).to_contain_text("不出")
            expect(page.locator("#pass")).to_have_text("首家须出牌")
        else:
            expect(page.locator("#players")).to_contain_text("已猜中")
            expect(page.locator("#players")).to_contain_text("画手")
            expect(page.locator("#input-reason")).not_to_contain_text("undefined")
        assert errors == []
        assert page.evaluate("document.body.scrollWidth <= innerWidth && document.body.scrollHeight <= innerHeight")
        browser.close()
