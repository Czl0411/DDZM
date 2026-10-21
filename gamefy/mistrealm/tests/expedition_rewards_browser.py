"""Reward/replacement UI against a loopback dev DB; seeds only a new test UID."""
import json
import os
from pathlib import Path
from random import Random
import sqlite3
from urllib.parse import urlparse
from uuid import uuid4

from playwright.sync_api import sync_playwright
from dzmm_bot.core import mistrealm_expedition as x

base=os.environ.get('MISTREALM_DEV_URL','http://127.0.0.1:18771')
assert urlparse(base).hostname in ('127.0.0.1','localhost')
db=os.environ['MISTREALM_DEV_DB']
uid='expedition-reward-test-'+uuid4().hex[:8]
output=Path('/tmp/mistrealm-expedition-check');output.mkdir(exist_ok=True)

def saved():
    with sqlite3.connect(db) as conn:
        return json.loads(conn.execute('SELECT state FROM mistrealm_expeditions WHERE player_id=(SELECT id FROM mistrealm_players WHERE platform_uid=?)',(uid,)).fetchone()[0])

def seed(state):
    state['version']+=1
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE mistrealm_expeditions SET state=? WHERE player_id=(SELECT id FROM mistrealm_players WHERE platform_uid=?)',(json.dumps(state),uid))

with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
    page=browser.new_page(viewport={'width':1366,'height':768});errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(base+'/v3/?player='+uid);page.locator('#enter-game').click();page.locator('#tutorial-skip').click()
    page.locator('#expedition-mode').click();page.locator('[data-xp=start]').click()
    page.get_by_role('heading',name='选择起始牌 · 1 / 5').wait_for()
    r=saved();r.update(phase='reward',node=1,completed=1,deck=[],offers=['xb01','xv13','xa09'],reward_next='route',gold=50)
    for _ in range(6):x.add_card(r,'xa01')
    x.add_card(r,'xb13')
    for _ in range(3):x.add_card(r,'xb09')
    old_hero=next(c['id'] for c in r['deck'] if x.CATALOGUE[c['card']]['hero']);seed(r)
    def reopen():
        page.reload();page.locator('#enter-game').click();page.locator('#expedition-mode').click()
    reopen();page.locator('[data-xp=pick][data-index="1"]').click()
    assert page.locator('[data-xp=confirm-choice]').is_disabled()
    assert page.locator('[data-xp=pick-replacement]').count()==1
    page.locator('[data-xp=pick-replacement]').click()
    page.screenshot(path=str(output/'reward-replace-hero.png'))
    page.locator('[data-xp=confirm-choice]').click();page.locator('.xp-route').wait_for()
    r=saved();assert len(r['deck'])==10 and all(c['id']!=old_hero for c in r['deck'])
    assert [c['card'] for c in r['deck'] if x.CATALOGUE[c['card']]['hero']]==['xv13']
    r.update(phase='shop',offers=['xa09','xb02','xb03']);seed(r);reopen()
    page.locator('[data-xp=buy][data-index="0"]').click()
    assert page.locator('[data-xp=pick-replacement]').count()==3
    page.locator('[data-xp=pick-replacement]').first.click()
    page.locator('[data-xp=confirm-choice]').click();page.locator('.xp-working').wait_for(state='hidden')
    r=saved();assert len(r['deck'])==10 and r['gold']==35 and len(r['offers'])==2
    page.locator('[data-xp=leave]').click();page.locator('[data-hand]').first.wait_for()
    assert saved()['battle_step']=='wave'
    assert not errors,errors
    browser.close()
print('Expedition hero replacement, shop replacement and next wave passed')
