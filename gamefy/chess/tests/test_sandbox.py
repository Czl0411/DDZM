"""Browser regression checks using the platform's actual iframe restrictions."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
import pytest

from playwright.sync_api import sync_playwright, expect


@pytest.mark.parametrize("width,role", [(390, "red"), (1280, "black")])
def test_claim_chat_and_reopen_in_platform_sandbox(width, role):
    publish = Path(__file__).resolve().parents[1] / "publish"
    room = "11111111-1111-4111-8111-111111111111"
    saved = {}
    calls = []
    moves = []
    state = {"role": "spectator", "game": {"status": "waiting", "version": 0,
             "red_remaining_ms": 900000, "black_remaining_ms": 900000}, "messages": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": width, "height": 1200})
        context.expose_function("saveRoom", lambda key, value: saved.update({key: value}))
        context.expose_function("readRoom", lambda key: {"value": saved.get(key)})
        context.add_init_script("""window.dzmm = {
          getLaunchParams: async()=>({}), user:{info:async()=>({id:'player'})},
          kv:{get:async k=>readRoom(k),put:async(k,v)=>saveRoom(k,v)},
          loading:{progress(){},ready(){},error(){}}
        };""")

        def route(request):
            url = request.request.url
            headers = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"}
            if request.request.method == "OPTIONS":
                request.fulfill(status=204, headers=headers)
            elif "/api/chess" in url:
                calls.append(url)
                if url.endswith("/events"):
                    request.fulfill(body="", content_type="text/event-stream", headers=headers)
                    return
                if url.endswith("/claim"):
                    state["role"] = role
                    state["game"]["status"] = "playing"
                    state["game"]["turn_started_at"] = "2026-10-13T00:00:00Z"
                    state["game"]["position"] = {"turn": role, "board": ["rheakaehr", ".........", ".c.....c.", "p.p.p.p.p", ".........", ".........", "P.P.P.P.P", ".C.....C.", ".........", "RHEAKAEHR"]}
                if url.endswith("/moves"):
                    moves.append(request.request.post_data_json)
                if url.endswith("/chat"):
                    state["messages"] = [{"sender": "player", "text": "hello"}]
                body = [{"id": room, "creator_name": "Creator", "status": "waiting"}] if url.endswith("/rooms") else state
                request.fulfill(body=json.dumps(body), content_type="application/json", headers=headers)
            elif url.endswith("/host"):
                request.fulfill(body='<body style="margin:0"><iframe style="width:100%;height:1200px;border:0" sandbox="allow-scripts allow-modals" src="/index.html"></iframe>', content_type="text/html")
            else:
                request.fulfill(path=str(publish / url.split("/")[-1].split("#")[0]), headers=headers)

        context.route("**/*", route)
        page = context.new_page()
        page.goto("https://chess.test/host")
        frame = page.frame_locator("iframe")
        frame.locator("#rooms button").click()
        frame.locator("#chat-input").fill("hello")
        frame.locator("#chat-send").click()
        expect(frame.locator("#chat-list")).to_contain_text("hello")
        expect(frame.locator("#board .piece")).to_have_count(32)
        page.screenshot(path=f"/tmp/chess-ui-{width}.png", full_page=True)
        assert frame.locator("body").evaluate("e=>e.scrollWidth <= innerWidth")
        frame.locator("#claim-panel button").click()
        expect(frame.locator("#claim-panel")).to_be_hidden(timeout=3000)
        assert any(url.endswith("/claim") for url in calls)
        y = 6 if role == "red" else 3
        target_y = 5 if role == "red" else 4
        frame.locator(f'[aria-label="0,{y}{"兵" if role == "red" else "卒"}"]').click()
        frame.locator(f'[aria-label="0,{target_y}"]').click()
        expect(frame.locator(".cell.selected")).to_have_count(0)
        assert moves[-1]["from_xy"] == [0, y]
        assert moves[-1]["to_xy"] == [0, target_y]
        frame.locator("#chat-input").fill("hello")
        frame.locator("#chat-send").click()
        expect(frame.locator("#chat-list")).to_contain_text("hello")
        page.reload()
        expect(frame.locator("#players")).to_be_visible()
        expect(frame.locator("#lobby")).to_be_hidden()
        state["game"]["events"] = [{"seq": 1, "kind": "move", "color": "red", "ply": 1, "piece": "R", "captured": "p", "check": True, "from_xy": [3, 3], "to_xy": [4, 3]}]
        state["game"]["check_square"] = [4, 0]
        frame.locator("#chat-input").fill("hello")
        frame.locator("#chat-send").click()
        expect(frame.locator("#move-notice")).to_have_text("吃 · 将军")
        expect(frame.locator('[aria-label="4,0將"]')).to_have_class(re.compile("in-check"))
        expect(frame.locator("#move-notice")).to_be_hidden(timeout=4000)
        page.reload()
        expect(frame.locator("#moves-list")).to_contain_text("将军")
        expect(frame.locator("#move-notice")).to_be_hidden()
        state["game"]["events"].extend([{"seq": 2, "kind": "offer_undo", "color": "red"}, {"seq": 3, "kind": "accept_undo", "color": "black", "undone_seq": 1}])
        frame.locator("#chat-input").fill("hello")
        frame.locator("#chat-send").click()
        expect(frame.locator("#moves-list .revoked")).to_contain_text("已撤回")
        state["game"]["status"] = "finished"
        state["game"]["result"] = "red:checkmate"
        expect(frame.locator("#result-title")).to_have_text("胜利" if role == "red" else "落败")
        expect(frame.locator("#result-reason")).to_contain_text("绝杀")
        page.screenshot(path=f"/tmp/chess-result-{width}.png", full_page=True)
        frame.locator("#back-to-rooms").click()
        expect(frame.locator("#lobby")).to_be_visible()
        saved["chess:last-room:player"] = "22222222-2222-4222-8222-222222222222"
        page.reload()
        expect(frame.locator("#lobby")).to_be_visible()
        browser.close()


def test_embedded_finished_exit_posts_leave_and_closes_module_without_reload():
    publish = Path(__file__).resolve().parents[2] / "club" / "publish"
    room = "11111111-1111-4111-8111-111111111111"
    actions = []
    state = {
        "role": "red", "is_host": True, "server_time": "2026-10-13T00:00:00Z",
        "messages": [],
        "game": {
            "id": room, "status": "finished", "version": 4, "result": "red:checkmate",
            "red_name": "我", "black_name": "对手", "room_type": "casual", "stake": 0,
            "red_remaining_ms": 800000, "black_remaining_ms": 790000,
            "position": {"turn": "red", "board": ["rheakaehr", ".........", ".c.....c.", "p.p.p.p.p", ".........", ".........", "P.P.P.P.P", ".C.....C.", ".........", "RHEAKAEHR"]},
            "events": [], "rematch_ready": [], "settlement": None,
        },
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context()
        context.add_init_script("""
          const sdk={getLaunchParams:async()=>({}),user:{info:async()=>({id:'player'})},kv:{get:async()=>({value:null}),put:async()=>{}},loading:{progress(){},ready(){},error(){}}};
          window.dzmm=sdk;
          window.MoyuClubRuntime={embedded:true,sdk,close:()=>{window.moduleClosed=true},openGameLobby:game=>{window.moduleLobby=game}};
        """)

        def route(request):
            url = request.request.url
            path = urlsplit(url).path
            headers = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"}
            if request.request.method == "OPTIONS":
                request.fulfill(status=204, headers=headers)
            elif path.endswith("/runtime-bootstrap.js"):
                request.fulfill(body="", content_type="text/javascript", headers=headers)
            elif url.endswith("/config.js"):
                request.fulfill(body="window.CHESS_API_BASE='https://chess.test';", content_type="text/javascript", headers=headers)
            elif url.endswith("/api/club/economy-settings"):
                request.fulfill(json=[{"game": "chess", "coin_stakes": [5, 10, 20], "rake_percent": 20}], headers=headers)
            elif url.endswith("/events"):
                request.fulfill(body="", content_type="text/event-stream", headers=headers)
            elif url.endswith("/actions"):
                actions.append(request.request.post_data_json)
                request.fulfill(json={**state, "game": {**state["game"], "status": "cancelled", "version": 5}}, headers=headers)
            elif f"/api/chess/{room}" in url:
                request.fulfill(json=state, headers=headers)
            else:
                request.fulfill(path=str(publish / path.lstrip("/")), headers=headers)

        context.route("**/*", route)
        page = context.new_page()
        page.goto(f"https://chess.test/games/chess/index.html?club=1&room={room}")
        expect(page.locator("#result")).to_be_visible()
        room_url = page.url
        page.locator("#result-exit").click()
        page.wait_for_function("window.moduleLobby === 'chess'")
        assert page.evaluate("window.moduleClosed") is None
        assert actions[-1] == {"action": "leave", "version": 4}
        assert page.url == room_url
        browser.close()
