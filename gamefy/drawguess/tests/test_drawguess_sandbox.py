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
        "room_id": ROOM, "short_id": "DRAW88", "creator_name": "小画家",
        "cursor": 0, "server_time_ms": 1_000,
        "self_seat": self_seat, "code": "2468" if phase == "waiting" else None,
        "canvas": [], "messages": [],
        "state": {
            "phase": phase, "version": 0, "match_id": 1, "turn_id": 1,
            "turn_index": 0, "deadline_ms": 91_000, "players": players,
            "host_name": "小画家", "drawer_seat": None if phase == "waiting" else 0,
            "ranking": [], "turn_points": {},
        },
    }


def install_routes(context, publish, state, actions, saved=None, room_count=1):
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
                rooms = [
                    {
                        "room_id": f"{index:08d}-1111-4111-8111-111111111111",
                        "short_id": f"DRAW{index:02d}",
                        "creator_name": "小画家",
                        "room_type": "casual", "stake": 0,
                        "phase": state["state"]["phase"],
                        "occupied": 3,
                        "capacity": 8,
                        "mine": state["self_seat"] is not None,
                    }
                    for index in range(1, room_count + 1)
                ]
                if room_count == 1:
                    rooms[0].update(room_id=ROOM, short_id="DRAW88")
                request.fulfill(body=json.dumps(rooms), content_type="application/json", headers=headers)
                return
            request.fulfill(body=json.dumps(state, ensure_ascii=False), content_type="application/json", headers=headers)
            return
        relative = path.strip("/") or "index.html"
        request.fulfill(path=str(publish / relative), headers=headers)

    context.route("**/*", route)
    return saved


@pytest.mark.parametrize(
    ("width", "height"), [(320, 700), (390, 844), (1280, 900)]
)
def test_room_stages_share_one_fixed_viewport_and_persistent_chat(width, height):
    publish = Path(__file__).resolve().parents[1] / "publish"
    state, actions = snapshot(), []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": width, "height": height})
        context.add_init_script(
            "window.dzmm={user:{info:async()=>({id:'host'})},"
            "kv:{get:async()=>({value:null}),put:async()=>{}},"
            "loading:{progress(){},ready(){},error(){}},log:{info(){},error(){}}};"
        )
        install_routes(context, publish, state, actions)
        page = context.new_page()
        page.goto("https://draw.test/index.html")
        page.locator("#rooms button").click()
        page.evaluate("window.initialChatColumn=document.querySelector('.chat-column')")

        phase_data = [
            ("waiting", "#ready"),
            ("selecting", ".word-card"),
            ("drawing", "#clear"),
            ("revealing", "#reveal"),
            ("finished", "#ranking .primary"),
        ]
        for phase, primary in phase_data:
            state["self_seat"] = 0
            state["state"].update(
                phase=phase,
                drawer_seat=None if phase in {"waiting", "finished"} else 0,
                deadline_ms=None if phase == "finished" else 91_000,
                ranking=[],
            )
            state["state"].pop("candidates", None)
            state["state"].pop("answer", None)
            state["state"].pop("word_length", None)
            if phase == "selecting":
                state["state"]["candidates"] = [
                    {"id": "w001", "answer": "苹果"},
                    {"id": "w002", "answer": "熊猫"},
                    {"id": "w003", "answer": "雨伞"},
                ]
            if phase in {"drawing", "revealing"}:
                state["state"].update(answer="苹果", word_length=2)
            if phase == "finished":
                state["state"]["ranking"] = [
                    {"name": f"玩家 {index}", "score": 200 - index, "rank": index}
                    for index in range(1, 17)
                ]
            state["messages"] = [
                {"id": str(index), "name": "群友", "text": f"长期聊天消息 {index}"}
                for index in range(80)
            ]

            page.locator("#room-refresh").click()
            expect(page.locator(".room-toolbar")).to_be_visible()
            expect(page.locator(primary).first).to_be_visible()
            expect(page.locator(".chat-column")).to_be_visible()
            expect(page.locator("#chat-input")).to_be_enabled()
            expect(page.locator("#chat-send")).to_be_visible()
            assert page.evaluate(
                "window.initialChatColumn===document.querySelector('.chat-column')"
            )
            layout = page.evaluate("""
              () => {
                const body = document.body;
                const workspace = document.querySelector('.stage-workspace');
                const chat = document.querySelector('.chat-column');
                const messages = document.querySelector('.messages');
                return {
                  bodyScrollHeight: body.scrollHeight,
                  bodyScrollWidth: body.scrollWidth,
                  innerHeight,
                  innerWidth,
                  workspaceBottom: workspace.getBoundingClientRect().bottom,
                  chatBottom: chat.getBoundingClientRect().bottom,
                  messagesOverflowY: getComputedStyle(messages).overflowY,
                };
              }
            """)
            assert layout["bodyScrollHeight"] <= layout["innerHeight"]
            assert layout["bodyScrollWidth"] <= layout["innerWidth"]
            assert layout["workspaceBottom"] <= layout["innerHeight"] + 1
            assert layout["chatBottom"] <= layout["innerHeight"] + 1
            assert layout["messagesOverflowY"] == "auto"
            if phase == "drawing":
                assert page.locator("#draw-canvas").evaluate(
                    "e=>e.getBoundingClientRect().bottom<="
                    "document.querySelector('.stage-workspace').getBoundingClientRect().bottom+1"
                )
                expect(page.locator("#drawing-tools")).to_be_visible()
            if phase == "finished":
                assert page.locator(".ranking-list").evaluate(
                    "e=>e.scrollHeight>e.clientHeight"
                )
        browser.close()


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
        expect(page.locator("#rooms .room-button strong")).to_have_text("小画家的房间")
        page.locator("#rooms button").click()
        expect(page.locator("#room-view")).to_be_visible()
        expect(page.locator(".seat")).to_have_count(8)
        assert ROOM not in page.locator("#room-title").inner_text()
        page.locator("#ready").click();page.locator("#start").click()
        expect(page.locator(".word-card")).to_have_count(3)
        page.locator(".word-card").first.click()
        expect(page.locator("#drawing-tools")).to_be_visible()
        expect(page.locator("#input-reason")).to_have_text("作画中 · 可以聊天")
        expect(page.locator("#chat-input")).to_be_enabled()
        assert page.locator("body").evaluate("e=>e.scrollWidth<=innerWidth")
        page.screenshot(path=f"/tmp/drawguess-drawing-{width}.png")

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


@pytest.mark.parametrize(("width", "columns"), [(390, 4), (1280, 8)])
def test_waiting_room_uses_complete_seat_grid_and_secondary_room_code(width, columns):
    publish = Path(__file__).resolve().parents[1] / "publish"
    state, actions = snapshot(), []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": width, "height": 900})
        context.add_init_script("window.dzmm={user:{info:async()=>({id:'host'})},kv:{get:async()=>({value:null}),put:async()=>{}},loading:{progress(){},ready(){},error(){}},log:{info(){},error(){}}};")
        install_routes(context, publish, state, actions)
        page = context.new_page();page.goto("https://draw.test/index.html");page.locator("#rooms button").click()

        expect(page.locator("#room-title")).to_have_text("候场房间")
        expect(page.locator("#room-code")).to_have_text("小画家的房间")
        expect(page.locator(".seat")).to_have_count(8)
        assert page.locator("#players").evaluate("e=>getComputedStyle(e).display") == "grid"
        assert len(page.locator("#players").evaluate("e=>getComputedStyle(e).gridTemplateColumns.split(' ')")) == columns
        assert page.locator("#players").evaluate("e=>e.scrollWidth<=e.clientWidth")
        first = page.locator(".seat").nth(0).bounding_box()
        if columns == 4:
            next_row = page.locator(".seat").nth(4).bounding_box()
            assert first and next_row and abs(first["x"] - next_row["x"]) < 2 and next_row["y"] > first["y"]
        else:
            last = page.locator(".seat").nth(7).bounding_box()
            assert first and last and abs(first["y"] - last["y"]) < 2 and last["x"] > first["x"]
        assert page.locator("body").evaluate("e=>e.scrollWidth<=innerWidth")
        page.screenshot(path=f"/tmp/drawguess-waiting-{width}.png", full_page=True)
        browser.close()


@pytest.mark.parametrize(("room_count", "should_scroll"), [(1, False), (18, True)])
def test_game_fills_viewport_and_scrolls_only_inside_content(room_count, should_scroll):
    publish = Path(__file__).resolve().parents[1] / "publish"
    state, actions = snapshot(), []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.add_init_script("window.dzmm={user:{info:async()=>({id:'host'})},kv:{get:async()=>({value:null}),put:async()=>{}},loading:{progress(){},ready(){},error(){}},log:{info(){},error(){}}};")
        install_routes(context, publish, state, actions, room_count=room_count)
        page = context.new_page();page.goto("https://draw.test/index.html")

        expect(page.locator(".content-scroll")).to_have_count(1)
        layout = page.evaluate("""
          () => {
            const content = document.querySelector('.content-scroll');
            const shell = document.querySelector('.app-shell');
            return {
              viewportHeight: innerHeight,
              shellHeight: shell.getBoundingClientRect().height,
              bodyHeight: document.body.getBoundingClientRect().height,
              bodyScrollHeight: document.body.scrollHeight,
              bodyOverflow: getComputedStyle(document.body).overflowY,
              contentOverflow: getComputedStyle(content).overflowY,
              contentClientHeight: content.clientHeight,
              contentScrollHeight: content.scrollHeight,
              contentBottom: content.getBoundingClientRect().bottom,
              lobbyBottom: document.querySelector('#lobby').getBoundingClientRect().bottom,
              roomButtonHeight: document.querySelector('.room-button').getBoundingClientRect().height,
            };
          }
        """)
        assert abs(layout["shellHeight"] - layout["viewportHeight"]) < 2
        assert abs(layout["bodyHeight"] - layout["viewportHeight"]) < 2
        assert layout["bodyScrollHeight"] <= layout["viewportHeight"]
        assert layout["bodyOverflow"] == "hidden"
        assert layout["contentOverflow"] == "auto"
        overflow = layout["contentScrollHeight"] - layout["contentClientHeight"]
        assert (overflow > 1) is should_scroll
        if not should_scroll:
            assert abs(layout["lobbyBottom"] - layout["contentBottom"]) < 2
            assert layout["roomButtonHeight"] < 120
        page.screenshot(path=f"/tmp/drawguess-viewport-{'long' if should_scroll else 'short'}.png")
        if should_scroll:
            page.locator(".content-scroll").evaluate("e=>{e.scrollTop=e.scrollHeight}")
            assert page.locator(".content-scroll").evaluate("e=>e.scrollTop>0")
            page.screenshot(path="/tmp/drawguess-viewport-long-bottom.png")
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
        expect(page.locator("#input-reason")).to_have_text("观战中 · 可以聊天")
        expect(page.locator("#chat-input")).to_be_enabled()
        state["self_seat"] = 1;state["state"]["players"][1]["guessed"] = True;page.locator("#room-refresh").click()
        expect(page.locator("#input-reason")).to_have_text("已猜中 · 可以聊天")
        expect(page.locator("#chat-input")).to_be_enabled()
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
        expect(page.locator("#rooms")).to_contain_text("小画家的房间")
        page.locator("#rooms button").click();expect(page.locator("#room-view")).to_be_visible()
        page.reload();expect(page.locator("#rooms")).to_contain_text("小画家的房间")
        assert page.evaluate("location.hash") == ""
        assert page.evaluate("window.readyCalled") is True
        browser.close()


def test_identity_refresh_clears_private_word_before_new_identity_resolves():
    publish = Path(__file__).resolve().parents[1] / "publish"
    state, actions = snapshot("drawing", 0), []
    state["state"].update(drawer_seat=0, answer="苹果", word_length=2)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context()
        context.add_init_script("""
          window.testUid='host';
          window.dzmm={
            user:{info:()=>window.testUid==='host'?Promise.resolve({id:'host'}):new Promise(resolve=>setTimeout(()=>resolve({id:'viewer'}),200))},
            kv:{get:async()=>({value:null}),put:async()=>{}},loading:{ready(){},error(){}},log:{info(){},error(){}}
          };
        """)
        install_routes(context, publish, state, actions)
        page = context.new_page();page.goto("https://draw.test/index.html");page.locator("#rooms button").click()
        expect(page.locator("#prompt")).to_have_text("请画：苹果")
        page.evaluate("window.testUid='viewer';document.querySelector('#refresh').click()")
        expect(page.locator("#room-view")).to_be_hidden()
        expect(page.locator("#prompt")).not_to_contain_text("苹果")
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
