"""Exercise the real entry in an opaque SDK iframe, routing every request locally."""
import html
import mimetypes
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from uuid import uuid4
import httpx
from playwright.sync_api import sync_playwright,expect

ROOT=Path(sys.argv[1]).resolve()/'publish'
BASE='http://127.0.0.1:18744'
class Handler(BaseHTTPRequestHandler):
    document=''
    def log_message(self,*args):pass
    def do_OPTIONS(self):self.reply(b'',204,'text/plain')
    def reply(self,data,status=200,kind='text/html; charset=utf-8'):
        self.send_response(status);self.send_header('Content-Type',kind)
        self.send_header('Access-Control-Allow-Origin','*');self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type')
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.end_headers();self.wfile.write(data)
    def do_GET(self):self.handle_request()
    def do_POST(self):self.handle_request()
    def handle_request(self):
        if self.path=='/platform-sandbox':self.reply(self.document.encode());return
        if self.path.startswith('/platform-assets/'):
            name=self.path.split('/platform-assets/',1)[1].split('?',1)[0];path=ROOT/name
            if name in ('config.js','classic/config.js'):data=("export const CONFIG={apiBase:'"+SURFACE+"'};").encode()
            elif path.is_file():data=path.read_bytes()
            else:self.reply(b'missing',404);return
            self.reply(data,kind=mimetypes.guess_type(str(path))[0] or 'application/octet-stream');return
        if self.path.startswith('/api/'):
            if self.path.endswith('/events'):self.reply(b': heartbeat\n\n',kind='text/event-stream');return
            data=self.rfile.read(int(self.headers.get('Content-Length',0)))
            r=httpx.request(self.command,BASE+self.path,content=data,headers={k:v for k,v in self.headers.items() if k.lower() in ('authorization','content-type')})
            self.reply(r.content,r.status_code,'application/json');return
        self.reply(b'missing',404)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
SURFACE='http://127.0.0.1:'+str(server.server_port)
threading.Thread(target=server.serve_forever,daemon=True).start()
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True,args=['--disable-features=LocalNetworkAccessChecks'])
    for mode in ('classic-join-click','classic-join-enter','new','classic-room','legacy-room','classic-queue','legacy-queue'):
        uid='platform-entry-'+str(uuid4())
        api=httpx.Client(base_url=BASE+'/api/mistrealm',headers={'Authorization':'MistrealmUid '+uid})
        api.post('/players/me',json={'name':'沙箱旅人','avatar':None}).raise_for_status()
        prefix='/classic' if mode.startswith('classic') else ''
        body={'request_id':str(uuid4())}
        if prefix:
            d=httpx.get(BASE+'/classic/cards.json').json()['starters'][0]
            r=api.post('/classic/decks',json=d);r.raise_for_status();body['deck_id']=r.json()['id']
        if mode.endswith('room'):
            api.post(prefix+'/rooms',json=body).raise_for_status()
        if mode.endswith('queue'):
            api.post(prefix+'/matchmaking',json={'deck_id':body['deck_id']} if prefix else {}).raise_for_status()
        host=None
        if mode.startswith('classic-join'):
            host=httpx.Client(base_url=BASE+'/api/mistrealm',headers={'Authorization':'MistrealmUid '+'join-host-'+str(uuid4())})
            host.post('/players/me',json={'name':'房主','avatar':None}).raise_for_status()
            host_deck=host.post('/classic/decks',json=d);host_deck.raise_for_status()
            host_room=host.post('/classic/rooms',json={'deck_id':host_deck.json()['id'],'request_id':str(uuid4())})
            host_room.raise_for_status();host_room=host_room.json()
        context=browser.new_context(viewport={'width':390,'height':844} if mode.startswith('classic-join') else {'width':1366,'height':900});page=context.new_page();errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('console',lambda m:print('console:',m.text) if m.type=='error' else None)
        stub=f"<base href='{SURFACE}/platform-assets/'><script>window.dzmm={{user:{{info:async()=>({{id:'{uid}',name:'沙箱旅人'}})}},loading:{{progress(){{}},ready(){{window.sdkReady=true;}},error(c,m){{throw new Error(c+':'+m)}}}}}};</script>"
        document=(ROOT/'index.html').read_text().replace('<head>','<head>'+stub,1)
        parent='<iframe sandbox="allow-scripts" style="border:0;width:100%;height:95vh" srcdoc="'+html.escape(document,quote=True)+'"></iframe>'
        Handler.document=parent
        try:
            page.goto(SURFACE+'/platform-sandbox')
            frame=page.frame_locator('iframe')
            expected={'classic-join-click':'#quick-match','classic-join-enter':'#quick-match','new':'#quick-match','classic-room':'#lock-deck','legacy-room':'#ready','classic-queue':'#cancel-match','legacy-queue':'#match-cancel'}[mode]
            expect(frame.locator(expected)).to_be_visible(timeout=12000)
            assert page.frames[1].url in ('about:srcdoc',''), 'must retain injected SDK instead of navigating iframe'
            assert page.frames[1].evaluate('window.sdkReady===true')
            assert not errors,errors
            page.reload();expect(frame.locator(expected)).to_be_visible(timeout=12000)
            if mode.startswith('classic-join'):
                frame.locator('#room-code-input').fill(host_room['code'])
                if mode.endswith('enter'):frame.locator('#room-code-input').press('Enter')
                else:frame.locator('#join-room').click()
                expect(frame.locator('#room-code')).to_have_text(host_room['code'])
                assert api.get('/players/me').json()['room_id']==host_room['room_id']
                frame.locator('#leave').click();expect(frame.locator('#quick-match')).to_be_visible()
                frame.locator('#room-code-input').fill('123');frame.locator('#join-room').click()
                expect(frame.locator('#join-feedback')).to_contain_text('6位')
                frame.locator('#room-code-input').fill(host_room['code']);frame.locator('#join-room').click()
                expect(frame.locator('#join-feedback')).to_have_text('房间不存在，请检查房间码')
                expect(frame.locator('#room-code-input')).to_have_value(host_room['code'])
                expect(frame.locator('#join-room')).to_be_enabled()
                expect(frame.locator('#join-feedback')).to_be_in_viewport()
                page.screenshot(path=str(ROOT.parent/'platform-join-error-390.png'),full_page=True)
            if mode=='new':
                frame.locator('#channel-toggle').click()
                expect(frame.locator('#channel-input')).to_be_visible()
                frame.locator('#channel-input').fill('沙箱公屏消息')
                frame.locator('#channel-send').click()
                expect(frame.locator('#channel-messages')).to_contain_text('沙箱公屏消息')
                frame.locator('#channel-close').click()
                frame.locator('#edit-deck').click();expect(frame.locator('#builder')).to_be_visible()
                page.screenshot(path=str(ROOT.parent/'platform-sandbox.png'),full_page=True)
        except Exception:
            print(mode,errors,[f.url for f in page.frames])
            print(page.frames[-1].content()[:1200])
            raise
        finally:
            context.close()
            profile=api.get('/players/me').json()
            if profile.get('matchmaking',{}).get('status')=='waiting':
                api.post(prefix+'/matchmaking/cancel',json={'ticket':profile['matchmaking']['ticket']}).raise_for_status()
            api.close()
            if host:host.close()
    browser.close()
server.shutdown()
print('Opaque iframe: SDK retained, new Classic default, v1/v2 rooms and queues restored, reload, sandbox button/Enter joining, inline errors and assets passed')
