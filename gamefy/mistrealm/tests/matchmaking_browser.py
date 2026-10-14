"""Run against the loopback dev server; exercises real queue API and late responses."""
import asyncio
import os
from pathlib import Path
from uuid import uuid4
from playwright.async_api import async_playwright

BASE=os.environ.get('MISTREALM_DEV_URL','http://127.0.0.1:18743')
OUT=Path('.superpowers/sdd/2026-10-15-mistrealm/screenshots')
OUT.mkdir(parents=True,exist_ok=True)

async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
        context=await browser.new_context(viewport={'width':1366,'height':900})
        a=await context.new_page();b=await context.new_page()
        errors=[]
        for p in [a,b]:p.on('pageerror',lambda e:errors.append(str(e)))
        tag=uuid4().hex[:8]
        await a.goto(f'{BASE}/?player=match-a-{tag}')
        await a.locator('#match-start').click()
        await a.locator('#match-cancel').wait_for()
        await a.screenshot(path=str(OUT/'matchmaking-desktop.png'),full_page=True)
        await a.reload()
        await a.locator('#match-cancel').wait_for()
        await a.set_viewport_size({'width':390,'height':844})
        assert await a.evaluate('document.documentElement.scrollWidth<=innerWidth')
        await a.screenshot(path=str(OUT/'matchmaking-mobile.png'),full_page=True)

        # Hold a successful heartbeat response until after cancellation completed.
        arrived=asyncio.Event();release=asyncio.Event();delivered=asyncio.Event()
        async def late(route):
            response=await route.fetch()
            arrived.set()
            await release.wait()
            await route.fulfill(response=response)
            delivered.set()
        await a.route('**/matchmaking/heartbeat',late)
        await asyncio.wait_for(arrived.wait(),10)
        await a.locator('#match-cancel').click()
        await a.locator('#match-start').wait_for()
        release.set()
        await asyncio.wait_for(delivered.wait(),10)
        await a.unroute('**/matchmaking/heartbeat',late)
        assert await a.locator('#match-cancel').count()==0

        await a.locator('#match-start').click()
        await a.locator('#match-cancel').wait_for()
        await b.goto(f'{BASE}/?player=match-b-{tag}')
        await b.locator('#match-start').click()
        for p in [a,b]:await p.locator('#ready').wait_for()
        assert await a.locator('.code').inner_text()==await b.locator('.code').inner_text()
        assert await a.locator('.player-panel').count()==2
        await a.locator('#ready').click()
        await b.locator('.readiness.ready').wait_for()
        await b.locator('#ready').click()
        await a.wait_for_function("document.querySelector('#start')&&!document.querySelector('#start').disabled")
        await a.locator('#start').click()
        for p in [a,b]:await p.get_by_text('调整你的开局',exact=True).wait_for()
        assert not errors,errors
        print('PASS: queue start, refresh recovery, mobile layout, cancel, late heartbeat ignored, two-player pairing, ready/start')
        await browser.close()

asyncio.run(main())
