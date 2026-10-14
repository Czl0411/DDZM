"""Isolated real API/browser regression for pending choices, large rows and reconnect."""
import random
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright, expect
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uvicorn
from dzmm_bot.core import mistrealm_classic_state as game
from dzmm_bot.core.mistrealm_api import mistrealm_router
from dzmm_bot.core.mistrealm_classic_cards import STARTER_DECKS
from dzmm_bot.core.repository import CoreRepository
from dzmm_bot.core.schema import Base, MistrealmRoomRecord

ROOT=Path(__file__).resolve().parents[1]/'publish'
OUT=Path('.superpowers/sdd/2026-10-15-mistrealm-classic-120/screenshots')
NOW=datetime.now(timezone.utc);STAMP=int(NOW.timestamp()*1000)

with TemporaryDirectory(prefix='classic-browser-e2e-') as directory:
    engine=create_engine(f'sqlite:///{directory}/test.db',connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine);factory=sessionmaker(engine,expire_on_commit=False);repo=CoreRepository(factory)
    for uid in ('choice-a','choice-b'):repo.mistrealm_register(uid,'长昵称'*12 if uid=='choice-a' else '测试对手','https://invalid.example/avatar.png',NOW)
    decks=[repo.mistrealm_save_deck(uid,None,d['name'],d['faction'],d['leader'],d['counts'],NOW) for uid,d in zip(('choice-a','choice-b'),[STARTER_DECKS[0],STARTER_DECKS[3]])]
    room=repo.mistrealm_create('choice-a',uuid4(),NOW,UUID(decks[0]['id']))
    repo.mistrealm_join('choice-b',room['code'],uuid4(),NOW,UUID(decks[1]['id']))
    with factory.begin() as session:
        record=session.get(MistrealmRoomRecord,UUID(room['room_id']));s=record.state
        def act(seat,kind,payload=None):
            global s
            s=game.apply_action(s,seat,kind,payload or {},STAMP,random.Random(3))
        act(0,'lock');act(1,'lock');act(0,'mulligan',{'cards':[]});act(1,'mulligan',{'cards':[]})
        s['turn']=0;s['players'][0]['hand']=[dict(id='medic',card='c105'),dict(id='spy',card='c006')]
        s['players'][0]['discard']=[dict(id='revive',card='c003'),dict(id='hero',card='c110')]
        s['players'][0]['rows'][0]=[dict(id=f'stress-{i}',card='c003') for i in range(50)]
        act(0,'play',{'card':'medic','row':1})
        record.state=s;record.phase=s['phase'];record.match_id=uuid4();record.deadline=NOW.replace(year=NOW.year+1)
    app=FastAPI();app.include_router(mistrealm_router(repo,lambda:NOW))
    @app.get('/classic/',response_class=HTMLResponse)
    def index():
        stub="<script>window.dzmm={user:{info:async()=>({id:'choice-a',name:'长昵称'.repeat(12),avatarUrl:'https://invalid.example/avatar.png'})}};</script>"
        return (ROOT/'classic/index.html').read_text().replace('<script type="module"',stub+'<script type="module"')
    app.mount('/',StaticFiles(directory=ROOT))
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'));thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
            context=browser.new_context(viewport={'width':1366,'height':900});page=context.new_page();errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{port}/classic/')
            expect(page.locator('[data-option]')).to_have_count(1)
            page.reload();expect(page.locator('[data-option]')).to_have_count(1)
            assert page.locator('.self [data-inspect]').count()==51
            page.locator('[data-option]').click();expect(page.locator('[data-option]')).to_have_count(0)
            expect(page.locator('.self [data-inspect]')).to_have_count(52)
            page.locator('[data-inspect="stress-0"]').click()
            expect(page.locator('.power-breakdown')).to_contain_text('当前战力 6')
            page.locator('#close-modal').click()
            # Network loss must recover the same room and never lose the revived card.
            context.set_offline(True);page.locator('#reconnect').click()
            expect(page.locator('#feedback.error')).to_be_visible()
            context.set_offline(False);page.locator('#reconnect').click()
            expect(page.locator('.self [data-inspect]')).to_have_count(52)
            for width,height in [(1366,900),(844,390),(390,844)]:
                page.set_viewport_size({'width':width,'height':height})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                lane=page.locator('.self .row-scroll').first
                page.screenshot(path=str(OUT/f'classic-stress-{width}.png'),full_page=True)
                dimensions=lane.evaluate('(el)=>({scroll:el.scrollWidth,client:el.clientWidth,cards:el.children.length,cardWidth:el.children[0].getBoundingClientRect().width})')
                assert dimensions['scroll']>dimensions['client'],(width,dimensions)
                lane.evaluate('(el)=>el.scrollLeft=el.scrollWidth')
                page.screenshot(path=str(OUT/f'classic-stress-{width}.png'),full_page=True)
            assert not errors,errors
            browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=10);sock.close();engine.dispose()
print('Classic medic reload, 50-unit row, power breakdown, offline recovery and responsive checks passed')
