"""Queue timer must progress even when the device clock is behind the server."""
import json
import os
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
    page=browser.new_page()
    page.add_init_script('Date.now = () => 0;')
    started=None
    heartbeats=[]
    def queue():
        return {'status':'waiting','ticket':'clock-test','queued_at_ms':1792000000000,
                'expires_at_ms':1792000020000,'elapsed_ms':int((time.monotonic()-started)*1000)}
    def api(route):
        global started
        path=route.request.url.split('/api/mistrealm')[1]
        if path=='/players/me':
            result={'name':'计时测试','room_id':None,'matchmaking':queue() if started else {'status':'idle'}}
        elif path=='/matchmaking':
            started=time.monotonic();result=queue()
        elif path=='/matchmaking/heartbeat':
            heartbeats.append(True);result=queue()
        elif path=='/matchmaking/cancel':
            started=None;result={'status':'idle'}
        else: raise AssertionError(path)
        route.fulfill(status=200,content_type='application/json',body=json.dumps(result))
    page.route('**/api/mistrealm/**',api)
    page.goto(os.environ.get('MISTREALM_DEV_URL','http://127.0.0.1:18742')+'/?player=clock-test')
    page.locator('#match-start').click()
    page.wait_for_function("Number(document.querySelector('#match-elapsed')?.textContent)>=3",timeout=6500)
    assert heartbeats
    page.reload()
    page.wait_for_function("Number(document.querySelector('#match-elapsed')?.textContent)>=3")
    page.locator('#match-cancel').click()
    page.locator('#match-start').wait_for()
    browser.close()
    print('PASS: skewed device clock, elapsed progression, heartbeat, reload recovery, cancellation')
