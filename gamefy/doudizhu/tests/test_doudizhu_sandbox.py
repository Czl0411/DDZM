import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest
from playwright.sync_api import sync_playwright, expect


@pytest.mark.parametrize('width', [320, 390, 1280])
def test_table_in_sandbox(width):
    publish = Path(__file__).resolve().parents[1] / 'publish'
    room = '11111111-1111-4111-8111-111111111111'
    saved, actions = {}, []
    now = datetime.now(timezone.utc)
    state = dict(id=room, short_id='ABC123', round_id=None, version=0, phase='waiting', seat=None,
                 players=[dict(name='房主', ready=False, count=0, trustee=False),None,None],
                 hand=[], bottom=[], turn=None, landlord=None, bid=0, multiplier=1, previous=None,
                 table=[None]*3, result=None, events=[], messages=[], server_time=now.isoformat(),
                 deadline=(now+timedelta(minutes=10)).isoformat())
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome', headless=True)
        context=browser.new_context(viewport={'width':width,'height':1000})
        context.expose_function('saveRoom',lambda k,v:saved.update({k:v}))
        context.expose_function('readRoom',lambda k:{'value':saved.get(k)})
        context.add_init_script("window.dzmm={user:{info:async()=>({id:'alice'})},kv:{get:async k=>readRoom(k),put:async(k,v)=>saveRoom(k,v)},loading:{ready(){},error(){}}};")
        def route(r):
            url=r.request.url
            headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'}
            if r.request.method=='OPTIONS':
                r.fulfill(status=204,headers=headers);return
            if '/api/doudizhu/' in url:
                if url.endswith('/events'):
                    r.fulfill(body='',content_type='text/event-stream',headers=headers);return
                if url.endswith('/actions'):
                    data=r.request.post_data_json;actions.append(data)
                    action=data['action']; state['version']+=1
                    if action=='claim':
                        state['seat']=1
                        state['players']=[dict(name=n,ready=False,count=0,trustee=False) for n in ('房主','我','好友')]
                    if action=='ready':
                        state.update(phase='bidding',turn=1,hand=list(range(17)),round_id=room)
                        for player in state['players']: player.update(count=17,online=True)
                        state['deadline']=(now+timedelta(seconds=15)).isoformat()
                    if action=='bid':
                        state.update(phase='playing',landlord=1,hand=list(range(20)),bid=3,multiplier=3,bottom=[17,18,19])
                        state['players'][1]['count']=20
                        state['deadline']=(now+timedelta(seconds=25)).isoformat()
                    if action=='play':
                        state['hand']=[c for c in state['hand'] if c not in data['payload']['cards']]
                        state['turn']=2
                if url.endswith('/chat'):
                    state['messages']=[dict(id='m',name='我',text=r.request.post_data_json['text'])]
                body=[dict(id=room,short_id='ABC123',phase='waiting',occupied=1)] if url.endswith('/rooms') else state
                if url.endswith('/suggestions'):body=[{'cards':[0]}]
                r.fulfill(body=json.dumps(body),content_type='application/json',headers=headers);return
            if url.endswith('/host'):
                r.fulfill(body='<body style="margin:0"><iframe style="border:0;width:100%;height:1000px" sandbox="allow-scripts allow-modals" src="/index.html"></iframe>',content_type='text/html');return
            if url.endswith('/config.js'):
                r.fulfill(body="window.DOUDIZHU_CONFIG={apiBase:'https://ddz.test'};",content_type='text/javascript',headers=headers);return
            r.fulfill(path=str(publish / url.rsplit('/',1)[-1]),headers=headers)
        context.route('**/*',route)
        page=context.new_page()
        page.on('pageerror', lambda error: print('Browser error:', error))
        page.on('console', lambda message: print('Browser console:', message.text) if message.type=='error' else None)
        page.set_default_timeout(6000)
        page.goto('https://ddz.test/host')
        frame=page.frame_locator('iframe')
        expect(frame.locator('#feedback')).not_to_have_text('正在读取玩家身份…')
        assert frame.locator('#feedback').inner_text() == ''
        frame.locator('#rooms button').click()
        frame.locator('#code').fill('1234');frame.locator('#claim').click()
        frame.locator('[data-action="ready"]').click()
        frame.locator('[data-score="3"]').click()
        expect(frame.locator('#hand .card')).to_have_count(20)
        first = frame.locator('#hand .card').first
        first.dispatch_event('pointerdown', {'pointerId': 1})
        first.dispatch_event('pointercancel', {'pointerId': 1})
        expect(frame.locator('#hand .selected')).to_have_count(1)
        assert actions[-1]['action'] == 'bid'
        first.focus();first.press('Enter')
        expect(frame.locator('#hand .selected')).to_have_count(0)
        assert frame.locator('body').evaluate('e=>e.scrollWidth <= innerWidth')
        page.screenshot(path=f'/tmp/doudizhu-{width}.png',full_page=True)
        frame.locator('#hint').click()
        expect(frame.locator('#hand .selected')).to_have_count(1)
        frame.locator('#play').click()
        expect(frame.locator('#hand .card')).to_have_count(19)
        state['events']=[dict(seat=2,play=dict(kind='bomb',cards=[24,25,26,27]))]
        state['version']+=1
        expect(frame.locator('#feedback')).to_contain_text('炸弹')
        assert frame.locator('#feedback').evaluate('e=>getComputedStyle(e).animationName') != 'none'
        assert actions[-1]['payload']['cards']==[0]
        frame.locator('#chat summary').click()
        frame.locator('#chat-input').fill('<b>好牌</b>');frame.locator('#chat-send').click()
        expect(frame.locator('#messages')).to_contain_text('<b>好牌</b>')
        assert frame.locator('#messages b').count()==0
        page.reload();expect(frame.locator('#table')).to_be_visible()
        expect(frame.locator('#hand .card')).to_have_count(19)
        frame.locator('#back').click();expect(frame.locator('#lobby')).to_be_visible()
        browser.close()


def test_slow_previous_room_does_not_override_new_navigation():
    publish = Path(__file__).resolve().parents[1] / 'publish'
    a, b = '11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'
    saved, held, streams = {}, [], []
    now = datetime.now(timezone.utc)
    def snapshot(rid):
        return dict(id=rid, short_id='A' if rid==a else 'B', round_id=None, version=0,
            phase='waiting', seat=None, players=[None]*3, hand=[], bottom=[], turn=None,
            landlord=None, bid=0, multiplier=1, previous=None, table=[None]*3,
            result=None, events=[], messages=[], server_time=now.isoformat(),
            deadline=(now+timedelta(minutes=10)).isoformat())
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page()
        page.expose_function('saveRoom',lambda k,v:saved.update({k:v}))
        page.add_init_script("window.dzmm={user:{info:async()=>({id:'viewer'})},kv:{get:async()=>({}),put:async(k,v,options)=>{if(options?.flush)return saveRoom(k,v);}}};")
        def route(r):
            url=r.request.url
            if url.endswith('/config.js'):
                r.fulfill(body="window.DOUDIZHU_CONFIG={apiBase:'https://ddz.test'};",content_type='text/javascript');return
            if url.endswith('/rooms'):
                r.fulfill(json=[dict(id=rid,short_id=label,phase='waiting',occupied=1) for rid,label in ((a,'A'),(b,'B'))]);return
            if url.endswith('/events'):
                streams.append(url);r.fulfill(body='',content_type='text/event-stream');return
            if '/api/doudizhu/rooms/' in url:
                rid=url.rsplit('/',1)[-1]
                if rid==a and not held:held.append(r);return
                r.fulfill(json=snapshot(rid));return
            r.fulfill(path=str(publish / url.rsplit('/',1)[-1]))
        page.route('**/*',route)
        page.goto('https://ddz.test/index.html')
        page.locator('#rooms button').nth(0).click()
        page.locator('#rooms button').nth(1).click()
        expect(page.locator('#room-label')).to_have_text('房间 B')
        with page.expect_response(lambda r:r.url.endswith('/'+a)):
            held[0].fulfill(json=snapshot(a))
        # Let the completed fetch and its JSON continuation finish before checking side effects.
        page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
        expect(page).to_have_url('https://ddz.test/index.html#room='+b)
        assert saved['doudizhu:last-room:viewer']==b
        assert streams and all('/'+b+'/events' in url for url in streams)
        browser.close()
