"""Check the scene under crowded, rotated and reduced-motion states."""
from pathlib import Path
from urllib.parse import urlsplit
import pytest
from playwright.sync_api import sync_playwright,expect
from test_club_sandbox import playing_snapshot

@pytest.mark.parametrize('width,height,reduced',[(1280,720,False),(844,390,False),(390,844,False),(320,700,True),(624,704,False)])
def test_mahjong_scene(width,height,reduced):
    publish=Path(__file__).resolve().parents[1]/'publish'
    state=playing_snapshot();state['seat']=2;state['game']['turn']=2
    game=state['game'];game['hand']=[0,4,8,36,40,44,108,124];game['hand_counts']=[13,13,8,13]
    game['actions']={'discard':game['hand'],'riichi':[0]}
    for seat in range(4):
        game['discards'][seat]=[{'tile':n*4+seat,'riichi':False,'called':False} for n in range(18)]
    game['melds'][2]=[{'kind':'pon','tiles':[12,13,14],'called_tile':14,'from':1,'open':True},{'kind':'ankan','tiles':[16,17,18,19],'open':False}]
    game['hints']={'current':None,'discards':{'0':{'waits':[{'type':24,'unseen':2,'ron_reason':None,'tsumo_reason':None},{'type':25,'unseen':1,'ron_reason':'no_yaku','tsumo_reason':None}],'furiten':None,'closed':True}}}
    errors=[];sent=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        ctx=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce' if reduced else 'no-preference')
        ctx.add_init_script("window.dzmm={user:{info:async()=>({id:'preview'})},getLaunchParams:async()=>({roomId:'"+state['id']+"'}),loading:{ready(){},progress(){},error(){}}};const original=window.fetch;window.fetch=(url,opts)=>String(url).endsWith('/events')?Promise.resolve(new Response(new ReadableStream({start(){}}))):original(url,opts);")
        def route(r):
            path=urlsplit(r.request.url).path;headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'}
            if r.request.method=='OPTIONS':r.fulfill(status=204,headers=headers)
            elif '/api/club/mahjong/rooms/' in path:
                if path.endswith('/actions') and r.request.method=='POST':sent.append(r.request.post_data_json)
                r.fulfill(json=state,headers=headers)
            elif path.endswith('/session'):r.fulfill(json={'id':'preview','uid':'preview','name':'预览'},headers=headers)
            elif path.endswith('/presence'):r.fulfill(json={'online':4,'playing':4},headers=headers)
            elif '/api/' in path:r.fulfill(json=[],headers=headers)
            else:r.fulfill(path=str(publish/(path.lstrip('/') or 'index.html')),headers=headers)
        ctx.route('**/*',route);page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('https://club.test/')
        expect(page.locator('#hand .tile')).to_have_count(8)
        page.evaluate('document.fonts.ready')
        page.evaluate('''() => {
            window.flights=[];
            new MutationObserver(records=>records.forEach(record=>record.addedNodes.forEach(n=>{
                if(n.nodeType!==1||!n.classList.contains('tile-flight'))return;
                const frame=n.getAnimations()[0].effect.getKeyframes()[0],m=new DOMMatrix(frame.transform);
                flights.push({x:parseFloat(n.style.left)+parseFloat(n.style.width)/2+m.e,y:parseFloat(n.style.top)+parseFloat(n.style.height)/2+m.f});
            }))).observe(document.body,{childList:true});
        }''')
        expect(page.locator('.river-self')).to_have_attribute('data-seat','2')
        expect(page.locator('.river-right')).to_have_attribute('data-seat','3')
        expect(page.locator('.meld-self .tile-back')).to_have_count(2)
        expect(page.locator('.concealed svg')).to_have_count(0)
        page.locator('#hand .tile').first.click()
        expect(page.locator('#hand .tile').first).to_have_attribute('aria-pressed','true')
        expect(page.locator('#action-bar')).to_contain_text('立直打出')
        expect(page.locator('#hand .tenpai-badge')).to_have_count(1)
        expect(page.locator('#hand-guidance')).to_contain_text('未见3张')
        hint_button='#hand-hints-button' if (height<=740 and width/height<.7) or (width>height and height<=520) else '#wait-preview'
        expect(page.locator(hint_button)).to_be_visible()
        expect(page.locator(hint_button)).to_contain_text('部分受限')
        expect(page.locator('#wait-preview .wait-permission')).to_have_text(['可胡','仅自摸'])
        page.locator(hint_button).click()
        expect(page.locator('#hand-hints-dialog')).to_be_visible()
        expect(page.locator('#hand-hints-list')).to_contain_text('荣和无役')
        expect(page.locator('#hand-hints-list .wait-tile')).to_have_count(2)
        page.screenshot(path=f'/tmp/mahjong-hints-{width}.png')
        page.locator('#mahjong-rules summary').click()
        expect(page.locator('#mahjong-rules')).to_contain_text('宝牌只能加番')
        assert page.locator('#hand-hints-dialog').evaluate('n => n.scrollWidth <= n.clientWidth')
        page.locator('#close-hand-hints').click()
        page.wait_for_timeout(180)
        bounds=page.evaluate("""() => {
            const box=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom}};
            return {hand:box('#hand'),actions:box('#action-bar'),meld:box('.meld-self'),tiles:[...document.querySelectorAll('#hand .tile')].map(n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom}}),w:document.body.scrollWidth,h:document.body.scrollHeight};
        }""")
        assert bounds['w']<=width and bounds['h']<=height
        # Face artwork must stay on the ivory front at portrait/tablet ratios too.
        assert page.locator('#mahjong-table').evaluate("n => getComputedStyle(n).backgroundImage.includes('mahjong-table.webp')")
        assert page.locator('#hand .tile').first.evaluate("n => getComputedStyle(n).backgroundImage.includes('mahjong-tile-v1.webp')")
        for face in page.locator('#hand .tile-face').all():
            assert face.evaluate('''n => {
                const r=n.getBoundingClientRect(),t=n.parentElement.getBoundingClientRect();
                const b=n.getBBox();
                return r.left>=t.left && r.right<=t.right && r.top>=t.top && r.bottom<=t.bottom &&
                    b.x>=0 && b.y>=0 && b.x+b.width<=100 && b.y+b.height<=130;
            }''')
        for tile in bounds['tiles']:assert tile['x']>=0 and tile['right']<=width and tile['bottom']<=height
        def intersects(a,b):return min(a['right'],b['right'])>max(a['x'],b['x']) and min(a['bottom'],b['bottom'])>max(a['y'],b['y'])
        assert not intersects(bounds['actions'],bounds['meld']),bounds
        assert not intersects(bounds['actions'],bounds['hand']),bounds
        for position in ('left','top','right'):
            def rect(selector):
                return page.locator(selector).evaluate('n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom}}')
            assert not intersects(rect(f'.seat-rack-{position}'),rect(f'.river-{position}')),position
        origin=page.locator('.concealed-right .tile').last.bounding_box()
        state['version']+=1;state['game']['discards'][3].append({'tile':131,'riichi':True,'called':False})
        # Room polling receives the updated fixture.
        expect(page.locator('.river-right .latest-discard')).to_have_attribute('data-id','131')
        expect(page.locator('#opponent-right .player-action')).to_contain_text('立直')
        if not reduced:
            expect(page.locator('#table-callout')).to_be_visible()
            flight=page.evaluate('flights[0]')
            assert abs(flight['x']-origin['x']-origin['width']/2)<1
            assert abs(flight['y']-origin['y']-origin['height']/2)<1
        else:expect(page.locator('#table-callout')).to_be_hidden()
        page.wait_for_timeout(1000)
        expect(page.locator('.tile-flight')).to_have_count(0)
        expect(page.locator('#table-callout')).to_be_hidden()
        # A called tile flies from the source river to the caller's exposed meld.
        origin=page.locator('.river-right .latest-discard').bounding_box()
        page.evaluate('flights=[]')
        game['discards'][3][-1]['called']=True
        game['melds'][0]=[{'kind':'pon','tiles':[128,129,131],'called_tile':131,'from':3,'open':True}]
        game['hand_counts'][0]=11;state['version']+=1
        expect(page.locator('#opponent-top .player-action')).to_have_text('碰 發')
        expect(page.locator('#mahjong-cue')).to_contain_text('北风的發')
        if not reduced:
            expect(page.locator('#table-callout')).to_be_visible()
            flight=page.evaluate('flights[0]')
            assert abs(flight['x']-origin['x']-origin['width']/2)<1
            assert abs(flight['y']-origin['y']-origin['height']/2)<1
        page.wait_for_timeout(800)
        expect(page.locator('.tile-flight')).to_have_count(0)
        state['version']+=1;state['phase']='reaction';state['game']['actions']={'pass':True,'pon':[[0,4]],'chi':[[4,8],[8,16],[16,20]],'kan':[[0,1,2]],'ron':True}
        # Room polling receives the updated fixture.
        expect(page.locator('#turn-status')).to_have_text('等待你的回应')
        expect(page.locator('#self-player')).to_have_class('player self-player active')
        expect(page.locator('#action-bar')).to_contain_text('碰')
        expect(page.locator('#hand .tile:not(:disabled)')).to_have_count(0)
        page.locator('#action-bar button',has_text='吃').click()
        expect(page.locator('#meld-choices .meld-choice')).to_have_count(3)
        expect(page.locator('#action-bar button',has_text='吃')).to_have_attribute('aria-expanded','true')
        for button in page.locator('#action-bar button, #meld-choices button').all():
            assert button.evaluate('''n=>{const r=n.getBoundingClientRect();const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return r.x>=0&&r.right<=innerWidth&&r.y>=0&&r.bottom<=innerHeight&&n.contains(hit)}''')
        page.screenshot(path=f'/tmp/mahjong-response-{width}.png')
        page.locator('#meld-choices .cancel-choice').click()
        expect(page.locator('#meld-choices')).to_be_hidden()
        page.locator('#action-bar .pass-action').click()
        expect(page.locator('#pass-win-dialog')).to_be_visible()
        expect(page.locator('#pass-win-note')).to_contain_text('暂时振听')
        page.locator('#cancel-pass-win').click()
        expect(page.locator('#action-bar')).to_contain_text('荣和')
        page.locator('#action-bar .pass-action').click()
        state['version']+=1;state['game']['actions']={}
        expect(page.locator('#pass-win-dialog')).to_be_hidden()
        expect(page.locator('#hand-guidance')).to_contain_text('等待其他玩家回应')
        expect(page.locator('#turn-status')).to_have_text('等待其他玩家回应')
        expect(page.locator('.player.active')).to_have_count(0)
        page.screenshot(path=f'/tmp/mahjong-crowded-{width}.png')
        # Tap to inspect, tap again to discard: one request, exact physical tile.
        state['version']+=1;state['phase']='playing';game['actions']={'discard':game['hand']}
        expect(page.locator('#hand .tile:not(:disabled)')).to_have_count(8)
        page.locator('#hand .tile').first.click()
        assert sent==[]
        page.locator('#hand .tile').first.click()
        expect(page.locator('#hand .tile').first).to_have_attribute('aria-pressed','false')
        assert len(sent)==1 and sent[0]['action']=='discard' and sent[0]['payload']=={'tile':0}
        # Four exposed melds must remain attached to each opponent and inside the screen.
        for seat in (0,1,3):
            game['hand_counts'][seat]=1
            game['melds'][seat]=[{'kind':'pon','tiles':[i*4,i*4+1,i*4+2],'called_tile':i*4+2,'from':2,'open':True} for i in range(4)]
        state['version']+=1
        expect(page.locator('.seat-rack .meld')).to_have_count(12)
        page.screenshot(path=f'/tmp/mahjong-melds-{width}.png')
        for rack in page.locator('.seat-rack').all():
            assert rack.evaluate('n=>{const r=n.getBoundingClientRect();return r.x>=0&&r.right<=innerWidth&&r.y>=0&&r.bottom<=innerHeight}'),rack.evaluate('n=>({rect:n.getBoundingClientRect().toJSON(),css:getComputedStyle(n).transform,left:getComputedStyle(n).left,parent:n.parentNode.getBoundingClientRect().toJSON()})')
        game['hints']={'current':{'waits':[{'type':i,'unseen':3,'ron_reason':None,'tsumo_reason':None} for i in range(13)],'furiten':None},'discards':{}}
        state['version']+=1
        expect(page.locator('#wait-preview')).to_contain_text('共13种')
        assert page.locator('#wait-preview').evaluate('n=>n.scrollWidth<=n.clientWidth')
        # The reported 5/8-man shape must say no yaku without opening a dialog.
        waits=[{'type':i,'unseen':n,'ron_reason':'no_yaku','tsumo_reason':'no_yaku'} for i,n in [(4,0),(7,2)]]
        game['hints']={'current':{'waits':waits,'furiten':None,'closed':False},'discards':{}}
        state['version']+=1
        expect(page.locator(hint_button)).to_contain_text('无役')
        expect(page.locator('#wait-preview .wait-permission')).to_have_text(['无役','无役'])
        expect(page.locator('#wait-preview')).to_contain_text('缺少役种，通常不能胡')
        if page.locator('#wait-preview').is_visible():
            assert page.locator('#wait-preview').evaluate('n=>n.scrollWidth<=n.clientWidth')
            for selector in ['.meld-self','#hand','.river-self']:
                assert not intersects(rect('#wait-preview'),rect(selector)),selector
        page.screenshot(path=f'/tmp/mahjong-no-yaku-{width}.png')
        page.locator(hint_button).click()
        expect(page.locator('#hand-hints-note')).to_contain_text('无役＝缺少有效胡牌条件')
        expect(page.locator('#hand-hints-list .wait-tile').first).to_contain_text('荣和无役 · 自摸无役')
        page.locator('#close-hand-hints').click()
        game['hints']['current']['furiten']='discard'
        for item in waits:item['ron_reason']='discard'
        state['version']+=1
        expect(page.locator(hint_button)).to_contain_text('弃牌振听')
        expect(page.locator('#wait-preview')).to_contain_text('普通自摸也无役')
        # The legal action wins over generic guidance, including a special-yaku ron.
        game['hints']['current']['furiten']=None
        for item in waits:item['ron_reason']='no_yaku'
        waits[1]['ron_now']=True
        game['actions']={'ron':True,'pass':True};state['phase']='reaction'
        state['version']+=1
        expect(page.locator(hint_button)).to_contain_text('可荣和')
        expect(page.locator('#wait-preview .wait-permission')).to_have_text(['无役','可荣和'])
        expect(page.locator('#action-bar')).to_contain_text('荣和')
        # A legal special-yaku self draw is clear even with a complete 14-tile hand.
        game['hand']=list(range(0,56,4));game['melds'][2]=[]
        game['actions']={'tsumo':True,'discard':game['hand']};state['phase']='playing'
        game['hints']={'current':None,'discards':{'0':{'waits':[{'type':4,'unseen':1,'ron_reason':'no_yaku','tsumo_reason':'no_yaku'}],'furiten':None}}}
        state['version']+=1
        expect(page.locator('#hand-hints-button')).to_contain_text('可自摸')
        page.locator('#hand-hints-button').click()
        expect(page.locator('#hand-hints-note')).to_contain_text('本次已满足和牌条件')
        page.locator('#close-hand-hints').click()
        expect(page.locator('#hand .tile').first.locator('.tenpai-badge')).to_have_text('无役')
        page.locator('#hand .tile').first.click()
        expect(page.locator(hint_button)).to_contain_text('无役')
        page.wait_for_timeout(200)
        if page.locator('#wait-preview').is_visible():
            for tile in page.locator('#hand .tile').all():
                tile_rect=tile.evaluate('n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom}}')
                assert not intersects(rect('#wait-preview'),tile_rect)
        page.screenshot(path=f'/tmp/mahjong-full-hand-hints-{width}.png')
        assert not errors
        browser.close()
