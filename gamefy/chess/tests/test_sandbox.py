"""Browser regression checks using the platform's actual iframe restrictions."""
import json
from pathlib import Path
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
                    if request.request.post_data_json["code"] != "1234":
                        request.fulfill(status=409, body='{"detail":"invalid_code"}', content_type="application/json", headers=headers)
                        return
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
        frame.locator("#claim-code").fill("12")
        frame.locator("#claim-panel button").click()
        expect(frame.locator("#feedback")).to_contain_text("四位数字")
        assert not any(url.endswith("/claim") for url in calls)
        frame.locator("#claim-code").fill("9999")
        frame.locator("#claim-panel button").click()
        expect(frame.locator("#feedback")).to_contain_text("入座码不正确")
        page.wait_for_timeout(1200)  # A subsequent state refresh must not erase the error.
        expect(frame.locator("#feedback")).to_contain_text("入座码不正确")
        frame.locator("#claim-code").fill("1234")
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
        frame.locator("#back-to-rooms").click()
        expect(frame.locator("#lobby")).to_be_visible()
        saved["chess:last-room:player"] = "22222222-2222-4222-8222-222222222222"
        page.reload()
        expect(frame.locator("#lobby")).to_be_visible()
        browser.close()
