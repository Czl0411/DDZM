import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright


ROOM = "11111111-1111-4111-8111-111111111111"


def snapshot(phase="waiting", self_seat=0):
    players = [
        {"name": "小画家", "ready": False, "score": 0, "is_host": True, "guessed": False},
        {"name": "猜猜", "ready": True, "score": 0, "is_host": False, "guessed": False},
        {"name": "阿圆", "ready": True, "score": 0, "is_host": False, "guessed": False},
    ]
    return {
        "room_id": ROOM, "short_id": "DRAW88", "cursor": 0, "server_time_ms": 1_000,
        "self_seat": self_seat, "code": "2468" if phase == "waiting" else None,
        "canvas": [], "messages": [],
        "state": {
            "phase": phase, "version": 0, "match_id": 1, "turn_id": 1,
            "turn_index": 0, "deadline_ms": 91_000, "players": players,
            "host_name": "小画家", "drawer_seat": None if phase == "waiting" else 0,
            "ranking": [], "turn_points": {},
        },
    }


def install_routes(context, publish, state, actions, saved=None):
    saved = saved if saved is not None else {}

    def route(request):
        url = request.request.url
        path = urlsplit(url).path
        headers = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"}
        if request.request.method == "OPTIONS":
            request.fulfill(status=204, headers=headers)
            return
        if "/api/drawguess/" in url:
            if path.endswith("/events"):
                request.fulfill(body="", content_type="text/event-stream", headers=headers)
                return
            if path.endswith("/actions"):
                body = request.request.post_data_json
                actions.append(body)
                action = body["action"]
                if action in {"ready", "unready"}:
                    state["state"]["players"][state["self_seat"]]["ready"] = action == "ready"
                elif action == "start":
                    state["state"].update(
                        phase="selecting", version=state["state"]["version"] + 1,
                        drawer_seat=0, deadline_ms=16_000,
                        candidates=[{"id": "w001", "answer": "苹果"}, {"id": "w002", "answer": "熊猫"}, {"id": "w003", "answer": "雨伞"}],
                    )
                    state["code"] = None
                elif action == "choose":
                    state["state"].update(
                        phase="drawing", version=state["state"]["version"] + 1,
                        answer="苹果", word_length=2, deadline_ms=91_000,
                    )
                    state["state"].pop("candidates", None)
                elif action == "rematch":
                    state.clear();state.update(snapshot("waiting", 0))
                request.fulfill(body=json.dumps(state, ensure_ascii=False), content_type="application/json", headers=headers)
                return
            if path.endswith("/strokes"):
                body = request.request.post_data_json;actions.append(body)
                for operation in body["operations"]:
                    state["cursor"] += 1
                    state["canvas"].append({"seq": state["cursor"], "turn_id": state["state"]["turn_id"], **operation})
                request.fulfill(body=json.dumps({"cursor": state["cursor"], "reset": False, "events": [], "snapshot": state}), content_type="application/json", headers=headers)
                return
            if path.endswith("/chat"):
                body = request.request.post_data_json;actions.append(body)
                if body["text"] == "苹果":
                    state["state"].update(phase="revealing", answer="苹果", deadline_ms=6_000)
                    state["state"]["players"][state["self_seat"]]["score"] = 100
                    text = "已猜中 +100分"
                else:
                    text = body["text"]
                state["messages"].append({"id": str(len(state["messages"])), "name": "猜猜", "text": text})
                request.fulfill(body=json.dumps({"id": "m", "name": "猜猜", "text": text}, ensure_ascii=False), content_type="application/json", headers=headers)
                return
            if path.endswith("/rooms"):
                request.fulfill(body=json.dumps([{"room_id": ROOM, "short_id": "DRAW88", "phase": state["state"]["phase"], "occupied": 3, "capacity": 8, "mine": state["self_seat"] is not None}]), content_type="application/json", headers=headers)
                return
            request.fulfill(body=json.dumps(state, ensure_ascii=False), content_type="application/json", headers=headers)
            return
        relative = path.strip("/") or "index.html"
        request.fulfill(path=str(publish / relative), headers=headers)

    context.route("**/*", route)
    return saved


@pytest.mark.parametrize("width", [320, 390, 1280])
def test_full_game_mobile_and_desktop(width):
    publish = Path(__file__).resolve().parents[1] / "publish"
    state, actions = snapshot(), []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": width, "height": 1000})
        context.add_init_script("""window.dzmm={user:{info:async()=>({id:'host'})},kv:{get:async()=>({value:null}),put:async()=>{}},loading:{progress(){},ready(){window.readyCalled=true},error(){}},log:{info(){},error(){}}};""")
        install_routes(context, publish, state, actions)
        page = context.new_page();page.goto("https://draw.test/index.html")
        page.locator("#rooms button").click()
        expect(page.locator("#room-view")).to_be_visible()
        expect(page.locator(".seat")).to_have_count(8)
        assert ROOM not in page.locator("#room-title").inner_text()
        page.locator("#ready").click();page.locator("#start").click()
        expect(page.locator(".word-card")).to_have_count(3)
        page.locator(".word-card").first.click()
        expect(page.locator("#drawing-tools")).to_be_visible()
        expect(page.locator("#input-reason")).to_have_text("你正在作画")
        assert page.locator("body").evaluate("e=>e.scrollWidth<=innerWidth")

        state["self_seat"] = 1;state["state"]["drawer_seat"] = 0
        state["state"].pop("answer", None);state["state"]["word_length"] = 2
        page.locator("#room-refresh").click()
        page.locator("#chat-input").fill("苹果");page.locator("#chat-send").click()
        expect(page.locator("#reveal")).to_contain_text("苹果")

        state["state"].update(phase="finished", ranking=[
            {"name": "猜猜", "score": 200, "rank": 1}, {"name": "小画家", "score": 160, "rank": 2}, {"name": "阿圆", "score": 120, "rank": 3},
        ])
        page.locator("#room-refresh").click()
        expect(page.locator("#ranking")).to_contain_text("第 1 名")
        assert page.evaluate("location.hash") == ""
        page.screenshot(path=f"/tmp/drawguess-{width}.png", full_page=True)
        assert page.evaluate("window.readyCalled") is True
        browser.close()


def test_keyboard_touch_and_permissions():
    publish = Path(__file__).resolve().parents[1] / "publish"
    state, actions = snapshot("drawing", 1), []
    state["state"].update(drawer_seat=0, word_length=2)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.add_init_script("window.dzmm={user:{info:async()=>({id:'p1'})},kv:{get:async()=>({value:null}),put:async()=>{}},loading:{ready(){},error(){}},log:{info(){},error(){}}};")
        install_routes(context, publish, state, actions)
        page = context.new_page();page.goto("https://draw.test/index.html");page.locator("#rooms button").click()
        page.locator("#chat-input").fill("测试")
        page.locator("#chat-input").evaluate("el=>{el.dispatchEvent(new CompositionEvent('compositionstart'));el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));}")
        assert not any("text" in action for action in actions)
        page.locator("#chat-input").evaluate("el=>el.dispatchEvent(new CompositionEvent('compositionend'))")
        page.locator("#chat-send").click()
        assert any(action.get("text") == "测试" for action in actions)
        assert page.locator("#chat-send").evaluate("e=>e.getBoundingClientRect().height>=44")
        assert page.locator("#draw-canvas").evaluate("e=>getComputedStyle(e).touchAction") == "none"

        state["self_seat"] = None;page.locator("#room-refresh").click()
        expect(page.locator("#input-reason")).to_have_text("观战中，仅可查看")
        state["self_seat"] = 1;state["state"]["players"][1]["guessed"] = True;page.locator("#room-refresh").click()
        expect(page.locator("#input-reason")).to_have_text("你已猜中，等待揭晓")
        browser.close()


def test_boot_restore_kv_failure_and_no_hash_navigation():
    publish = Path(__file__).resolve().parents[1] / "publish"
    state, actions = snapshot(), []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context()
        context.add_init_script(f"""window.dzmm={{user:{{info:async()=>({{id:'host'}})}},kv:{{get:async()=>{{throw new Error('kv')}} ,put:async()=>{{throw new Error('kv')}}}},loading:{{ready(){{window.readyCalled=true}},error(){{}}}},log:{{info(){{}},error(){{}}}}}};""")
        install_routes(context, publish, state, actions)
        page = context.new_page();page.goto("https://draw.test/index.html")
        expect(page.locator("#rooms")).to_contain_text("DRAW88")
        page.locator("#rooms button").click();expect(page.locator("#room-view")).to_be_visible()
        page.reload();expect(page.locator("#rooms")).to_contain_text("DRAW88")
        assert page.evaluate("location.hash") == ""
        assert page.evaluate("window.readyCalled") is True
        browser.close()


def test_reconnect_clear_and_next_turn_replaces_canvas():
    publish = Path(__file__).resolve().parents[1] / "publish"
    state, actions = snapshot("drawing", 1), []
    state["state"].update(drawer_seat=0, word_length=2)
    state["canvas"] = [{"seq": 1, "turn_id": 1, "op": "begin", "stroke_id": "old", "points": [[0.1, 0.1]], "color": "#222222", "width": 0.008, "tool": "pen"}]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context()
        context.add_init_script("window.dzmm={user:{info:async()=>({id:'p1'})},kv:{get:async()=>({value:null}),put:async()=>{}},loading:{ready(){},error(){}},log:{info(){},error(){}}};")
        install_routes(context, publish, state, actions)
        page=context.new_page();page.goto("https://draw.test/index.html");page.locator("#rooms button").click()
        expect(page.locator("#draw-canvas")).to_have_attribute("data-turn-id", "1")
        state["state"]["turn_id"] = 2;state["state"]["turn_index"] = 1;state["state"]["drawer_seat"] = 1;state["canvas"] = [];state["cursor"] = 2
        page.locator("#room-refresh").click()
        expect(page.locator("#draw-canvas")).to_have_attribute("data-turn-id", "2")
        expect(page.locator("#feedback")).not_to_contain_text("加载中")
        browser.close()
