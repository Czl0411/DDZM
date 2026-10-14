"""Two real local browser clients; never points synthetic players at production."""
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect

BASE='http://127.0.0.1:18744/classic/'
OUT=Path('.superpowers/sdd/2026-10-15-mistrealm-classic-120/screenshots')
assert Path('gamefy/mistrealm/publish/classic/index.html').exists(), 'Classic UI must exist'
OUT.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
    context=browser.new_context(viewport={'width':1366,'height':900})
    errors=[];pages=[context.new_page(),context.new_page()]
    for i,page in enumerate(pages):
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.add_init_script('Date.now=()=>0;')
        page.goto(BASE+'?player=classic-browser-'+str(uuid4()))
        expect(page.locator('#quick-match')).to_be_visible()
    a,b=pages
    a.locator('#edit-deck').click()
    expect(a.locator('#builder')).to_be_visible()
    a.locator('#deck-name').fill('赤铜测试军团')
    a.locator('[data-inspect="c001"]').click()
    expect(a.locator('#modal-content')).to_contain_text('同排每张同名单位')
    a.locator('#back-builder').click()
    expect(a.locator('#deck-name')).to_have_value('赤铜测试军团')
    a.locator('#save-deck').click()
    expect(a.locator('#selected-deck')).to_contain_text('赤铜测试军团')
    a.reload();expect(a.locator('#quick-match')).to_be_visible()
    a.locator('#create-room').click()
    expect(a.locator('#room-code')).to_be_visible()
    code=a.locator('#room-code').inner_text().strip()
    b.locator('#room-code-input').fill(code);b.locator('#join-room').click()
    expect(b.locator('[data-player="0"]')).to_contain_text('阵营待揭晓')
    a.locator('#lock-deck').click();b.locator('#lock-deck').click()
    for page in pages:
        expect(page.locator('#confirm-mulligan')).to_be_visible()
        page.locator('#confirm-mulligan').click()
    for page in pages:expect(page.locator('.combat-row')).to_have_count(6)
    a.screenshot(path=str(OUT/'classic-battle-1366.png'),full_page=True)
    for width,height in [(844,390),(390,844)]:
        a.set_viewport_size({'width':width,'height':height})
        assert a.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'horizontal page overflow'
        a.screenshot(path=str(OUT/f'classic-battle-{width}.png'),full_page=True)
    assert not errors,errors
    browser.close()
print('Classic two-player builder, reload, lock, mulligan, 3-row and responsive smoke passed')
