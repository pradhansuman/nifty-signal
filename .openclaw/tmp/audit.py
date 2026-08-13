from playwright.sync_api import sync_playwright
import time, json
EXE = '/Users/skp/Library/Caches/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-x64/chrome-headless-shell'
CHECKS = [
    # (element id, label)
    ('actionText', 'Nifty Action'),
    ('chainRows', 'Nifty Chain'),
    ('expiryRead', 'Nifty Expiry'),
    ('ivRankVal', 'Nifty IV Rank'),
    ('btTrades', 'Nifty Backtest'),
    ('oiBias', 'Nifty OI'),
    ('fiiNetVal', 'FII/DII'),
    ('outlookRead', 'Outlook'),
    ('btcSignal', 'BTC Signal'),
    ('btcLevels', 'BTC Levels'),
    ('bnfSignal', 'BNF Signal'),
    ('bnfChainRows', 'BNF Chain'),
    ('bnfExpiryRead', 'BNF Expiry'),
    ('bnfIvRankVal', 'BNF IV Rank'),
    ('bnfOiBias', 'BNF OI'),
    ('bnfBtTrades', 'BNF Backtest'),
    ('gapSignal', 'Gap&Go'),
    ('weeklyRead', 'Weekly Review'),
]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=EXE)
    pg = b.new_page(viewport={'width': 420, 'height': 1000})
    errors = []
    pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto('http://localhost:5099/', wait_until='domcontentloaded', timeout=60000)
    time.sleep(14)
    print("=== SECTION DATA AUDIT ===")
    for eid, label in CHECKS:
        try:
            el = pg.query_selector(f'#{eid}')
            if not el:
                print(f'❌ {label:16s} element #{eid} MISSING')
                continue
            txt = (el.text_content() or '').strip().replace('\n', ' ')[:60]
            n_rows = pg.evaluate(f"document.querySelectorAll('#{eid} tr').length") if 'Rows' in eid else 0
            if eid.endswith('Rows'):
                print(f'{"✅" if n_rows > 0 else "❌"} {label:16s} rows={n_rows} | first: {txt[:40]}')
            elif txt in ('', '--', 'Loading...', 'Loading…', 'Collecting OI snapshots…'):
                print(f'❌ {label:16s} EMPTY/STALE: "{txt}"')
            else:
                print(f'✅ {label:16s} {txt}')
        except Exception as e:
            print(f'❌ {label:16s} err {str(e)[:50]}')
    print("\n=== JS ERRORS ===")
    print('\n'.join(errors[:10]) if errors else 'none')
    b.close()
