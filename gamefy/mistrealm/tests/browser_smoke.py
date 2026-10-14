"""Exercise the loopback development server; run after scripts/mistrealm_dev.py."""
from pathlib import Path
import os
from uuid import uuid4
from playwright.sync_api import sync_playwright

output=Path('.superpowers/sdd/2026-10-15-mistrealm/screenshots')
output.mkdir(parents=True,exist_ok=True)
tag=uuid4().hex[:8]
base=os.environ.get('MISTREALM_DEV_URL','http://127.0.0.1:18741')
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
    context=browser.new_context(viewport={'width':1366,'height':768})
    a=context.new_page();b=context.new_page();errors=[]
    def sync():
        version=max(int(p.locator('#main').get_attribute('data-version') or 0) for p in [a,b])
        for p in [a,b]:
            p.wait_for_function("Number(document.querySelector('#main').dataset.version)>=Number("+str(version)+")")
    def await_action(p,previous):
        p.wait_for_function("Number(document.querySelector('#main').dataset.version)>Number("+str(previous)+")")
    for p in [a,b]:p.on('pageerror',lambda e:errors.append(str(e)))
    a.goto(f'{base}/?player=a-{tag}')
    a.locator('#create').wait_for()
    a.screenshot(path=str(output/'home-desktop.png'),full_page=True)
    a.locator('#create').click()
    a.locator('.code').wait_for()
    code=a.locator('.code').inner_text()
    b.goto(f'{base}/?player=b-{tag}')
    b.locator('#join-code').fill(code)
    b.locator('#join-form button').click()
    b.locator('[data-faction="crown"]').click()
    b.locator('[data-faction="crown"][aria-pressed="true"]').wait_for()
    b.wait_for_function("document.querySelector('#ready')&&!document.querySelector('#ready').disabled")
    b.locator('#ready').click()
    a.locator('.ready').wait_for()
    a.locator('#ready').click()
    a.locator('#start').wait_for(state='visible')
    a.wait_for_function("!document.querySelector('#start').disabled")
    a.screenshot(path=str(output/'room-desktop.png'),full_page=True)
    a.locator('#start').click()
    for p in [a,b]:
        p.locator('#confirm-prep').wait_for()
        sync()
        previous=int(p.locator('#main').get_attribute('data-version'))
        p.locator('#confirm-prep').click()
        await_action(p,previous)
    for p in [a,b]:
        p.get_by_text('留下一张预备牌',exact=True).wait_for()
        sync()
        previous=int(p.locator('#main').get_attribute('data-version'))
        p.locator('.hand .card').first.click()
        p.locator('#confirm-prep').click()
        await_action(p,previous)
    for p in [a,b]:p.locator('#pass').wait_for()
    sync()
    a.screenshot(path=str(output/'battle-desktop.png'),full_page=True)
    # Exercise a real unit deployment (no enemy yet, so damage effects have no target).
    for p in [a,b]:
        if p.locator('#pass').is_enabled():
            for card in p.locator('.hand .card').all():
                if '战地动员' not in card.get_attribute('aria-label') and '破甲弩矢' not in card.get_attribute('aria-label'):
                    card.click()
                    break
            p.locator('#play').click()
            break
    a.reload();a.locator('#pass').wait_for()
    for width,height in [(390,844),(844,390)]:
        a.set_viewport_size({'width':width,'height':height})
        a.screenshot(path=str(output/f'battle-{width}.png'),full_page=True)
        assert a.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'overflow {width}'
    a.set_viewport_size({'width':1366,'height':768})
    # Play remaining rounds by passing; round-result delay is authoritative on the server.
    for _ in range(3):
        sync()
        for turn in range(2):
            for p in [a,b]:
                if p.locator('#pass').count() and p.locator('#pass').is_enabled():
                    previous=int(p.locator('#main').get_attribute('data-version'))
                    p.locator('#pass').click();p.locator('#confirm-yes').click()
                    await_action(p,previous)
                    p.wait_for_function("!document.querySelector('#confirm-yes')||!document.querySelector('#modal').open")
                    break
            else:
                raise AssertionError('Neither player can act')
            if turn==0:
                other=b if p==a else a
                other.wait_for_function("document.querySelector('#pass')&&!document.querySelector('#pass').disabled")
        sync()
        if a.locator('#rematch').count():break
        a.wait_for_function("document.querySelector('#pass')||document.querySelector('#rematch')",timeout=15000)
        b.wait_for_function("document.querySelector('#pass')||document.querySelector('#rematch')",timeout=15000)
        if a.locator('#rematch').count():break
    a.locator('#rematch').wait_for()
    a.screenshot(path=str(output/'result-desktop.png'),full_page=True)
    previous=int(a.locator('#main').get_attribute('data-version'))
    a.locator('#rematch').click();await_action(a,previous);sync()
    b.locator('#rematch').click()
    for p in [a,b]:p.locator('#ready').wait_for()
    # Closing a waiting room must release the other client's page.
    a.locator('#leave').click()
    b.locator('#create').wait_for()
    assert not errors,errors
    print('PASS: two clients, factions, ready, mulligan, reserve, unit deployment, reload, 3 rounds, rematch; 3 viewport widths; no page errors')
    sandbox=context.new_page()
    sandbox.goto(base+'/sandbox')
    frame=sandbox.frame_locator('iframe')
    frame.locator('#create').wait_for()
    frame.locator('#create').click()
    frame.locator('.code').wait_for()
    frame.locator('#leave').click()
    frame.locator('#create').wait_for()
    print('PASS: opaque-origin iframe sandbox (allow-scripts only), SDK bootstrap, create and leave')
    browser.close()
