from playwright.sync_api import sync_playwright
import time
EXE = '/Users/skp/Library/Caches/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-x64/chrome-headless-shell'
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE)
    pg = b.new_page(viewport={'width': 420, 'height': 900})
    pg.goto('http://127.0.0.1:5099/', wait_until='domcontentloaded', timeout=60000)
    time.sleep(6)
    pg.screenshot(path='.openclaw/tmp/nav_top.png')
    pg.click('.qnav-chip[data-target="btcCard"]')
    time.sleep(2)
    pg.screenshot(path='.openclaw/tmp/nav_btc.png')
    b.close()
print('shots saved')
