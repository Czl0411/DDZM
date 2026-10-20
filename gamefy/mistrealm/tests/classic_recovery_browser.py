"""Entry-version and uncertain-cancel recovery against the loopback preview only."""
from uuid import uuid4
import httpx
from playwright.sync_api import sync_playwright, expect

BASE='http://127.0.0.1:18744'
failures=[]

def user():
    uid='recovery-'+str(uuid4())
    c=httpx.Client(base_url=BASE+'/api/mistrealm',headers={'Authorization':'MistrealmUid '+uid})
    c.post('/players/me',json={'name':'恢复测试','avatar':None}).raise_for_status()
    return uid,c

def post(c,path,body):
    r=c.post(path,json=body);r.raise_for_status();return r.json()

def deck(c):
    d=httpx.get(BASE+'/classic/cards.json').json()['starters'][0]
    return post(c,'/classic/decks',d)['id']

def create(c,classic):
    body={'request_id':str(uuid4())}
    if classic:body['deck_id']=deck(c)
    return post(c,('/classic' if classic else '')+'/rooms',body)

with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
    context=browser.new_context()
    def local_only(route):
        if not route.request.url.startswith(BASE+'/'):route.abort();return
        if route.request.url==BASE+'/config.js':route.fulfill(content_type='text/javascript',body="export const CONFIG={apiBase:''};")
        else:route.continue_()
    context.route('**/*',local_only)
    for classic in (True,False):
        for queued in (False,True):
            uid,c=user();prefix='/classic' if classic else ''
            if queued:
                value=post(c,prefix+'/matchmaking',{'deck_id':deck(c)} if classic else {})
            else:
                value=create(c,classic)
                if classic:
                    _,op=user()
                    joined=post(op,'/classic/rooms/join',{'code':value['code'],'deck_id':deck(op),'request_id':str(uuid4())})
                    for actor in (c,op):
                        current=actor.get('/rooms/'+value['room_id']).json()
                        post(actor,'/classic/rooms/'+value['room_id']+'/actions',dict(action='lock',payload={},request_id=str(uuid4()),version=current['state']['version'],match_id=current['match_id']))
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            try:
                page.goto(BASE+('/' if classic else '/classic/')+'?player='+uid)
                page.wait_for_url(BASE+('/classic/' if classic else '/')+'?player='+uid,timeout=6000)
                selector=('#cancel-match' if classic else '#match-cancel') if queued else ('#confirm-mulligan' if classic else '#ready')
                expect(page.locator(selector)).to_be_visible()
                assert not errors,errors
                profile=c.get('/players/me').json()
                assert profile['matchmaking']['ticket']==value['ticket'] if queued else profile['room_id']==value['room_id']
            except Exception as e:failures.append(f'entry classic={classic} queued={queued}: {e}')
            finally:
                page.close()
                if queued:post(c,prefix+'/matchmaking/cancel',{'ticket':value['ticket']})
                c.close()
    # A dropped cancel request must resume heartbeats; a dropped successful response must settle idle.
    for processed in (False,True):
        uid,c=user();page=context.new_page()
        try:
            page.goto(BASE+'/classic/?player='+uid);expect(page.locator('#quick-match')).to_be_visible()
            page.locator('#quick-match').click();expect(page.locator('#cancel-match')).to_be_visible()
            page.wait_for_function('Number(document.querySelector("#elapsed")?.textContent)>=2')
            def drop_cancel(route):
                if processed:route.fetch()
                route.abort()
            page.route('**/classic/matchmaking/cancel',drop_cancel)
            with page.expect_response(lambda r:'/classic/matchmaking/heartbeat' in r.url,timeout=10000):
                page.locator('#cancel-match').click()
            page.unroute('**/classic/matchmaking/cancel',drop_cancel)
            if processed:expect(page.locator('#quick-match')).to_be_visible()
            else:
                expect(page.locator('#cancel-match')).to_be_visible()
                assert int(page.locator('#elapsed').inner_text())>=2
                _,op=user();post(op,'/classic/matchmaking',{'deck_id':deck(op)})
                expect(page.locator('#confirm-mulligan')).to_be_visible(timeout=10000)
                op.close()
        except Exception as e:failures.append(f'cancel processed={processed}: {e}')
        finally:
            page.close()
            pending=c.get('/players/me').json().get('matchmaking',{})
            if pending.get('status')=='waiting':post(c,'/classic/matchmaking/cancel',{'ticket':pending['ticket']})
            c.close()
    browser.close()
assert not failures,'\n'.join(failures)
print('Both entry directions preserve rooms/queues; dropped cancel request/response recover waiting, paired and idle states')
