"""Settlement stays readable and the next hand needs explicit readiness."""
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import pytest
from playwright.sync_api import expect, sync_playwright
from test_club_sandbox import playing_snapshot

@pytest.mark.parametrize('width,height',[(1280,720),(844,390),(390,844),(320,700)])
def test_settlement_breakdown_and_manual_ready(width,height):
    publish=Path(__file__).resolve().parents[1]/'publish'
    state=playing_snapshot();state.update(phase='hand_finished',room_type='coin',buy_in=5,deadline=None)
    for player in state['players']:player['ready']=False
    result={'kind':'ron','winners':[0],'loser':1,'tile':38,'deltas':[2900,-2900,0,0],'details':[{'seat':0,'han':2,'fu':30,'yaku':['立直','平和'],'limit':''}]}
    state['game'].update(actions={},result=result,last_hand_result=result,points=[27900,22100,25000,25000],winning_hands={'0':[0,4,8,12,16,20,40,44,48,72,76,80,36]})
    state['settlement']={'order':[0,2,3,1],'net':[8,-8,0,0],'refunds':[5]*4,'transfers':[{'from':1,'to':0,'points':2900,'coins':8}]}
    sent=[];errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        ctx=browser.new_context(viewport={'width':width,'height':height})
        ctx.add_init_script("window.dzmm={user:{info:async()=>({id:'preview'})},getLaunchParams:async()=>({roomId:'"+state['id']+"'}),loading:{ready(){},progress(){},error(){}}};const original=window.fetch;window.fetch=(url,opts)=>String(url).endsWith('/events')?Promise.resolve(new Response(new ReadableStream({start(){}}))):original(url,opts);")
        def route(r):
            path=urlsplit(r.request.url).path;headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'}
            if r.request.method=='OPTIONS':r.fulfill(status=204,headers=headers)
            elif '/api/club/mahjong/rooms/' in path:
                if path.endswith('/actions') and r.request.method=='POST':
                    body=r.request.post_data_json;sent.append(body);state['version']+=1
                    if body['action']=='ready':
                        for player in state['players']:player['ready']=True
                    elif body['action']=='start':
                        state.update(phase='playing',settlement=None);state['game'].update(result=None,last_hand_result=None)
                state['server_time']=datetime.now(timezone.utc).isoformat();r.fulfill(json=state,headers=headers)
            elif path.endswith('/session'):r.fulfill(json={'id':'preview','uid':'preview','name':'预览'},headers=headers)
            elif path.endswith('/presence'):r.fulfill(json={'online':4,'playing':0},headers=headers)
            elif '/api/' in path:r.fulfill(json=[],headers=headers)
            else:r.fulfill(path=str(publish/(path.lstrip('/') or 'index.html')),headers=headers)
        ctx.route('**/*',route);page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('https://club.test/')
        expect(page.locator('#result')).to_be_visible()
        expect(page.locator('#self-player')).to_contain_text('庄家')
        expect(page.locator('.coin-breakdown')).to_contain_text('2900点 ÷ 2000 × 5 ＝ 8币')
        expect(page.locator('.result-rows')).to_contain_text('本局摸鱼币 -8')
        expect(page.get_by_role('button',name='等待准备 0/4')).to_be_disabled()
        assert page.locator('#result').evaluate('n=>n.scrollWidth<=n.clientWidth')
        for button in page.locator('.result-actions button').all():
            r=button.bounding_box();assert r['x']>=0 and r['x']+r['width']<=width and r['y']+r['height']<=height
        page.screenshot(path=f'/tmp/mahjong-settlement-{width}.png')
        page.get_by_role('button',name='准备下一局',exact=True).click()
        expect(page.get_by_role('button',name='开始下一局',exact=True)).to_be_enabled()
        assert [item['action'] for item in sent]==['ready']
        page.get_by_role('button',name='开始下一局',exact=True).click()
        expect(page.locator('#result')).to_be_hidden()
        assert [item['action'] for item in sent]==['ready','start']
        assert not errors
        browser.close()
