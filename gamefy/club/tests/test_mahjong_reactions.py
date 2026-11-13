"""Keep touch targets and chi choices stable while other seats respond."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from test_club_sandbox import playing_snapshot


@pytest.mark.parametrize('width,height', [(1280, 720), (844, 390), (390, 844)])
def test_reaction_choices_survive_updates_and_submit_once(width, height):
    publish = Path(__file__).resolve().parents[1] / 'publish'
    state = playing_snapshot()
    state['phase'] = 'reaction'
    game = state['game']
    game.update(turn=3, reaction_version=state['version'], reaction_action=None,
                actions={'pass': True, 'chi': [[0, 4], [4, 12], [12, 16]]})
    game['discards'][3] = [{'tile': 8, 'called': False, 'riichi': False}]
    sent, errors = [], []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        ctx = browser.new_context(viewport={'width': width, 'height': height}, has_touch=True)
        ctx.add_init_script("window.dzmm={user:{info:async()=>({id:'preview'})},getLaunchParams:async()=>({roomId:'" + state['id'] + "'}),loading:{ready(){},progress(){},error(){}}};const original=window.fetch;window.fetch=(url,opts)=>String(url).endsWith('/events')?Promise.resolve(new Response(new ReadableStream({start(){}}))):original(url,opts);")

        def route(r):
            path = urlsplit(r.request.url).path
            headers = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*'}
            if r.request.method == 'OPTIONS':
                r.fulfill(status=204, headers=headers)
            elif '/api/club/mahjong/rooms/' in path:
                if path.endswith('/actions') and r.request.method == 'POST':
                    body = r.request.post_data_json
                    sent.append(body)
                    assert body['payload']['reaction_version'] == game['reaction_version']
                    state['version'] += 1
                    game.update(actions={}, reaction_action=body['action'])
                now = datetime.now(timezone.utc)
                state['server_time'] = now.isoformat()
                state['deadline'] = (now + timedelta(seconds=15)).isoformat()
                r.fulfill(json=state, headers=headers)
            elif path.endswith('/session'):
                r.fulfill(json={'id': 'preview', 'uid': 'preview', 'name': '预览'}, headers=headers)
            elif path.endswith('/presence'):
                r.fulfill(json={'online': 4, 'playing': 4}, headers=headers)
            elif '/api/' in path:
                r.fulfill(json=[], headers=headers)
            else:
                r.fulfill(path=str(publish / (path.lstrip('/') or 'index.html')), headers=headers)

        ctx.route('**/*', route)
        page = ctx.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('https://club.test/')
        expect(page.locator('#turn-status')).to_have_text('等待你的回应')
        expect(page.locator('#decision-timer')).to_have_text('15')
        page.get_by_role('button', name='吃', exact=True).tap()
        choices = page.locator('#meld-choices .meld-choice')
        expect(choices).to_have_count(3)
        expect(page.locator('#meld-choice-timer')).to_have_text('剩余 15 秒')
        choice = choices.nth(1)
        choice.evaluate('n => window.pressedChoice = n')
        state['version'] += 1  # Another seat passed on the same discard.
        # Hold the pointer across a server refresh, just as a real click can.
        if width == 1280:
            box = choice.bounding_box()
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            page.mouse.down()
        page.wait_for_timeout(1300)
        expect(choices).to_have_count(3)
        assert choice.evaluate('n => n === window.pressedChoice')
        for button in choices.all():
            assert button.evaluate('n => {const r=n.getBoundingClientRect();return n.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}')
        page.screenshot(path=f'/tmp/club-chi-response-{width}.png')
        old = deepcopy(state)
        if width == 1280:
            page.mouse.up()
        else:
            choice.tap()
        expect(page.locator('#hand-guidance')).to_have_text('已选择吃 · 等待其他玩家回应')
        expect(page.locator('#meld-choices')).to_be_hidden()
        assert len(sent) == 1
        assert sent[0]['action'] == 'chi'
        assert sent[0]['payload']['tiles'] == [4, 12]
        accepted = deepcopy(state)
        state.clear(); state.update(old)  # A late poll must not reopen actions.
        page.wait_for_timeout(1300)
        expect(page.locator('#hand-guidance')).to_contain_text('已选择吃')
        expect(page.locator('#action-bar button')).to_have_count(0)
        state.clear(); state.update(accepted); game = state['game']

        # A new discard invalidates open choices, even with identical tile options.
        state['version'] += 1
        game.update(reaction_version=state['version'], reaction_action=None, actions=old['game']['actions'])
        expect(page.get_by_role('button', name='吃', exact=True)).to_be_visible()
        page.get_by_role('button', name='吃', exact=True).tap()
        expect(choices).to_have_count(3)
        state['version'] += 1; game['reaction_version'] = state['version']
        expect(page.locator('#meld-choices')).to_be_hidden()

        # A single chi combination and pon each submit directly on a touch tap.
        for action, label, tiles in [('chi', '吃', [0, 4]), ('pon', '碰', [9, 10])]:
            state['version'] += 1
            game.update(reaction_version=state['version'], reaction_action=None,
                        actions={'pass': True, action: [tiles]})
            button = page.get_by_role('button', name=label, exact=True)
            expect(button).to_be_visible()
            page.wait_for_timeout(1100)  # Ensure the old multi-choice buttons were replaced.
            button.tap()
            expect(page.locator('#hand-guidance')).to_have_text(f'已选择{label} · 等待其他玩家回应')
            assert sent[-1]['action'] == action
            assert sent[-1]['payload']['tiles'] == tiles
        assert len(sent) == 3
        assert errors == []
        browser.close()
