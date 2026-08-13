from playwright.sync_api import sync_playwright
import time
EXE = '/Users/skp/Library/Caches/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-x64/chrome-headless-shell'
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE)
    pg = b.new_page(viewport={'width': 420, 'height': 900})
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto('http://127.0.0.1:5099/', wait_until='domcontentloaded', timeout=60000)
    time.sleep(6)
    chips = pg.evaluate("document.querySelectorAll('.qnav-chip').length")
    sticky = pg.evaluate("getComputedStyle(document.getElementById('quickNav')).position")
    active = pg.evaluate("document.querySelector('.qnav-chip.active')?.dataset.target")
    print(f'chips: {chips} | position: {sticky} | initial active: {active}')
    # Click BNF chip → should scroll down to bnfCard
    pg.click('.qnav-chip[data-target="bnfCard"]')
    time.sleep(1.5)
    top = pg.evaluate("document.getElementById('bnfCard').getBoundingClientRect().top")
    print(f'after BNF click: bnfCard top = {top:.0f}px (0-60 = under sticky nav, good)')
    active2 = pg.evaluate("document.querySelector('.qnav-chip.active')?.dataset.target")
    print(f'active chip now: {active2}')
    # Scroll back to top → spy should re-highlight Live
    pg.evaluate("window.scrollTo(0,0)")
    time.sleep(1)
    active3 = pg.evaluate("document.querySelector('.qnav-chip.active')?.dataset.target")
    print(f'after scroll top: active = {active3}')
    print('JS errors:', errs if errs else 'none')
    b.close()
