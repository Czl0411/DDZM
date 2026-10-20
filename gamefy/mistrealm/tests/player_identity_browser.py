"""Both seats see player identities in room and battle, including broken avatars."""
import json
from pathlib import Path
from time import time
from playwright.sync_api import sync_playwright
from dzmm_bot.core.mistrealm_state import new_state, player, project

state=new_state('a',int(time()*1000))
state['players'][1]=player('b')
seat=0
names=['自己的昵称','对手很长的昵称'*6]
def api(route):
    if route.request.url.endswith('/players/me'):
        body={'uid':'a','name':names[seat],'room_id':'identity-test'}
    elif route.request.url.endswith('/events'):
        route.fulfill(content_type='text/event-stream',body=': heartbeat\n\n');return
    else:
        view=project(state,seat)
        for i,p in enumerate(view['players']):p.update(name=names[i],avatar='https://avatar.test/'+str(i)+'.svg')
        body={'room_id':'identity-test','match_id':'test','code':'123456','state':view}
    route.fulfill(content_type='application/json',body=json.dumps(body))
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
    page=browser.new_page()
    page.route('**/api/mistrealm/**',api)
    page.route('https://avatar.test/0.svg',lambda r:r.fulfill(content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><rect width="80" height="80" fill="#65aabb"/></svg>'))
    page.route('https://avatar.test/1.svg',lambda r:r.fulfill(status=404,body='missing'))
    output=Path('.superpowers/identity');output.mkdir(parents=True,exist_ok=True)
    for phase in ['waiting','playing']:
        state['phase']=phase
        for seat in [0,1]:
            page.goto('http://127.0.0.1:18742/?player=identity-test')
            page.locator('.player-identity').first.wait_for(timeout=5000)
            assert page.locator('.player-identity').count()==2
            for name in names:assert name in page.locator('#main').inner_text()
            assert page.locator('.player-identity').filter(has_text='你').count()==1
            page.wait_for_function("document.querySelector('img[src=\"https://avatar.test/0.svg\"]')?.naturalWidth>0")
            page.wait_for_function("getComputedStyle(document.querySelector('img[src=\"https://avatar.test/1.svg\"]')).visibility==='hidden'")
            for width in [1366,390]:
                page.set_viewport_size({'width':width,'height':900})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(output/f'{phase}-{seat}-{width}.png'),full_page=True)
    browser.close()
print('PASS: identities from both seats, room/battle, loaded/broken avatars, long names, desktop/mobile')
