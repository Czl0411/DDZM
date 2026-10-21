"""Real-browser smoke test against scripts/mistrealm_dev.py."""
import os
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import sync_playwright

base=os.environ.get('MISTREALM_DEV_URL','http://127.0.0.1:18771')
output=Path(os.environ.get('MISTREALM_SCREENSHOTS','/tmp/mistrealm-expedition-check'))
output.mkdir(parents=True,exist_ok=True)
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
    page=browser.new_page(viewport={'width':1366,'height':768});errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(base+'/v3/?player=expedition-test-'+uuid4().hex[:8])
    page.locator('#enter-game').click()
    page.locator('#tutorial-skip').click()
    page.locator('#expedition-mode').click()
    page.locator('[data-xp="start"]').click()
    for i in range(5):
        page.get_by_role('heading',name=f'选择起始牌 · {i+1} / 5').wait_for()
        choices=page.locator('[data-xp="pick"]')
        units=[c for c in choices.all() if c.locator('.xp-card-power').inner_text().isdigit()]
        (units[0] if units else choices.first).click()
        assert page.locator('[data-xp="pick"][aria-pressed="true"]').count()==1
        if i==0:page.screenshot(path=str(output/'draft-desktop.png'))
        page.locator('[data-xp="confirm-choice"]').click()
    page.locator('.xp-route').wait_for()
    assert '旅途商店' not in page.locator('.xp-route').inner_text()
    page.screenshot(path=str(output/'route-desktop.png'))
    page.locator('[data-xp="home"]').first.click()
    page.reload();page.locator('#enter-game').click()
    page.locator('#expedition-mode').click()
    page.locator('.xp-route').wait_for()
    page.locator('.xp-route button').filter(has_text='战斗').first.click()
    page.locator('.xp-board').wait_for()
    assert page.locator('.xp-hand [data-xp="hand"]').count()==5
    played=False
    for c in page.locator('[data-xp="hand"]').all():
        c.click()
        if page.locator('[data-xp="play"]').count():
            page.locator('[data-xp="play"]').first.click();played=True;break
    assert played,'opening draft must allow this smoke scenario to play a card'
    page.locator('.xp-working').wait_for(state='hidden')
    for _ in range(20):
        if not page.locator('[data-xp="target"]').count():break
        page.locator('[data-xp="target"]').first.click()
        page.locator('.xp-working').wait_for(state='hidden')
    assert page.locator('[data-xp="board"]').count()>0
    page.screenshot(path=str(output/'battle-desktop.png'))
    for width,height in [(844,390),(390,844)]:
        page.set_viewport_size({'width':width,'height':height})
        page.screenshot(path=str(output/f'battle-{width}x{height}.png'))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert page.locator('[data-xp="pass"]').is_visible()
        assert page.locator('[data-xp="pass"]').evaluate('el=>{const r=el.getBoundingClientRect(),m=document.querySelector("#main").getBoundingClientRect();return r.bottom<=m.bottom+1&&r.right<=m.right+1&&r.top>=m.top-1&&r.left>=m.left-1}'), 'pass button outside the screen'
    page.set_viewport_size({'width':1366,'height':768})
    page.locator('[data-xp="pass"]').click()
    page.locator('#xp-cancel').click()
    assert page.locator('.xp-board').count()==1
    page.locator('[data-xp="concede"]').click()
    page.locator('#xp-confirm').click()
    page.get_by_role('heading',name='本次远征结束').wait_for()
    assert not errors,errors
    browser.close()
print('Expedition browser smoke passed; screenshots:',output)
