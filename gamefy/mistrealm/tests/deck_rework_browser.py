"""Deterministic browser interaction against real rules with intercepted HTTP snapshots."""
import json
import os
from pathlib import Path
from random import Random
from time import time

from playwright.sync_api import sync_playwright
from dzmm_bot.core.mistrealm_state import apply_action, project, new_state, player

base = os.environ.get('MISTREALM_DEV_URL', 'http://127.0.0.1:18742')
s = new_state('a', 0)
s['players'][1] = player('b')
s.update(phase='playing', round=1, turn=0, first_bonus=False, deadline_ms=int(time()*1000)+45000)
p = s['players'][0]
p['hand'] = [{'id': 'medic', 'key': 'neutral_medic'}, {'id': 'guide', 'key': 'raven_guide'},
             {'id': 'flag', 'key': 'crown_banner'}, {'id': 'infantry', 'key': 'crown_infantry'}]
p['discard'] = [{'id': 'bow', 'key': 'neutral_crossbow'}, {'id': 'excluded', 'key': 'neutral_mercenary'}]
s['players'][1]['passed'] = True
s['players'][1]['rows'][0] = [{'id':'enemy', 'key':'neutral_mercenary', 'power':7, 'armor':0}]
errors = []

def snapshot():
    return {'room_id': 'test', 'match_id': 'test-match', 'code': '123456', 'state': project(s, 0)}

def route_api(route):
    global s
    path = route.request.url.split('/api/mistrealm')[-1]
    if path == '/players/me':
        body = {'uid': 'a', 'name': '测试旅人', 'room_id': 'test'}
    elif path.endswith('/actions'):
        request = route.request.post_data_json
        s = apply_action(s, 0, request['action'], request['payload'], int(time()*1000), Random(42))
        body = snapshot()
    elif path.endswith('/events'):
        route.fulfill(status=200, content_type='text/event-stream', body=': heartbeat\n\n')
        return
    else:
        body = snapshot()
    route.fulfill(status=200, content_type='application/json', body=json.dumps(body))

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True)
    page = browser.new_page(viewport={'width': 1366, 'height': 1000})
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/api/mistrealm/**', route_api)
    page.goto(base+'/?player=deck-test')
    page.locator('[data-card="medic"]').click()
    page.locator('.revive-options [data-card="bow"]').wait_for()
    assert page.locator('.revive-options [data-card="excluded"]').count() == 0
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    output=Path('.superpowers/sdd/2026-10-15-mistrealm/screenshots')
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output/'deck-revive-mobile.png'),full_page=True)
    page.locator('.revive-options [data-card="bow"]').click()
    page.locator('#play').click()
    page.locator('.battle-row [data-card="bow"]').wait_for()
    assert s['players'][1]['rows'][0][0]['power'] == 7
    page.locator('.hand [data-card="guide"]').click()
    page.locator('.battle-row [data-card="bow"]').click()
    page.locator('#play').click()
    page.locator('.hand [data-card="bow"]').wait_for()
    page.locator('.hand [data-card="bow"]').click()
    page.locator('[data-card="enemy"]').click()
    page.locator('#play').click()
    page.wait_for_function("!document.querySelector('#play')")
    assert s['players'][1]['rows'][0][0]['power'] == 4
    page.locator('.hand [data-card="flag"]').click()
    page.locator('[data-owner="0"][data-row="0"]').click()
    page.locator('#play').click()
    page.locator('.battle-row [data-card="flag"]').wait_for()
    page.locator('.hand [data-card="infantry"]').click()
    page.locator('#play').click()
    page.locator('.battle-row [data-card="infantry"]').wait_for()
    assert s['players'][0]['rows'][0][-1]['power'] == 9
    page.set_viewport_size({'width':1366,'height':1000})
    page.screenshot(path=str(output/'deck-combo-desktop.png'),full_page=True)
    assert not errors, errors
    browser.close()
print('PASS: discard targeting, revive without deployment, recall/redeploy damage, front-row banner synergy, mobile overflow')
