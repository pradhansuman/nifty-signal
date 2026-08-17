
// JS entry — runs immediately (script at bottom, DOM already ready)
var _jsAlive = true;
document.getElementById('debugInfo').textContent = 'JS loaded ✅';
let cachedSignal = null;
let deferredPrompt = null;

// ── Locale: English ⇄ ଓଡ଼ିଆ (Odia) ──
const L10N = {
  'live-alerts': '🔔 ଲାଇଭ୍ ଆଲର୍ଟ',
  'active-scalp': '⚡ ସକ୍ରିୟ ସ୍କାଲ୍ପ୍ କଲ୍',
  'today-scalp': "📜 ଆଜିର ସ୍କାଲ୍ପ୍ କଲ୍",
  'scalp-pnl': '💰 ସ୍କାଲ୍ପ୍ ଡ୍ରାଏ-ରନ୍ ଲାଭ/କ୍ଷତି (ପେପର)',
  'scalp-gauges': '📊 ସ୍କାଲ୍ପର୍ ଗେଜ୍',
  'bnf-scalper': '🏦 ବ୍ୟାଙ୍କ୍ ନିଫ୍ଟି ସ୍କାଲ୍ପର୍',
  'sx-scalper': '🇮🇳 ସେନସେକ୍ସ ସ୍କାଲ୍ପର୍',
  'btc-scalper': '₿ ବିଟକଏନ୍ ସ୍କାଲ୍ପର୍',
  'nifty-strat': '🧭 ନିଫ୍ଟି ରଣନୀତି ସ୍ଥିତି',
  'options-chain': '📊 ଅପ୍ସନ୍ ଚେନ୍',
  'nifty-200ema': '📈 ନିଫ୍ଟି + ୨୦୦ EMA',
  'oi-buildup': '🧠 OI ବିଲ୍ଡଅପ୍ (ସ୍ମାର୍ଟ୍ ମନି)',
  'gap-go': '⚡ ଗ୍ୟାପ୍ ଆଣ୍ଡ୍ ଗୋ / ଫେଡ୍',
  'expiry-count': '⏳ ଏକ୍ସପାୟରୀ କାଉଣ୍ଟଡାଉନ୍',
  'fii-dii': '🏦 ସ୍ମାର୍ଟ୍ ମନି (FII/DII)',
  'intraday-sig': '📊 ଇଣ୍ଟ୍ରାଡେ ସିଗନାଲ୍',
  'journal': '📒 ଟ୍ରେଡ୍ ଜର୍ଣ୍ଣାଲ୍',
  'algo-scalp': '⚡ ସ୍କାଲ୍ପ୍ ଡ୍ରାଏ-ରନ୍ କଲ୍ (ପେପର)',
  'btc-signal': '🪙 BTC ସିଗନାଲ୍',
  'btc-alerts': '🔔 BTC ଆଲର୍ଟ',
  'btc-strat': '🧭 BTC ରଣନୀତି ସ୍ଥିତି',
  'bnf-signal': '🏦 BNF ସିଗନାଲ୍',
  'bnf-expiry': '⏳ BNF ଏକ୍ସପାୟରୀ କାଉଣ୍ଟଡାଉନ୍',
  'bnf-chain': '📋 BNF ଅପ୍ସନ୍ ଚେନ୍',
  'stock-movers': '🚀 ଷ୍ଟକ୍ ମୁଭର୍ସ',
  'stock-day': '⚡ ଡେ ଟ୍ରେଡ୍ ମୁଭର୍ସ',
  'stock-swing': '📈 ସୁଇଙ୍ଗ୍ କ୍ୟାଣ୍ଡିଡେଟ୍ସ',
  'bnf-oi': '🧠 BNF OI ବିଲ୍ଡଅପ୍',
  'bnf-alerts': '🔔 BNF ଆଲର୍ଟ',
  'bnf-strat': '🧭 ବ୍ୟାଙ୍କ୍ ନିଫ୍ଟି ରଣନୀତି ସ୍ଥିତି',
  'sx-signal': '🇮🇳 ସେନସେକ୍ସ ସିଗନାଲ୍',
  'sx-tech': '📊 ସେନସେକ୍ସ ଟେକ୍ନିକାଲ୍',
  'sx-200ema': '📈 SENSEX + ୨୦୦ EMA',
};
let curLang = 'en';  // all-English UI (Odia toggle removed per user, 2026-08-16)
function applyLang() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const k = el.getAttribute('data-i18n');
    if (curLang === 'or' && L10N[k]) el.innerHTML = L10N[k];
    else if (curLang === 'or' && !L10N[k]) el.innerHTML = el.innerHTML; // keep as-is
    else el.innerHTML = el.getAttribute('data-i18n-en') || el.innerHTML;
  });
  const t = document.getElementById('langToggle');
  if (t) t.textContent = curLang === 'or' ? '🌐 English' : '🌐 ଓଡ଼ିଆ';
  document.documentElement.lang = curLang;
}
function toggleLang() {
  curLang = curLang === 'or' ? 'en' : 'or';
  localStorage.setItem('dash_lang', curLang);
  applyLang();
}
// remember English originals so toggling back restores exactly
(function seedLang() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    if (!el.getAttribute('data-i18n-en')) el.setAttribute('data-i18n-en', el.innerHTML);
  });
  if (curLang === 'or') applyLang();
})();

// ── PWA Install ──
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  document.getElementById('installBanner').style.display = 'block';
});

function installApp() {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(() => {
      document.getElementById('installBanner').style.display = 'none';
      deferredPrompt = null;
    });
  }
}

window.addEventListener('appinstalled', () => {
  document.getElementById('installBanner').style.display = 'none';
});

// ── Clock ──
function updateClock() {
  const now = new Date();
  document.getElementById('clock').textContent =
    now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' });
}
setInterval(updateClock, 1000);
updateClock();

// ── Data Fetch ──
async function fetchSignal() {
  document.getElementById('debugInfo').textContent = 'Fetching signal...';
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 40000); // 40s timeout
  try {
    const resp = await fetch('/api/signal?_=' + Date.now(), { signal: ctrl.signal });
    clearTimeout(timer);
    document.getElementById('debugInfo').textContent = 'Response: ' + resp.status;
    if (!resp.ok) throw new Error('API ' + resp.status);
    cachedSignal = await resp.json();
    window._lastSignal = cachedSignal;
    document.getElementById('debugInfo').textContent = 'Data: ' + JSON.stringify(cachedSignal).slice(0, 150);
    render(cachedSignal);
    refreshStrategies();
    document.getElementById('footerText').textContent =
      'Updated ' + cachedSignal.updated;
    document.getElementById('debugInfo').textContent = 'Rendered ✅';
  } catch (e) {
    clearTimeout(timer);
    document.getElementById('debugInfo').textContent = 'ERROR: ' + e.message;
    document.getElementById('footerText').textContent = 'Connection lost — retrying...';
    if (cachedSignal) render(cachedSignal);
  }
}

function render(s) {
  if (!s || typeof s !== 'object') {
    console.warn('render got invalid data:', s);
    return;
  }
  try {
  const sig = s.signal || 'LOADING';
  const banner = document.getElementById('signalBanner');
  banner.className = 'signal-banner ' + (
    sig === 'BUY_CALLS' || sig === 'BUY_PUTS' ? 'buy' : sig === 'STAND_ASIDE' ? 'exit' : 'wait'
  );
  
  const icons = { BUY_CALLS: '🟢', BUY_PUTS: '🔴', WAIT: '🟡', STAND_ASIDE: '🔴', ERROR: '⚪' };
  document.getElementById('signalIcon').textContent = icons[sig] || '⚪';
  document.getElementById('signalText').textContent = sig.replace('_', ' ');
  document.getElementById('signalSub').textContent = s.reason || '';

  // Price
  document.getElementById('spotPrice').textContent = s.spot ? s.spot.toLocaleString('en-IN') : '--';
  const spotSrc = s.chain_spot ? 'Upstox' : (s.spot ? 'Yahoo' : '');
  const dist = s.distance_pct;
  const changeEl = document.getElementById('spotChange');
  if (dist != null) {
    changeEl.textContent = (dist >= 0 ? '+' : '') + dist + '% vs 200 EMA · ' + spotSrc;
    changeEl.className = 'change ' + (dist >= 0 ? 'up' : 'down');
  }

  // Gauges
  document.getElementById('adxVal').textContent = s.adx || '--';
  document.getElementById('adxSub').textContent = s.adx >= 20 ? 'trending' : (s.adx >= 15 ? 'weak' : 'ranging');
  document.getElementById('rsiVal').textContent = s.rsi_14 || '--';
  const rsi = s.rsi_14;
  document.getElementById('rsiSub').textContent = rsi > 70 ? 'overbought' : (rsi < 30 ? 'oversold' : 'neutral');
  document.getElementById('diPlusVal').textContent = s.di_plus || '--';
  document.getElementById('diMinusVal').textContent = s.di_minus || '--';

  // EMA
  document.getElementById('emaDistance').textContent = (dist >= 0 ? '+' : '') + dist + '%';
  document.getElementById('ema200Label').textContent = '200 EMA: ' + (s.ema_200 ? s.ema_200.toLocaleString('en-IN') : '--');
  document.getElementById('emaLow').textContent = s.ema_200 ? (s.ema_200 * 0.99).toFixed(0) : '--';
  document.getElementById('emaHigh').textContent = s.ema_200 ? (s.ema_200 * 1.01).toFixed(0) : '--';

  // EMA fill bar — map distance_pct (-1% to +1%) to 0-100% bar position
  const emaPos = dist != null ? Math.max(0, Math.min(100, 50 + dist * 50)) : 50;
  document.getElementById('emaMarker').style.left = emaPos + '%';
  const fill = document.getElementById('emaFill');
  fill.style.width = emaPos + '%';
  fill.className = 'ema-fill ' + (dist >= 0 ? 'bull' : 'bear');

  // Regime — compute from data
  const isTrending = s.adx >= 20;
  const isBullish = s.di_plus > s.di_minus;
  const bias = isTrending ? (isBullish ? 'defined_risk' : 'buy_directional') : 'sell_premium';
  const regimeLabel = isTrending ? (isBullish ? 'Low Vol Trending (Bullish)' : 'Trending (Bearish)') : 'Low Vol Ranging';
  const regimeBadge = document.getElementById('regimeBadge');
  regimeBadge.textContent = regimeLabel;
  regimeBadge.className = 'regime-badge ' + bias;
  
  document.getElementById('regimeDesc').textContent = isTrending
    ? 'Directional trend active — use debit spreads or directional plays'
    : 'Range-bound — premium selling ideal';
  document.getElementById('regimeTransition').textContent = 'ADX: ' + (s.adx || '--') + ' | DI+: ' + (s.di_plus || '--') + ' | DI-: ' + (s.di_minus || '--');

  // Action
  const actionCard = document.getElementById('actionCard');
  const actionTextEl = document.getElementById('actionText');
  if (s.action) {
    actionCard.classList.remove('hidden');
    actionTextEl.textContent = s.action;
  } else if (sig === 'BUY_CALLS') {
    actionCard.classList.remove('hidden');
    actionTextEl.textContent = s.reason || 'Buy calls at 200 EMA bounce';
  } else if (sig === 'WAIT') {
    actionCard.classList.remove('hidden');
    actionTextEl.textContent = 'No entry yet. Waiting for 200 EMA bounce with trend confirmation. ' + (s.reason || '');
  } else {
    actionCard.classList.add('hidden');
  }

  // ── Contrarian PCR Signal ──
  const contrarianCard = document.getElementById('contrarianCard');
  const contrarianText = document.getElementById('contrarianText');
  const cs = s.contrarian_signal;
  if (cs === 'SELL_CALLS' || cs === 'SELL_PUTS') {
    contrarianCard.classList.remove('hidden');
    contrarianCard.style.background = '#1a1030';
    const dir = cs === 'SELL_CALLS' ? '🔴 SELL CALLS' : '🟢 SELL PUTS';
    contrarianText.textContent = dir + ' — ' + (s.contrarian_reason || '');
    contrarianText.style.color = '#c4b5fd';
  } else if (cs === 'NEUTRAL') {
    contrarianCard.classList.remove('hidden');
    contrarianCard.style.background = '#141b22';
    contrarianText.textContent = '⚪ No contrarian edge — ' + (s.contrarian_reason || 'PCR balanced');
    contrarianText.style.color = 'var(--text-dim)';
  } else {
    contrarianCard.classList.add('hidden');
  }

  // ── ORB Scalp (fetched separately, only meaningful 9:30-10:15 AM) ──
  fetchORB();

  // Levels card (only for BUY) — green pill = TARGET, red pill = STOP
  if (sig === 'BUY_CALLS' || sig === 'BUY_PUTS') {
    document.getElementById('levelsCard').classList.remove('hidden');
    const tgt = s.expected_move_1sd
      ? '🎯 1σ Target: ±' + s.expected_move_1sd.toLocaleString('en-IN') + ' pts'
      : '🎯 Target: --';
    document.getElementById('targetLevel').textContent = tgt;
    document.getElementById('stopLevel').textContent = s.stop_level
      ? '🛑 Stop: ' + s.stop_level.toLocaleString('en-IN')
      : '🛑 Stop: --';
  } else {
    document.getElementById('levelsCard').classList.add('hidden');
  }

  // ── Expiry-aware trade card ──
  const tradeCard = document.getElementById('tradeCard');
  if (s.selected_expiry) {
    tradeCard.classList.remove('hidden');
    document.getElementById('tradeExpiry').textContent = s.selected_expiry + ' (' + (s.expiry_type || '') + ')';
    document.getElementById('tradeDTE').textContent = (s.dte || '--') + ' DTE';
    
    if (s.signal === 'BUY_CALLS' && s.recommended_trade) {
      document.getElementById('tradeType').textContent = '📈 Buy ' + s.entry_strike + ' CE';
      let tradeInfo = '';
      if (s.entry_premium != null) {
        tradeInfo = 'Premium: ₹' + s.entry_premium + ' (₹' + Math.round(s.entry_premium * 65).toLocaleString('en-IN') + '/lot)';
      }
      document.getElementById('entryLevel').textContent = tradeInfo || ('Entry: ' + (s.entry_strike || '--'));
      document.getElementById('targetLevelPill').textContent = s.expected_move_1sd
        ? '🎯 1σ: +' + s.expected_move_1sd.toLocaleString('en-IN') + ' pts'
        : '🎯 Target: --';
      document.getElementById('stopLevelPill').textContent = s.stop_level ? '🛑 Index Stop: ' + s.stop_level : '';
    } else if (s.signal === 'BUY_PUTS' && s.recommended_trade) {
      document.getElementById('tradeType').textContent = '📉 Buy ' + s.entry_strike + ' PE';
      let tradeInfo = '';
      if (s.entry_premium != null) {
        tradeInfo = 'Premium: ₹' + s.entry_premium + ' (₹' + Math.round(s.entry_premium * 65).toLocaleString('en-IN') + '/lot)';
      }
      document.getElementById('entryLevel').textContent = tradeInfo || ('Entry: ' + (s.entry_strike || '--'));
      document.getElementById('targetLevelPill').textContent = s.expected_move_1sd
        ? '🎯 1σ: −' + s.expected_move_1sd.toLocaleString('en-IN') + ' pts'
        : '🎯 Target: --';
      document.getElementById('stopLevelPill').textContent = s.stop_level ? '🛑 Index Stop: ' + s.stop_level : '';
    } else {
      document.getElementById('tradeType').textContent = s.recommended_trade || 'No active trade';
      document.getElementById('entryLevel').textContent = '';
      document.getElementById('targetLevelPill').textContent = '';
      document.getElementById('stopLevelPill').textContent = '';
    }
  } else {
    tradeCard.classList.add('hidden');
  }

  // ── BTST card ──
  const btstCard = document.getElementById('btstCard');
  if (s.btst_expiry && s.signal === 'BUY_CALLS') {
    btstCard.classList.remove('hidden');
    document.getElementById('btstExpiry').textContent = s.btst_expiry + ' (weekly)';
    document.getElementById('btstDTE').textContent = (s.btst_dte || '--') + ' DTE';
    let btstLabel = 'Buy ' + (s.btst_strike || '--') + ' CE (ATM)';
    if (s.btst_premium != null) btstLabel += ' @ ₹' + s.btst_premium;
    document.getElementById('btstTrade').textContent = btstLabel;
    document.getElementById('btstEntry').textContent = 'Entry: ' + (s.btst_strike || '--');
    document.getElementById('btstTarget').textContent = 'Target: ' + (s.btst_target || '--');
    document.getElementById('btstStop').textContent = '🛑 Index Stop: ' + (s.btst_stop || '--');
  } else {
    btstCard.classList.add('hidden');
  }

  // ── Options Chain (Upstox) ──
  const optionsCard = document.getElementById('optionsCard');
  if (s.option_chain_source) {
    optionsCard.classList.remove('hidden');
    document.getElementById('optionsSource').textContent = s.option_chain_source;
    
    // PCR color
    const pcr = s.oi_pcr;
    const wpcr = s.weekly_pcr;
    const pcrEl = document.getElementById('pcrOIVAL');
    const pcrLabel = s.weekly_pcr != null ? (wpcr.toFixed(2) + ' / ' + (pcr||0).toFixed(2)) : ((pcr||0).toFixed(2));
    pcrEl.textContent = pcrLabel;
    pcrEl.style.fontSize = wpcr != null ? '20px' : '24px';
    if (pcr != null) {
      pcrEl.style.color = pcr > 1.2 ? 'var(--red)' : pcr < 0.8 ? 'var(--green)' : 'var(--yellow)';
    }
    // Show weekly/monthly breakdown
    const pcrLabelEl = document.getElementById('pcrOIVAL').nextElementSibling;
    if (pcrLabelEl && s.weekly_pcr != null) {
      pcrLabelEl.innerHTML = 'PCR (W/M)';
    }
    
    // ATM IV
    const ivEl = document.getElementById('atmIVVal');
    const iv = s.atm_iv;
    ivEl.textContent = iv != null ? iv.toFixed(1) + '%' : '--';
    if (iv != null) {
      ivEl.style.color = iv < 12 ? 'var(--green)' : iv > 20 ? 'var(--red)' : 'var(--yellow)';
    }
    
    // Max Pain
    document.getElementById('maxPainVal').textContent = s.max_pain_estimate 
      ? Number(s.max_pain_estimate).toLocaleString('en-IN') : '--';
    
    // Mean IV
    const mivEl = document.getElementById('ivMeanVal');
    const miv = s.iv_mean;
    mivEl.textContent = miv != null ? miv.toFixed(1) + '%' : '--';
    
    // Call/Put OI totals
    const coi = s.total_call_oi;
    const poi = s.total_put_oi;
    document.getElementById('callOIVal').textContent = coi ? (coi / 1e6).toFixed(1) + 'M' : '--';
    document.getElementById('putOIVal').textContent = poi ? (poi / 1e6).toFixed(1) + 'M' : '--';
    
    // OI Changes
    const cc = s.call_oi_change;
    const pc = s.put_oi_change;
    const ccEl = document.getElementById('callChgVal');
    const pcEl = document.getElementById('putChgVal');
    ccEl.textContent = cc != null ? ((cc >= 0 ? '+' : '') + (cc / 1e6).toFixed(1) + 'M') : '--';
    pcEl.textContent = pc != null ? ((pc >= 0 ? '+' : '') + (pc / 1e6).toFixed(1) + 'M') : '--';
    ccEl.style.color = (cc != null && cc > 0) ? 'var(--green)' : 'var(--red)';
    pcEl.style.color = (pc != null && pc > 0) ? 'var(--green)' : 'var(--red)';
  } else {
    optionsCard.classList.add('hidden');
  }

  // ── Trailing Stop (card removed from dashboard — null-safe) ──
  const fixedStopEl = document.getElementById('fixedStop');
  if (fixedStopEl) {
    const fixedStop = s.stop_level;
    const trailStopVal = s.trail_stop;
    fixedStopEl.textContent = fixedStop ? fixedStop.toLocaleString('en-IN') : '--';
    const trailStopEl = document.getElementById('trailStop');
    if (trailStopEl) trailStopEl.textContent = trailStopVal ? trailStopVal.toLocaleString('en-IN') : '--';
    if (trailStopVal && fixedStop) {
      const gap = trailStopVal - fixedStop;
      const gapEl = document.getElementById('stopGap');
      if (gapEl) {
        gapEl.textContent = (gap > 0 ? '+' : '') + gap.toFixed(0) + ' pts';
        gapEl.style.color = gap > 0 ? 'var(--green)' : 'var(--red)';
        trailStopEl.style.color = gap > 50 ? 'var(--green)' : 'var(--yellow)';
      }
    }
  }
  } catch(e) { console.error('Render error:', e); }
}

// ── Position Sizing ──
async function calcPositionSize() {
  const capital = document.getElementById('capitalInput').value;
  const riskPct = document.getElementById('riskInput').value;
  const el = document.getElementById('sizingResult');
  el.style.display = 'block';
  el.innerHTML = '<span style="color:var(--text-dim)">Calculating...</span>';
  try {
    const resp = await fetch('/api/position-size?capital=' + capital + '&risk_pct=' + riskPct);
    const d = await resp.json();
    if (d.error) { el.innerHTML = '<span style="color:var(--red)">' + d.error + '</span>'; return; }
    const riskColor = d.lots > 0 ? 'var(--green)' : 'var(--red)';
    el.innerHTML =
      '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
        '<div style="flex:1;min-width:80px"><span style="font-size:22px;font-weight:800;color:' + riskColor + '">' + d.lots + '</span><br><span style="font-size:11px;color:var(--text-dim)">Lots</span></div>' +
        '<div style="flex:1;min-width:80px"><span style="font-size:14px;font-weight:700">₹' + (d.capital_required || 0).toLocaleString('en-IN') + '</span><br><span style="font-size:11px;color:var(--text-dim)">Capital Needed</span></div>' +
        '<div style="flex:1;min-width:80px"><span style="font-size:14px;font-weight:700">₹' + (d.capital_at_risk || 0).toLocaleString('en-IN') + '</span><br><span style="font-size:11px;color:var(--text-dim)">At Risk (' + (d.capital_at_risk_pct || 0) + '%)</span></div>' +
      '</div>' +
      '<div style="font-size:11px;color:var(--text-dim);margin-top:6px;line-height:1.5">' +
        'Entry: ₹' + (d.entry_premium || 0) + ' × 65 = ₹' + (d.capital_per_lot || 0).toLocaleString('en-IN') + '/lot | ' +
        'Stop: ' + (d.stop_distance_pts || '--') + ' pts → option moves ~' + (d.option_move_pts || '--') + ' pts (δ=' + (d.delta || 0.5).toFixed(3) + ', ' + (d.delta_source || '') + ')<br>' +
        'Risk/lot: ₹' + (d.option_risk_per_lot || 0).toLocaleString('en-IN') +
        (d.vix_multiplier && d.vix_multiplier < 1 ? ' ⚠️ VIX:' + (d.vix_level || 0) + ' → sizing ×' + d.vix_multiplier : '') +
        (d.gap_warning ? '<br><span style="color:var(--red)">⚠️ ' + d.gap_warning + '</span>' : '') +
        (d.lots_by_risk !== d.lots ? ' (capped by capital)' : '') +
      '</div>';
  } catch (e) {
    el.innerHTML = '<span style="color:var(--red)">Failed to calculate</span>';
  }
}

// ── Trade Journal ──
function toggleJournal() {
  const form = document.getElementById('journalForm');
  form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

async function logTrade() {
  const direction = document.getElementById('jDirection').value;
  const lots = parseInt(document.getElementById('jLots').value) || 0;
  const entryPx = parseFloat(document.getElementById('jEntryPx').value) || 0;
  const exitPx = parseFloat(document.getElementById('jExitPx').value) || null;
  const strike = document.getElementById('jStrike').value;
  const expiry = document.getElementById('jExpiry').value;
  if (!lots || !entryPx) return alert('Enter Lots and Entry Price');
  
  const trade = { direction, lots, entry_price: entryPx, exit_price: exitPx || undefined, strike, expiry };
  try {
    const resp = await fetch('/api/journal', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(trade) });
    if (resp.ok) {
      document.getElementById('journalForm').style.display = 'none';
      ['jLots','jEntryPx','jExitPx','jStrike','jExpiry'].forEach(id => document.getElementById(id).value = '');
      fetchJournal();
    }
  } catch(e) { alert('Failed to save'); }
}

async function fetchJournal() {
  try {
    const resp = await fetch('/api/journal');
    const data = await resp.json();
    const stats = data.stats || {};
    document.getElementById('jTotalTrades').textContent = stats.total_trades || 0;
    document.getElementById('jWinRate').textContent = stats.win_rate != null ? stats.win_rate + '%' : '--';
    const pnl = stats.total_pnl;
    const pnlEl = document.getElementById('jTotalPnl');
    pnlEl.textContent = pnl != null ? '₹' + Math.abs(pnl).toLocaleString('en-IN') : '--';
    pnlEl.style.color = pnl > 0 ? 'var(--green)' : pnl < 0 ? 'var(--red)' : 'inherit';
    document.getElementById('jRR').textContent = stats.risk_reward != null ? '1:' + stats.risk_reward : '--';
    
    // Show last 5 trades
    const trades = (data.trades || []).slice(-5).reverse();
    const el = document.getElementById('recentTrades');
    if (!trades.length) { el.innerHTML = '<div style="font-size:12px;color:var(--text-dim)">No trades yet</div>'; return; }
    el.innerHTML = trades.map(t => {
      const pnlClass = (t.pnl || 0) >= 0 ? 'color:var(--green)' : 'color:var(--red)';
      return '<div style="display:flex;justify-content:space-between;font-size:11px;padding:4px 0;border-bottom:1px solid var(--border)">' +
        '<span>' + t.date + ' <b>' + (t.direction||'--').toUpperCase() + '</b> ' + (t.strike||'') + '</span>' +
        '<span style="' + pnlClass + '">' + (t.pnl != null ? '₹' + t.pnl.toLocaleString('en-IN') : 'Open') + '</span>' +
      '</div>';
    }).join('');
  } catch(e) {}
}

async function fetchAlerts() {
  try {
    const resp = await fetch('/api/alerts');
    const alerts = await resp.json();
    const el = document.getElementById('alertsList');
    const badge = document.getElementById('alertBadge');
    
    if (!alerts || !alerts.length) {
      el.innerHTML = '<div style="color:var(--text-dim);padding:12px;text-align:center">Waiting for market signals...</div>';
      badge.style.display = 'none';
      return;
    }
    
    const critical = alerts.filter(a => a.level === 'critical').length;
    if (critical > 0) {
      badge.style.display = 'inline-block';
      badge.textContent = critical;
      badge.style.background = 'var(--red)';
    } else {
      badge.style.display = 'none';
    }
    
    el.innerHTML = alerts.reverse().map(a => {
    const bg = a.level === 'critical' ? '#ff174418' : a.level === 'warning' ? '#ffc10718' : 'transparent';
      const border = a.level === 'critical' ? '#ff1744' : a.level === 'warning' ? '#ffc107' : 'var(--border)';
      const anim = a.level === 'critical' ? 'animation:alertGlow 2s infinite' : '';
      return '<div style="padding:8px 10px;margin-bottom:8px;background:' + bg + ';border-left:4px solid ' + border + ';border-radius:6px;' + anim + '">' +
        '<div style="font-weight:800;font-size:10px;color:var(--text-dim);margin-bottom:2px">' + a.time + '</div>' +
        '<div style="font-weight:800;font-size:13px;margin-bottom:3px">' + a.title + '</div>' +
        '<div style="font-size:11px;color:var(--text-dim);line-height:1.4">' + a.body + '</div>' +
      '</div>';
    }).join('');
  } catch(e) {}
}

async function fetchTunnelURL() {
  try {
    const resp = await fetch('/api/tunnel');
    const data = await resp.json();
    if (data.url) {
      document.getElementById('tunnelBadge').textContent = '🔗 ' + data.url;
    }
  } catch(e) {}
}

async function fetchORB() {
  const card = document.getElementById('orbCard');
  const text = document.getElementById('orbText');
  const details = document.getElementById('orbDetails');
  
  try {
    const resp = await fetch('/api/orb');
    const d = await resp.json();
    
    if (d.signal === 'ORB_BUY') {
      card.style.background = '#0a2816'; card.style.borderColor = '#00c85355';
      text.textContent = '🟢 BUY — ' + (d.breakout_direction || '') + ' breakout';
      text.style.color = '#80ffb4';
      details.textContent = (d.reason || '') +
        ' | Entry: ' + (d.entry_strike || '--') + ' CE | Target: ' + (d.target_strike || '--') + ' | Stop: ' + (d.stop_strike || '--');
    } else if (d.signal === 'ORB_SELL') {
      card.style.background = '#280a0a'; card.style.borderColor = '#ff174455';
      text.textContent = '🔴 SELL — ' + (d.breakout_direction || '') + ' breakdown';
      text.style.color = '#ff8080';
      details.textContent = (d.reason || '') +
        ' | Entry: ' + (d.entry_strike || '--') + ' PE | Target: ' + (d.target_strike || '--') + ' | Stop: ' + (d.stop_strike || '--');
    } else {
      card.style.background = '#0a1628'; card.style.borderColor = '#448aff55';
      text.textContent = '⏳ ' + (d.reason || 'Waiting for breakout...');
      text.style.color = '#80b4ff';
      if (d.opening_high) {
        details.textContent = 'Range: ' + d.opening_low + ' – ' + d.opening_high +
          ' (' + (d.range_pts || '--') + ' pts) | Spot: ' + (d.spot || '--');
      } else {
        details.textContent = '';
      }
    }
  } catch(e) {
    text.textContent = 'ORB not available';
    text.style.color = 'var(--text-dim)';
  }
}

async function fetchIntraday() {
  try {
    const resp = await fetch('/api/intraday');
    const d = await resp.json();
    
    // VWAP
    const v = d.vwap || {};
    const vsEl = document.getElementById('vwapSignal');
    const vdEl = document.getElementById('vwapDetail');
    if (v.signal === 'VWAP_BUY') {
      vsEl.textContent = '🟢 BUY (mean reversion)';
      vsEl.style.color = 'var(--green)';
    } else if (v.signal === 'VWAP_SELL') {
      vsEl.textContent = '🔴 SELL (mean reversion)';
      vsEl.style.color = 'var(--red)';
    } else {
      vsEl.textContent = v.signal || '--';
      vsEl.style.color = 'var(--yellow)';
    }
    vdEl.textContent = v.reason || 'Outside hours';
    
    // EMA
    const e = d.ema || {};
    const esEl = document.getElementById('emaSignal');
    const edEl = document.getElementById('emaDetail');
    if (e.signal === 'EMA_BUY') {
      esEl.textContent = '🟢 GOLDEN CROSS';
      esEl.style.color = 'var(--green)';
    } else if (e.signal === 'EMA_SELL') {
      esEl.textContent = '🔴 DEATH CROSS';
      esEl.style.color = 'var(--red)';
    } else if (e.signal === 'EMA_LONG') {
      esEl.textContent = '🟢 In Uptrend';
      esEl.style.color = 'var(--green)';
    } else if (e.signal === 'EMA_SHORT') {
      esEl.textContent = '🔴 In Downtrend';
      esEl.style.color = 'var(--red)';
    } else {
      esEl.textContent = e.signal || '--';
      esEl.style.color = 'var(--yellow)';
    }
    edEl.textContent = e.reason || 'Outside hours';
    
  } catch(e) {
    document.getElementById('vwapSignal').textContent = 'N/A';
    document.getElementById('emaSignal').textContent = 'N/A';
  }
}

async function fetchAlgoStatus() {
  try {
    const resp = await fetch('/api/algo/status');
    const d = await resp.json();
    
    // Mode badge
    const modeEl = document.getElementById('algoMode');
    if (d.live_mode) {
      modeEl.textContent = '🔴 LIVE';
      modeEl.style.color = 'var(--red)';
      document.getElementById('algoWarning').style.display = 'none';
    } else {
      modeEl.textContent = '🧪 DRY RUN';
      modeEl.style.color = 'var(--green)';
    }
    
    // Limits
    const state = d.state || {};
    document.getElementById('algoLimits').textContent =
      `Max: ${d.max_lots_trade} lot/trade | ${d.max_lots_day} lot/day | Loss limit: ₹${d.daily_limit?.toLocaleString('en-IN')} | ` +
      `Paper P&L: ₹${(state.pnl_today||0).toLocaleString('en-IN')} today / ₹${(state.total_pnl||0).toLocaleString('en-IN')} total`;
    
    // Strategy toggles
    const strats = d.enabled_strategies || {};
    document.getElementById('algoStrategies').innerHTML = Object.entries(strats).map(([k,v]) =>
      `<span style="padding:2px 8px;border-radius:6px;font-size:10px;background:${v?'#00c85322':'#ff174422'};color:${v?'var(--green)':'var(--red)'};border:1px solid ${v?'#00c85344':'#ff174444'}">${k} ${v?'✅':'⏸'}</span>`
    ).join('');
    
    // Active positions
    const positions = d.active_positions || [];
    const closedTrades = d.closed_trades || [];
    let html = '';
    
    if (positions.length) {
      html += '<div style="font-size:10px;font-weight:700;color:var(--text-dim);margin-top:4px">Open Positions:</div>';
      html += positions.map(p => {
        const ot = p.option_type || (p.direction === 'SELL' ? 'PE' : 'CE');
        const exp = p.expiry ? (' ' + String(p.expiry).slice(0, 6)) : '';
        return `<div style="font-size:10px;padding:2px 0;border-bottom:1px solid var(--border)">
          #${p.id} ${p.direction} <b>${p.strike} ${ot}${exp}</b> ${p.lots}L @ ₹${p.entry_premium} (${p.signal_type})
        </div>`;
      }).join('');
    }
    
    if (closedTrades.length) {
      html += '<div style="font-size:10px;font-weight:700;color:var(--text-dim);margin-top:4px">Closed P&L:</div>';
      html += closedTrades.slice(-5).reverse().map(t => {
        const ot = t.option_type || (t.direction === 'SELL' ? 'PE' : 'CE');
        const exp = t.expiry ? (' ' + String(t.expiry).slice(0, 6)) : '';
        const pnlClass = (t.pnl||0) >= 0 ? 'var(--green)' : 'var(--red)';
        return `<div style="font-size:10px;padding:2px 0;border-bottom:1px solid var(--border)">
          #${t.id} ${t.direction} ${t.strike} ${ot}${exp}: <span style="color:${pnlClass}">₹${(t.pnl||0).toLocaleString('en-IN')} (${t.pnl_pct||0}%)</span>
        </div>`;
      }).join('');
    }
    
    document.getElementById('algoOrders').innerHTML = html || '<div style="font-size:10px;color:var(--text-dim)">No positions</div>';
    // ⚡ Scalp dry-run calls merged into the Algo card
    try {
      const sc = (d.scalp_calls || []).slice(0, 15);
      const scEl = document.getElementById('algoScalpCalls');
      const pnlEl = document.getElementById('algoScalpPnl');
      if (scEl) {
        if (pnlEl && d.scalp_pnl && d.scalp_pnl.resolved) {
          const p = d.scalp_pnl;
          pnlEl.textContent = p.resolved + ' trades · ' + p.wins + 'W/' + (p.resolved - p.wins) + 'L · ' +
            (p.net_rs ? '₹' + Number(p.net_rs).toLocaleString('en-IN') : p.net_pts + ' pts');
        }
        scEl.innerHTML = sc.map(c => {
          const st = c.status || 'ACTIVE';
          const chip = st === 'TARGET_HIT' ? 'var(--green)' : st === 'STOP_HIT' || st === 'EXPIRED' ? 'var(--red)' : 'var(--accent)';
          const pnl = c.pnl_pts != null ? ((c.pnl_pts >= 0 ? '+' : '') + c.pnl_pts + ' pts' + (c.pnl_rs ? ' · ₹' + Number(c.pnl_rs).toLocaleString('en-IN') : '')) : '';
          const hot = c.perfect ? ' 🔥' : '';
          return `<div style="font-size:10px;padding:2px 0;border-bottom:1px solid var(--border)">
            <span style="color:${chip}">${st}</span>${hot} ${c.time} ${String(c.asset).toUpperCase()} ${c.option || 'SPOT'} @ ${c.entry}${pnl ? ' → <b>' + pnl + '</b>' : ''}
          </div>`;
        }).join('') || '<div style="font-size:10px;color:var(--text-dim)">No scalp calls yet</div>';
      }
    } catch (e) {}
  } catch(e) {}
}

// ── FII/DII Smart Money ──
async function fetchFiiDii() {
  try {
    const resp = await fetch('/api/fiidii?_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const d = await resp.json();
    renderFiiDii(d);
  } catch(e) {}
}

function renderFiiDii(d) {
  const card = document.getElementById('fiiDiiCard');
  if (!card) return;
  const el = id => document.getElementById(id);
  const fii = d.fii_net, dii = d.dii_net;

  el('fiiDate').textContent = d.date || '';

  const fiiEl = el('fiiNetVal');
  fiiEl.textContent = fii != null ? (fii > 0 ? '+' : '') + fii.toLocaleString('en-IN', {maximumFractionDigits: 0}) : '--';
  fiiEl.style.color = fii > 0 ? 'var(--green)' : fii < 0 ? 'var(--red)' : 'var(--text-dim)';

  const diiEl = el('diiNetVal');
  diiEl.textContent = dii != null ? (dii > 0 ? '+' : '') + dii.toLocaleString('en-IN', {maximumFractionDigits: 0}) : '--';
  diiEl.style.color = dii > 0 ? 'var(--green)' : dii < 0 ? 'var(--red)' : 'var(--text-dim)';

  const score = d.sentiment_score;
  const scoreEl = el('smartMoneyScore');
  if (score != null) {
    scoreEl.textContent = score + '/100';
    scoreEl.style.color = score >= 60 ? 'var(--green)' : score <= 40 ? 'var(--red)' : 'var(--yellow)';
  } else {
    scoreEl.textContent = '--';
  }

  const readEl = el('smartMoneyRead');
  readEl.textContent = d.read || 'No data';
  readEl.style.color = 'var(--text-dim)';
}

// ── Tomorrow Outlook ──
async function fetchOutlook() {
  try {
    const resp = await fetch('/api/outlook?_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    renderOutlook(await resp.json());
  } catch(e) {}
}

function renderOutlook(d) {
  const card = document.getElementById('outlookCard');
  if (!card) return;
  const el = id => document.getElementById(id);
  const now = new Date();
  el('outlookTime').textContent = now.toLocaleTimeString('en-IN', {hour:'2-digit', minute:'2-digit'});

  const giftEl = el('giftNiftyVal');
  giftEl.textContent = d.gift_nifty != null ? Number(d.gift_nifty).toLocaleString('en-IN') : '--';

  const gapEl = el('gapVal');
  if (d.expected_gap != null) {
    const g = d.expected_gap;
    gapEl.textContent = (g > 0 ? '+' : '') + g.toLocaleString('en-IN', {maximumFractionDigits: 0});
    gapEl.style.color = g > 15 ? 'var(--green)' : g < -15 ? 'var(--red)' : 'var(--yellow)';
    gapEl.style.fontSize = '16px';
  } else {
    gapEl.textContent = '--';
  }

  const usEl = el('usReadVal');
  const us = d.us || {};
  const parts = Object.entries(us).map(([k,v]) => k.split(' ')[0] + ' ' + (v.change_pct >= 0 ? '+' : '') + v.change_pct + '%');
  usEl.textContent = parts.join(' · ') || '--';
  usEl.style.fontSize = '11px';
  usEl.style.color = Object.values(us).some(u => u.change_pct < 0) ? 'var(--red)' : 'var(--green)';

  const readEl = el('outlookRead');
  readEl.textContent = d.read || 'No data';
  readEl.style.color = 'var(--text-dim)';
}

// ── Bitcoin ──
async function fetchBtc() {
  try {
    const resp = await fetch('/api/btc?_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const d = await resp.json();
    window._lastBtc = d;
    renderBtc(d);
  } catch(e) {}
  // Also fetch 15m signal
  try {
    const resp = await fetch('/api/btc?interval=15m&_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const d = await resp.json();
    window._lastBtc15 = d;
    const s15 = document.getElementById('btcSignal15');
    if (s15) {
      const sig = d.signal || 'WAIT';
      s15.textContent = sig === 'BUY_LONG' ? '🟢 LONG' : sig === 'BUY_SHORT' ? '🔴 SHORT' : sig === 'WAIT' ? '⏳ WAIT' : 'ERR';
      s15.style.color = sig === 'BUY_LONG' ? 'var(--green)' : sig === 'BUY_SHORT' ? 'var(--red)' : 'var(--yellow)';
    }
  } catch(e) {}
}

function renderBtc(d) {
  const el = id => document.getElementById(id);
  if (!el('btcSpot')) return;
  refreshBtcStrategies();
  const spot = d.spot;
  el('btcSpot').textContent = spot != null ? '$' + Number(spot).toLocaleString('en-US', {maximumFractionDigits: 0}) : '--';
  el('btcSpot').style.color = spot != null && d.ema_distance_pct < 0 ? 'var(--red)' : 'var(--green)';

  const sigEl = el('btcSignal');
  const sig = d.signal || 'WAIT';
  sigEl.textContent = sig === 'BUY_LONG' ? '🟢 LONG' : sig === 'BUY_SHORT' ? '🔴 SHORT' : sig === 'EXIT_LONGS' ? '⚠️ EXIT L' : sig === 'EXIT_SHORTS' ? '⚠️ EXIT S' : sig === 'ERROR' ? 'ERR' : '⏳ WAIT';
  sigEl.style.color = sig === 'BUY_LONG' ? 'var(--green)' : sig === 'BUY_SHORT' ? 'var(--red)' : sig === 'WAIT' ? 'var(--yellow)' : 'var(--text-dim)';

  const chg = d['24h_change'];
  const chgEl = el('btc24h');
  chgEl.textContent = chg != null ? (chg > 0 ? '+' : '') + chg + '%' : '--';
  chgEl.style.color = chg > 0 ? 'var(--green)' : chg < 0 ? 'var(--red)' : 'var(--text-dim)';

  el('btcReason').textContent = d.reason || '';
  el('btcEma').textContent = d.ema_200 != null ? '$' + Number(d.ema_200).toLocaleString('en-US', {maximumFractionDigits: 0}) : '--';
  el('btcAdx').textContent = d.adx != null ? d.adx : '--';
  el('btcRsi').textContent = d.rsi != null ? d.rsi : '--';
  el('btcDi').textContent = d.di_plus != null && d.di_minus != null ? d.di_plus + ' / ' + d.di_minus : '--';

  const lv = el('btcLevels');
  lv.innerHTML = '';
  if (d.stop_level && d.target_level) {
    lv.innerHTML = '<div style="display:flex;gap:12px;flex-wrap:wrap">' +
      '<span style="color:var(--red);font-weight:700">🛑 Stop: $' + Number(d.stop_level).toLocaleString('en-US', {maximumFractionDigits: 0}) + '</span>' +
      '<span style="color:var(--green);font-weight:700">🎯 Target: $' + Number(d.target_level).toLocaleString('en-US', {maximumFractionDigits: 0}) + '</span>' +
      '</div>';
  } else {
    lv.innerHTML = '<span style="color:var(--yellow);font-weight:600">⏳ HOLD — no trade</span> <span style="color:var(--text-dim)">' + (d.reason || 'waiting for 200 EMA bounce setup') + '</span>';
  }
  // BTC recommendation banner
  const rec = document.getElementById('btcRec');
  if (rec && d.recommendation) {
    rec.style.display = 'block';
    rec.textContent = '💡 ' + d.recommendation;
    rec.style.background = d.action === 'BUY' ? 'rgba(0,200,83,0.12)' : d.action === 'SELL' ? 'rgba(255,23,68,0.12)' : 'rgba(255,193,7,0.08)';
    rec.style.color = d.action === 'BUY' ? 'var(--green)' : d.action === 'SELL' ? 'var(--red)' : 'var(--yellow)';
  }
  // BTC alerts
  const al = document.getElementById('btcAlertsList');
  if (al && d.alerts && d.alerts.length) {
    al.innerHTML = d.alerts.slice().reverse().map(a => {
      const color = a.signal === 'BUY_LONG' ? 'var(--green)' : a.signal === 'BUY_SHORT' ? 'var(--red)' : 'var(--yellow)';
      return '<div style="padding:4px 6px;border-left:3px solid ' + color + ';background:rgba(124,58,237,0.05);margin:3px 0;border-radius:4px">' +
        '<b style="color:' + color + '">' + a.signal + '</b> <span style="color:var(--text-dim)">' + a.date + ' ' + a.time + ' <span style="opacity:0.6">(was ' + a.prev + ')</span></span><br>' +
        '<span style="color:var(--text-dim)">' + a.reason + '</span></div>';
    }).join('');
  } else if (al) {
    al.innerHTML = '<div style="color:var(--text-dim);padding:8px;text-align:center">No signal changes yet today</div>';
  }
}

// ── IV Rank ──
async function fetchIvRank(prefix) {
  prefix = prefix || '';
  try {
    const resp = await fetch((prefix ? '/api/bnf/ivrank' : '/api/ivrank') + '?_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    renderIvRank(await resp.json(), prefix);
  } catch(e) {}
}

function renderIvRank(d, prefix) {
  prefix = prefix || '';
  const P = s => prefix ? prefix + s.charAt(0).toUpperCase() + s.slice(1) : s;
  const el = id => document.getElementById(P(id));
  if (!el('ivRankVal')) return;
  el('ivRange').textContent = (d.low_52w != null ? d.low_52w : '--') + ' – ' + (d.high_52w != null ? d.high_52w : '--');

  const rank = d.iv_rank;
  const rankEl = el('ivRankVal');
  rankEl.textContent = rank != null ? rank + '%' : '--';
  rankEl.style.color = rank <= 20 ? 'var(--green)' : rank <= 40 ? 'var(--blue)' : rank <= 60 ? 'var(--yellow)' : rank <= 80 ? 'var(--red)' : '#ff6b7a';

  const pct = d.iv_percentile;
  const pctEl = el('ivPctVal');
  pctEl.textContent = pct != null ? pct + '%' : '--';
  pctEl.style.color = pct <= 25 ? 'var(--green)' : pct >= 75 ? 'var(--red)' : 'var(--yellow)';

  el('ivCurrentVal').textContent = d.current_vix != null ? d.current_vix : '--';
  const atmIv = document.getElementById(P('atmIvVal'));
  if (atmIv) atmIv.textContent = d.atm_iv != null ? d.atm_iv : '--';

  const readEl = el('ivRead');
  readEl.textContent = d.read || '';
  readEl.style.color = rank != null && rank <= 40 ? 'var(--green)' : rank != null && rank >= 70 ? 'var(--red)' : 'var(--text-dim)';
}

// ── Backtest ──
async function fetchBacktest(prefix) {
  prefix = prefix || '';
  try {
    const resp = await fetch((prefix ? '/api/bnf/backtest' : '/api/backtest') + '?_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    renderBacktest(await resp.json(), prefix);
  } catch(e) {}
}

function renderBacktest(d, prefix) {
  prefix = prefix || '';
  const P = s => prefix ? prefix + s.charAt(0).toUpperCase() + s.slice(1) : s;
  const el = id => document.getElementById(P(id));
  if (!el('btTrades')) return;
  if (d.error) { el('btRead').textContent = d.error; return; }
  el('btPeriod').textContent = d.period ? d.period.slice(0, 10) + ' → ' + d.period.slice(-10) : '';
  el('btTrades').textContent = d.trades;
  const wr = el('btWinRate');
  wr.textContent = d.win_rate + '%';
  wr.style.color = d.win_rate >= 55 ? 'var(--green)' : d.win_rate >= 45 ? 'var(--yellow)' : 'var(--red)';
  const ex = el('btExpectancy');
  ex.textContent = (d.expectancy > 0 ? '+' : '') + d.expectancy + '%';
  ex.style.color = d.expectancy > 0 ? 'var(--green)' : 'var(--red)';
  const pf = el('btPF');
  pf.textContent = d.profit_factor || '--';
  pf.style.color = (d.profit_factor || 0) >= 1.3 ? 'var(--green)' : (d.profit_factor || 0) >= 1 ? 'var(--yellow)' : 'var(--red)';
  const rd = el('btRead');
  rd.textContent = d.read || '';
  rd.style.color = 'var(--text-dim)';

  const det = el('btDetails');
  det.innerHTML =
    'Avg win: ' + d.avg_win + '% · Avg loss: ' + d.avg_loss + '% · Max DD: ' + d.max_drawdown_pct + '%<br>' +
    'Total return (2y): ' + d.total_return_pct + '% · Best: ' + d.best_trade + '% · Worst: ' + d.worst_trade + '%<br>' +
    'Longs: ' + d.long_trades + ' · Shorts: ' + d.short_trades + ' · Avg hold: ' + d.avg_bars + ' bars<br>' +
    'Exits: 🎯target ' + (d.exit_reasons.target||0) + ' · 🛑stop ' + (d.exit_reasons.stop||0) + ' · ⏳time ' + (d.exit_reasons.time||0) + ' · ADX ' + (d.exit_reasons.adx_death||0) + '<br>' +
    'Rules: 1h bars, 48-bar time stop, 1% target, 0.5% EMA stop, costs 0.1%/round trip';
  if (d.variants) {
    const vLines = Object.entries(d.variants).map(([k,v]) =>
      (k === d.variant ? '<b>✓ ' : '') + (k === 'base' ? 'Base' : k === 'time' ? 'Morning-only' : 'Morning+VIX<18') + ': ' + v.trades + ' tr, ' + v.win_rate + '% WR, ' + v.expectancy + '%/tr' + (k === d.variant ? '</b>' : ''));
    det.innerHTML += '<br><br><b>Variants tested:</b><br>' + vLines.join('<br>');
  }
}

// ── Option Chain Table ──
async function fetchChain() {
  try {
    const resp = await fetch('/api/chain?_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    renderChain(await resp.json());
  } catch(e) {}
}

async function fetchBnfChain() {
  try {
    const resp = await fetch('/api/bnf/chain?_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    renderChain(await resp.json(), 'bnf');
  } catch(e) {}
}

function fmtOID(n) {
  if (n == null) return '--';
  if (n >= 1e6) return (n/1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n/1e3).toFixed(0) + 'K';
  return n;
}

function renderChain(d, prefix) {
  prefix = prefix || '';
  const P = s => prefix ? prefix + s.charAt(0).toUpperCase() + s.slice(1) : s;
  const id = s => document.getElementById(P(s));
  if (!id('chainRows')) return;
  if (d.error) {
    id('chainMeta').textContent = d.error;
    return;
  }
  id('chainMeta').textContent = (d.expiry || '') + ' · Spot ' + (d.chain_spot != null ? Number(d.chain_spot).toLocaleString('en-IN', {maximumFractionDigits: 0}) : '--');
  const walls = id('chainWalls');
  walls.innerHTML = d.call_wall ? '🧱 Call wall: <b style="color:var(--red)">' + d.call_wall + '</b> (OI ' + fmtOID(d.call_wall_oi) + ') · ' : '' +
    (d.put_wall ? 'Put wall: <b style="color:var(--green)">' + d.put_wall + '</b> (OI ' + fmtOID(d.put_wall_oi) + ')' : '');

  // Prominent spot price — Upstox chain spot, fall back to main signal spot
  const spotBig = id('chainSpotBig');
  let sp = d.chain_spot;
  if (sp == null && typeof cachedSignal !== 'undefined' && cachedSignal && cachedSignal.spot) sp = cachedSignal.spot;
  let spotTxt = sp != null ? Number(sp).toLocaleString('en-IN', {maximumFractionDigits: 2}) : '--';
  // GIFT Nifty in brackets with trend arrow
  if (d.gift_nifty != null) {
    const gift = Number(d.gift_nifty).toLocaleString('en-IN', {maximumFractionDigits: 0});
    const g = d.gift_gap_vs_spot;
    const up = d.gift_trend === 'gap_up' || (g != null && g > 15);
    const dn = d.gift_trend === 'gap_down' || (g != null && g < -15);
    const arrow = up ? '▲' : dn ? '▼' : '▶';
    const color = up ? 'var(--green)' : dn ? 'var(--red)' : 'var(--yellow)';
    spotTxt += ' <span style="font-size:14px;color:var(--text-dim)">(GIFT </span><span style="font-size:14px;color:' + color + ';font-weight:700">' + arrow + ' ' + gift + '</span><span style="font-size:14px;color:var(--text-dim)">)</span>';
    if (g != null && Math.abs(g) >= 15) {
      spotTxt += ' <span style="font-size:11px;color:' + color + ';font-weight:700">' + (g > 0 ? '+' : '') + Number(g).toLocaleString('en-IN', {maximumFractionDigits: 0}) + 'pts</span>';
    }
  }
  spotBig.innerHTML = spotTxt;

  const tb = id('chainRows');
  tb.innerHTML = '';
  const rows = d.rows || [];
  // Rank top-3 volume for CE and PE
  const rankCE = rows.filter(r => r.ce_vol != null).sort((a,b) => (b.ce_vol||0) - (a.ce_vol||0)).slice(0,3);
  const rankPE = rows.filter(r => r.pe_vol != null).sort((a,b) => (b.pe_vol||0) - (a.pe_vol||0)).slice(0,3);
  const rankCEMap = {}, rankPEMap = {};
  rankCE.forEach((r,i) => rankCEMap[r.strike] = i + 1);
  rankPE.forEach((r,i) => rankPEMap[r.strike] = i + 1);

  rows.forEach(r => {
    const isATM = d.atm && r.strike === d.atm;
    const isCW = d.call_wall && r.strike === d.call_wall;
    const isPW = d.put_wall && r.strike === d.put_wall;
    const tr = document.createElement('tr');
    tr.style.borderTop = '1px solid var(--border)';
    if (isATM) tr.style.background = 'rgba(124,58,237,0.12)';
    tr.innerHTML =
      '<td style="padding:3px 4px;text-align:left;font-weight:' + (isATM ? '800' : '600') + '">' + r.strike + (isATM ? ' ◀' : '') + '</td>' +
      '<td style="padding:3px 4px;text-align:right;color:var(--green)">' + (r.ce_ltp != null ? r.ce_ltp.toLocaleString('en-IN', {maximumFractionDigits: 1}) : '--') + '</td>' +
      '<td style="padding:3px 4px;text-align:right;color:' + (isCW ? '#ff6b7a;font-weight:800' : 'var(--text-dim)') + '">' + fmtOID(r.ce_oi) + '</td>' +
      '<td style="padding:3px 4px;text-align:right;color:var(--text-dim)">' + fmtOID(r.ce_vol) + (rankCEMap[r.strike] ? ' <b style="color:var(--yellow)">' + rankCEMap[r.strike] + '</b>' : '') + '</td>' +
      '<td style="padding:3px 4px;text-align:right;color:var(--text-dim)">' + (r.ce_iv != null ? r.ce_iv.toFixed(1) : '--') + '</td>' +
      '<td style="padding:3px 4px;text-align:right;color:var(--red)">' + (r.pe_ltp != null ? r.pe_ltp.toLocaleString('en-IN', {maximumFractionDigits: 1}) : '--') + '</td>' +
      '<td style="padding:3px 4px;text-align:right;color:' + (isPW ? '#00e676;font-weight:800' : 'var(--text-dim)') + '">' + fmtOID(r.pe_oi) + '</td>' +
      '<td style="padding:3px 4px;text-align:right;color:var(--text-dim)">' + fmtOID(r.pe_vol) + (rankPEMap[r.strike] ? ' <b style="color:var(--yellow)">' + rankPEMap[r.strike] + '</b>' : '') + '</td>';
    tb.appendChild(tr);
  });
}

// ── Nifty Chart (canvas) ──
async function fetchChart(interval) {
  try {
    const q = interval ? '&interval=' + interval : '';
    const resp = await fetch('/api/chart?_=' + Date.now() + q);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const d = await resp.json();
    drawChart(d, 'niftyChart', 'chartSpotTag', {line: '#448aff', ema: '#7c3aed'});
    const lbl = document.getElementById('niftyTfLabel');
    if (lbl && d.interval) lbl.textContent = d.interval + ' bars';
  } catch(e) {}
}

async function fetchBtcChart(interval) {
  try {
    const q = interval ? '&interval=' + interval : '';
    const resp = await fetch('/api/chart?asset=btc&_=' + Date.now() + q);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const d = await resp.json();
    drawChart(d, 'btcChart', 'btcSpotTag', {line: '#f7931a', ema: '#7c3aed'});
    const lbl = document.getElementById('btcTfLabel');
    if (lbl && d.interval) lbl.textContent = d.interval + ' bars';
  } catch(e) {}
}

async function fetchBnfChart(interval) {
  try {
    const q = interval ? '&interval=' + interval : '';
    const resp = await fetch('/api/chart?asset=banknifty&_=' + Date.now() + q);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const d = await resp.json();
    drawChart(d, 'bnfChart', 'bnfSpotTag', {line: '#00bcd4', ema: '#7c3aed'});
    const lbl = document.getElementById('bnfTfLabel');
    if (lbl && d.interval) lbl.textContent = d.interval + ' bars';
  } catch(e) {}
}

async function fetchSensex() {
  try {
    const resp = await fetch('/api/sensex?_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const d = await resp.json();
    window._lastSensex = d;
    renderSensex(d);
  } catch(e) {}
}

function renderSensex(d) {
  const el = id => document.getElementById(id);
  if (!el('sensexSpot')) return;
  refreshSensexStrategies(d);
  const spot = d.spot;
  el('sensexSpot').textContent = spot != null ? Number(spot).toLocaleString('en-IN', {maximumFractionDigits: 0}) : '--';
  el('sensexSpot').style.color = d.ema_distance_pct != null && d.ema_distance_pct < 0 ? 'var(--red)' : 'var(--green)';

  const sigEl = el('sensexSignal');
  const sig = d.signal || 'WAIT';
  sigEl.textContent = sig === 'BUY_LONG' ? '🟢 LONG' : sig === 'BUY_SHORT' ? '🔴 SHORT' : sig === 'EXIT_LONGS' ? '⚠️ EXIT L' : sig === 'EXIT_SHORTS' ? '⚠️ EXIT S' : sig === 'ERROR' ? 'ERR' : '⏳ WAIT';
  sigEl.style.color = sig === 'BUY_LONG' ? 'var(--green)' : sig === 'BUY_SHORT' ? 'var(--red)' : sig === 'WAIT' ? 'var(--yellow)' : 'var(--text-dim)';

  const chg = d.change_pct;
  const chgEl = el('sensexChg');
  chgEl.textContent = chg != null ? (chg > 0 ? '+' : '') + chg + '%' : '--';
  chgEl.style.color = chg > 0 ? 'var(--green)' : chg < 0 ? 'var(--red)' : 'var(--text-dim)';

  const dist = d.ema_distance_pct;
  const distEl = el('sensexDist');
  distEl.textContent = dist != null ? (dist > 0 ? '+' : '') + dist + '%' : '--';
  distEl.style.color = dist > 0 ? 'var(--green)' : dist < 0 ? 'var(--red)' : 'var(--yellow)';

  el('sensexReason').textContent = d.reason || '';
  el('sensexEma').textContent = d.ema_200 != null ? Number(d.ema_200).toLocaleString('en-IN', {maximumFractionDigits: 0}) : '--';
  el('sensexAdx').textContent = d.adx != null ? d.adx : '--';
  el('sensexRsi').textContent = d.rsi != null ? d.rsi : '--';
  el('sensexDi').textContent = d.di_plus != null && d.di_minus != null ? d.di_plus + ' / ' + d.di_minus : '--';

  const lv = el('sensexLevels');
  lv.innerHTML = '';
  if (d.stop_level && d.target_level) {
    lv.innerHTML = '<div style="display:flex;gap:12px;flex-wrap:wrap">' +
      '<span style="color:var(--red);font-weight:700">🛑 Stop: ' + Number(d.stop_level).toLocaleString('en-IN', {maximumFractionDigits: 0}) + '</span>' +
      '<span style="color:var(--green);font-weight:700">🎯 Target: ' + Number(d.target_level).toLocaleString('en-IN', {maximumFractionDigits: 0}) + '</span></div>';
  } else {
    lv.innerHTML = '<span style="color:var(--yellow);font-weight:600">⏳ HOLD — no trade</span> <span style="color:var(--text-dim)">' + (d.reason || 'waiting for 200 EMA bounce setup') + '</span>';
  }

  const rec = document.getElementById('sensexRec');
  if (rec && d.recommendation) {
    rec.style.display = 'block';
    rec.textContent = '💡 ' + d.recommendation;
    rec.style.background = d.action === 'BUY' ? 'rgba(0,200,83,0.12)' : d.action === 'SELL' ? 'rgba(255,23,68,0.12)' : 'rgba(255,193,7,0.08)';
    rec.style.color = d.action === 'BUY' ? 'var(--green)' : d.action === 'SELL' ? 'var(--red)' : 'var(--yellow)';
  }

  const al = document.getElementById('sensexAlertsList');
  if (al && d.alerts && d.alerts.length) {
    al.innerHTML = d.alerts.slice().reverse().map(a => {
      const color = a.signal === 'BUY_LONG' ? 'var(--green)' : a.signal === 'BUY_SHORT' ? 'var(--red)' : 'var(--yellow)';
      return '<div style="padding:4px 6px;border-left:3px solid ' + color + ';background:rgba(124,58,237,0.05);margin:3px 0;border-radius:4px">' +
        '<b style="color:' + color + '">' + a.signal + '</b> <span style="color:var(--text-dim)">' + a.date + ' ' + a.time + ' <span style="opacity:0.6">(was ' + a.prev + ')</span></span><br>' +
        '<span style="color:var(--text-dim)">' + a.reason + '</span></div>';
    }).join('');
  } else if (al) {
    al.innerHTML = '<div style="color:var(--text-dim);padding:8px;text-align:center">No signal changes yet today</div>';
  }
}

async function fetchSensexChart(interval) {
  try {
    const q = interval ? '&interval=' + interval : '';
    const resp = await fetch('/api/chart?asset=sensex&_=' + Date.now() + q);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const d = await resp.json();
    drawChart(d, 'sensexChart', 'sensexSpotTag', {line: '#f59e0b', ema: '#7c3aed'});
    const lbl = document.getElementById('sensexTfLabel');
    if (lbl && d.interval) lbl.textContent = d.interval + ' bars';
  } catch(e) {}
}

// Timeframe toggles
function initTimeframeToggles() {
  const bind = (id, fn) => {
    const wrap = document.getElementById(id);
    if (!wrap) return;
    wrap.querySelectorAll('button').forEach(b => {
      b.addEventListener('click', () => {
        wrap.querySelectorAll('button').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        fn(b.dataset.tf);
      });
    });
  };
  bind('tfNifty', tf => fetchChart(tf));
  bind('tfBtc', tf => fetchBtcChart(tf));
  bind('tfBnf', tf => fetchBnfChart(tf));
  bind('tfSensex', tf => fetchSensexChart(tf));
}

// Quick-nav section jumper + scroll-spy
function initQuickNav() {
  const nav = document.getElementById('quickNav');
  if (!nav) return;
  // Pair chips with sections, sorted by DOM position (chip order ≠ DOM order)
  const pairs = Array.from(nav.querySelectorAll('.qnav-chip'))
    .map(c => ({ chip: c, sec: document.getElementById(c.dataset.target) }))
    .filter(p => p.sec)
    .sort((a, b) => (a.sec.compareDocumentPosition(b.sec) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1);
  // Click → smooth scroll
  pairs.forEach(p => {
    p.chip.addEventListener('click', () => {
      p.sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
      pairs.forEach(x => x.chip.classList.remove('active'));
      p.chip.classList.add('active');
    });
  });
  // Scroll-spy: highlight the section currently in view
  let ticking = false;
  const onScroll = () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      ticking = false;
      const navH = nav.offsetHeight + 4;
      let cur = pairs[0].chip;
      for (let i = 0; i < pairs.length; i++) {
        if (pairs[i].sec.getBoundingClientRect().top <= navH + 40) cur = pairs[i].chip;
      }
      pairs.forEach(x => x.chip.classList.toggle('active', x.chip === cur));
      // auto-scroll chip into view if off-screen
      if (nav.scrollLeft !== undefined) {
        const navRect = nav.getBoundingClientRect();
        const chipRect = cur.getBoundingClientRect();
        if (chipRect.left < navRect.left) nav.scrollLeft += chipRect.left - navRect.left - 8;
        else if (chipRect.right > navRect.right) nav.scrollLeft += chipRect.right - navRect.right + 8;
      }
    });
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}

// Chart state registry for resize redraws
const chartState = {};

function fitCanvas(cv) {
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth || 460;
  const h = cv.clientHeight || 180;
  cv.width = Math.round(w * dpr);
  cv.height = Math.round(h * dpr);
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}

function drawChart(d, canvasId, spotTagId, colors) {
  const cv = document.getElementById(canvasId);
  if (!cv || d.error) return;
  chartState[canvasId] = { d: d, spotTagId: spotTagId, colors: colors };
  const colorLine = (colors && colors.line) || '#448aff';
  const colorEma = (colors && colors.ema) || '#7c3aed';
  const colorEma20 = (colors && colors.ema20) || '#f59e0b';
  const { ctx, w: W, h: H } = fitCanvas(cv);
  const PAD = 8;
  const VOL_H = 24;  // volume band height at bottom
  const PRICE_H = H - VOL_H - 10;
  ctx.clearRect(0, 0, W, H);
  const close = d.close || [];
  if (close.length < 5) return;
  const ema = d.ema200 || [];
  const ema20 = d.ema20 || [];
  const highs = d.high || close, lows = d.low || close;
  const vol = d.volume || [];
  const all = highs.concat(lows, ema.filter(v => v != null), ema20.filter(v => v != null));
  const min = Math.min.apply(null, all), max = Math.max.apply(null, all);
  const rng = (max - min) || 1;
  const X = i => PAD + (i / (close.length - 1)) * (W - 2 * PAD);
  const Y = v => PAD + PRICE_H - ((v - min) / rng) * (PRICE_H - 2 * PAD);
  const bw = Math.max(2.5, ((W - 2 * PAD) / close.length) * 0.7);

  // Grid + value labels (right-aligned on left edge, crisp small font)
  ctx.strokeStyle = 'rgba(30,41,59,0.55)';
  ctx.lineWidth = 1;
  ctx.font = '10px ui-monospace, Menlo, monospace';
  for (let g = 0; g <= 4; g++) {
    const gy = PAD + (g / 4) * (PRICE_H - 2 * PAD);
    ctx.beginPath(); ctx.moveTo(PAD, gy); ctx.lineTo(W - PAD, gy); ctx.stroke();
    const val = max - (g / 4) * rng;
    const txt = val >= 1000 ? (val / 1000).toFixed(1) + 'k' : val.toFixed(0);
    const tw = ctx.measureText(txt).width;
    // Label chip with dark bg so it never collides with candles
    ctx.fillStyle = 'rgba(13,20,32,0.75)';
    ctx.fillRect(1, gy - 8, tw + 4, 11);
    ctx.fillStyle = 'rgba(148,163,184,0.95)';
    ctx.fillText(txt, 3, gy + 1);
  }

  // Volume bars (bottom band)
  const vmax = Math.max.apply(null, vol.concat([1]));
  for (let i = 0; i < close.length; i++) {
    const v = vol[i] || 0;
    const up = i === 0 || close[i] >= (d.open && d.open[i] != null ? d.open[i] : close[i - 1]);
    ctx.fillStyle = up ? 'rgba(0,200,83,0.4)' : 'rgba(255,23,68,0.4)';
    const bh = Math.max(1, (v / vmax) * VOL_H);
    ctx.fillRect(X(i) - bw / 2, H - PAD - bh + 4, bw, bh);
  }
  // Volume band separator
  ctx.strokeStyle = 'rgba(30,41,59,0.8)';
  ctx.beginPath(); ctx.moveTo(PAD, PRICE_H + PAD + 2); ctx.lineTo(W - PAD, PRICE_H + PAD + 2); ctx.stroke();

  // Candles
  for (let i = 0; i < close.length; i++) {
    const o = d.open && d.open[i] != null ? d.open[i] : close[i];
    const h = highs[i], l = lows[i], c = close[i];
    const up = c >= o;
    ctx.strokeStyle = up ? '#00c853' : '#ff1744';
    ctx.fillStyle = up ? '#00c853' : '#ff1744';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(X(i), Y(h)); ctx.lineTo(X(i), Y(l)); ctx.stroke();
    const yo = Y(o), yc = Y(c);
    const bodyTop = Math.min(yo, yc), bodyH = Math.max(1.5, Math.abs(yo - yc));
    ctx.fillRect(X(i) - bw / 2, bodyTop, bw, bodyH);
  }

  // 20 EMA line (fast momentum — entry timing)
  ctx.strokeStyle = colorEma20; ctx.lineWidth = 1.5;
  ctx.beginPath(); let started = false;
  ema20.forEach((v, i) => {
    if (v == null) return;
    if (!started) { ctx.moveTo(X(i), Y(v)); started = true; }
    else ctx.lineTo(X(i), Y(v));
  });
  ctx.stroke();

  // 200 EMA line (trend — direction)
  ctx.strokeStyle = colorEma; ctx.lineWidth = 1.8;
  ctx.beginPath(); started = false;
  ema.forEach((v, i) => {
    if (v == null) return;
    if (!started) { ctx.moveTo(X(i), Y(v)); started = true; }
    else ctx.lineTo(X(i), Y(v));
  });
  ctx.stroke();

  // ── EMA guide lines + latest-value tags (bounce zone at a glance) ──
  const lastVal = arr => { for (let i = arr.length - 1; i >= 0; i--) if (arr[i] != null) return arr[i]; return null; };
  const lastEma20 = lastVal(ema20), lastEma = lastVal(ema);
  const fmt = v => Number(v).toLocaleString('en-IN', {maximumFractionDigits: 0});
  const drawGuide = (val, color, label, below) => {
    if (val == null) return;
    const gy = Y(val);
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = color; ctx.globalAlpha = 0.55; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(PAD, gy); ctx.lineTo(W - PAD, gy); ctx.stroke();
    ctx.restore();
    // Value chip at right edge, clamped inside canvas; `below` places it under the line
    const txt = label + ' ' + fmt(val);
    ctx.font = 'bold 10px ui-monospace, Menlo, monospace';
    const tw = ctx.measureText(txt).width + 8;
    let cy = below ? gy + 2 : gy - 15;
    if (cy < 2) cy = 2;
    if (cy > H - 16) cy = H - 16;
    ctx.fillStyle = 'rgba(13,20,32,0.85)';
    ctx.fillRect(W - PAD - tw, cy, tw, 14);
    ctx.fillStyle = color; ctx.globalAlpha = 1;
    ctx.fillText(txt, W - PAD - tw + 4, cy + 10);
  };
  drawGuide(lastEma20, colorEma20, '20E', false);
  drawGuide(lastEma, colorEma, '200E', true);

  // Spot tag
  if (spotTagId) {
    const tag = document.getElementById(spotTagId);
    if (tag && d.spot) tag.textContent = 'Spot: ' + Number(d.spot).toLocaleString('en-IN', {maximumFractionDigits: 0});
  }
}

// Redraw on resize (debounced) — keeps charts crisp on rotate/orientation change
let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    Object.keys(chartState).forEach(id => {
      const s = chartState[id];
      drawChart(s.d, id, s.spotTagId, s.colors);
    });
  }, 200);
});

// ── Nifty Scalper (5m momentum + live option call) ──
async function fetchScalper() {
  const banner = document.getElementById('scalperBanner');
  if (!banner) return;
  try {
    const resp = await fetch('/api/scalper?_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const d = await resp.json();
    const upd = document.getElementById('scalperUpdated');
    if (upd) upd.textContent = d.timestamp || '';
    const scoreEl = document.getElementById('scalperScore');
    if (scoreEl) scoreEl.textContent = 'Score: ' + (d.score >= 0 ? '+' : '') + d.score + ' (need ±' + (d.score_min != null ? d.score_min : 3) + ') · ' + (d.bias || 'FLAT');
    if (d.signal === 'SCALP_LONG' && d.call && !d.call.blocked) {
      banner.innerHTML = '<span class="live-badge live-long">🟢 LIVE</span>🟢 LONG — ' + d.call.option + ' @ ₹' + d.call.entry;
      banner.style.background = '#0a2816'; banner.style.color = '#80ffb4';
      document.getElementById('scalperCall').textContent = 'Buy at ask ₹' + (d.call.buy_ask != null ? d.call.buy_ask : d.call.entry) + ' · Expiry ' + d.call.expiry + ' · Lot ₹' + Number(d.call.lot_cost).toLocaleString('en-IN') + ' · Spread ' + d.call.spread_pct + '% · ⏳ expires ' + (d.call.expires_at || '--') + ' (target/stop net of spread)';
      document.getElementById('scalperEntry').textContent = 'Entry ₹' + d.call.entry;
      document.getElementById('scalperTarget').textContent = '🎯 ₹' + d.call.target;
      document.getElementById('scalperStop').textContent = '🛑 ₹' + d.call.stop;
      document.getElementById('scalperLevels').style.display = 'flex';
    } else if (d.signal === 'SCALP_SHORT' && d.call && !d.call.blocked) {
      banner.innerHTML = '<span class="live-badge live-short">🔴 LIVE</span>🔴 SHORT — ' + d.call.option + ' @ ₹' + d.call.entry;
      banner.style.background = '#280a0a'; banner.style.color = '#ff8080';
      document.getElementById('scalperCall').textContent = 'Buy at ask ₹' + (d.call.buy_ask != null ? d.call.buy_ask : d.call.entry) + ' · Expiry ' + d.call.expiry + ' · Lot ₹' + Number(d.call.lot_cost).toLocaleString('en-IN') + ' · Spread ' + d.call.spread_pct + '% · ⏳ expires ' + (d.call.expires_at || '--') + ' (target/stop net of spread)';
      document.getElementById('scalperEntry').textContent = 'Entry ₹' + d.call.entry;
      document.getElementById('scalperTarget').textContent = '🎯 ₹' + d.call.target;
      document.getElementById('scalperStop').textContent = '🛑 ₹' + d.call.stop;
      document.getElementById('scalperLevels').style.display = 'flex';
    } else if (d.call && d.call.blocked) {
      banner.textContent = '🚫 ' + (d.signal === 'SCALP_LONG' ? 'LONG' : 'SHORT') + ' blocked — ' + (d.call.block_reason || 'spread too wide');
      banner.style.background = '#2a1a0a'; banner.style.color = '#ffab00';
      document.getElementById('scalperCall').textContent = '';
      document.getElementById('scalperLevels').style.display = 'none';
    } else {
      const win = d.window === 'BLOCKED' ? ' ⏸ ' + (d.window_reason || '') : '';
      banner.textContent = '⏳ No scalp setup — ' + (d.reason || 'waiting for 5m data') + win;
      banner.style.background = '#141b22'; banner.style.color = '#ffab00';
      document.getElementById('scalperCall').textContent = '';
      document.getElementById('scalperLevels').style.display = 'none';
    }
    // 📜 Today's call history — kept alive till target/stop/expiry
    try {
      const hist = document.getElementById('scalperHistory');
      const cnt = document.getElementById('scalperCallsCount');
      const calls = d.calls || [];
      if (cnt) cnt.textContent = calls.length ? calls.length + ' call' + (calls.length > 1 ? 's' : '') : '--';
      if (hist) {
        if (!calls.length) {
          hist.innerHTML = '<div style="color:var(--text-dim);padding:6px;text-align:center;font-size:12px">No calls fired yet today</div>';
        } else {
          hist.innerHTML = calls.map(c => {
            const st = c.status || 'ACTIVE';
            const border = st === 'TARGET_HIT' ? '#00c853' : st === 'STOP_HIT' ? '#ff1744' : st === 'EXPIRED' ? '#64748b' : '#ffab00';
            const chip = st === 'TARGET_HIT' ? 'strat-ok' : st === 'STOP_HIT' ? 'strat-bad' : st === 'EXPIRED' ? 'strat-off' : 'strat-wait';
            const label = st === 'TARGET_HIT' ? '🎯 HIT' : st === 'STOP_HIT' ? '🛑 STOP' : st === 'EXPIRED' ? 'EXPIRED' : '● ACTIVE';
            const when = c.time + ' · expires ' + (c.expires_at || '--') + (c.hit_time ? ' · resolved ' + c.hit_time : '');
            const detail = c.option + ' @ ₹' + c.entry + ' → 🎯 ₹' + c.target + ' / 🛑 ₹' + c.stop +
              (c.hit_premium ? ' · last ₹' + c.hit_premium : '') +
              (c.pnl_pts != null ? ' · P&L ' + (c.pnl_pts >= 0 ? '+' : '') + c.pnl_pts + ' pts' + (c.pnl_rs ? ' · ₹' + Number(c.pnl_rs).toLocaleString('en-IN') : '') : '');
            return stratRowHTML(when, label, detail, chip === 'strat-ok' ? 'ok' : chip === 'strat-bad' ? 'bad' : chip === 'strat-off' ? 'off' : 'wait')
              .replace('<div class="strat-row"', '<div class="strat-row" style="border-left-color:' + border + '"');
          }).join('');
        }
      }
    } catch (e) { /* history render is best-effort */ }
    // 💰 Dry-run P&L summary
    try {
      const pnl = d.pnl || {};
      const pnlEl = document.getElementById('scalperPnl');
      const pnlGrid = document.getElementById('scalperPnlGrid');
      if (pnlEl && pnlGrid) {
        const net = pnl.net_rs != null && pnl.net_rs !== 0 ? '₹' + Number(pnl.net_rs).toLocaleString('en-IN') : (pnl.net_pts != null ? pnl.net_pts + ' pts' : '--');
        pnlEl.textContent = pnl.resolved ? (pnl.resolved + ' trades · ' + pnl.wins + 'W/' + (pnl.resolved - pnl.wins) + 'L · WR ' + pnl.win_rate + '%') : 'no resolved calls yet';
        const rows = [];
        rows.push(stratRowHTML('Net P&L', net, 'paper, spread included', (pnl.net_pts || 0) >= 0 ? 'ok' : 'bad'));
        const byA = pnl.by_asset || {};
        for (const a of ['nifty', 'bnf', 'sensex', 'btc']) {
          const b = byA[a];
          if (b) rows.push(stratRowHTML(a.toUpperCase(), b.w + 'W/' + (b.n - b.w) + 'L', b.n + ' calls · ' + (b.pts >= 0 ? '+' : '') + b.pts + ' pts' + (b.rs ? ' · ₹' + Number(b.rs).toLocaleString('en-IN') : ''), b.pts >= 0 ? 'ok' : 'bad'));
        }
        if (!rows.length) rows.push('<div style="color:var(--text-dim);padding:6px;text-align:center;font-size:12px">No resolved calls yet — calls resolve to target/stop/expiry</div>');
        pnlGrid.innerHTML = rows.join('');
      }
      // 📅 Dry-run P&L by day — the over-time record (one immutable row per day)
      try {
        const hr = await fetch('/api/scalp/history?_=' + Date.now());
        const hd = await hr.json();
        const hEl = document.getElementById('scalperPnlHistory');
        const hUpd = document.getElementById('scalperPnlHistUpd');
        if (hUpd) hUpd.textContent = hd.history && hd.history.length ? hd.history.length + ' days' : '--';
        if (hEl) {
          const rowsH = (hd.history || []).map(r => {
            const net = r.net_rs != null && r.net_rs !== 0 ? '₹' + Number(r.net_rs).toLocaleString('en-IN') : (r.net_pts != null ? r.net_pts + ' pts' : '--');
            const btc = (r.by_asset || {}).btc;
            const btcTxt = btc ? ' · ₿ ' + (btc.pts >= 0 ? '+' : '') + btc.pts + ' pts' : '';
            const ok = (r.net_pts || 0) >= 0;
            return stratRowHTML(r.date, r.resolved + ' calls · ' + r.wins + 'W/' + (r.resolved - r.wins) + 'L · WR ' + r.win_rate + '%', 'net ' + net + btcTxt, ok ? 'ok' : 'bad');
          });
          if (!rowsH.length) rowsH.push('<div style="color:var(--text-dim);padding:6px;text-align:center;font-size:12px">First snapshot lands after the day resolves — auto at 00:10 IST</div>');
          hEl.innerHTML = rowsH.join('');
        }
      } catch (e) { /* best-effort */ }
    } catch (e) { /* best-effort */ }
    // Gauges
    const g = document.getElementById('scalperGauges');
    if (g && d.ema9 != null) {
      const rows = [];
      const add = (n, st, r, c) => rows.push(stratRowHTML(n, st, r, c));
      const emaUp = d.ema9 > d.ema21;
      add('EMA 9/21', emaUp ? 'BULL' : 'BEAR', 'EMA9 ' + Number(d.ema9).toLocaleString('en-IN') + ' vs EMA21 ' + Number(d.ema21).toLocaleString('en-IN'), emaUp ? 'ok' : 'bad');
      const vwDiff = d.vwap != null ? ((d.spot - d.vwap) / d.vwap * 100) : null;
      add('VWAP', d.vwap != null ? (d.spot >= d.vwap ? 'ABOVE' : 'BELOW') : '--', vwDiff != null ? (vwDiff >= 0 ? '+' : '') + vwDiff.toFixed(2) + '% vs VWAP ' + Number(d.vwap).toLocaleString('en-IN') : 'no data', vwDiff != null ? (vwDiff >= 0 ? 'ok' : 'bad') : 'wait');
      add('RSI (14)', d.rsi != null ? d.rsi.toFixed(0) : '--', d.rsi != null ? (d.rsi > 70 ? 'overbought' : d.rsi < 30 ? 'oversold' : 'neutral') : '', 'wait');
      add('Stoch', d.stoch_k != null ? 'K ' + d.stoch_k.toFixed(0) + ' / D ' + (d.stoch_d != null ? d.stoch_d.toFixed(0) : '--') : '--', d.stoch_k != null ? (d.stoch_k > 80 ? 'overbought' : d.stoch_k < 20 ? 'oversold' : 'neutral') : '', 'wait');
      add('Momentum (3 bar)', d.momentum != null ? (d.momentum >= 0 ? '+' : '') + d.momentum.toFixed(1) : '--', d.momentum != null ? (Math.abs(d.momentum) > 5 ? 'strong move' : 'quiet') : '', d.momentum != null && Math.abs(d.momentum) > 5 ? 'wait' : 'wait');
      const gate = d.trend_gate != null ? d.trend_gate : 0.8;
      const strong = d.trend_dist != null && d.trend_dist >= gate;
      add('Trend (200E)', d.trend_dist != null ? (strong ? 'STRONG' : 'WEAK') : '--', d.trend_dist != null ? '|spot−200E| ' + d.trend_dist.toFixed(2) + '% vs gate ' + gate + '%' : '', strong ? 'ok' : 'bad');
      const adxG = d.adx_gate != null ? d.adx_gate : 25;
      const adxOk = d.adx != null && d.adx >= adxG;
      add('ADX (14)', d.adx != null ? d.adx.toFixed(2) : '--', d.adx != null ? 'ADX ' + d.adx.toFixed(2) + ' vs gate ' + adxG + ' (trend strength)' : '', adxOk ? 'ok' : 'bad');
      const vg = d.vix_gate || [12, 18];
      const vixOk = d.vix != null && d.vix >= vg[0] && d.vix <= vg[1];
      add('Nifty VIX', d.vix != null ? d.vix.toFixed(1) : '--', d.vix != null ? 'VIX ' + d.vix.toFixed(1) + ' vs ' + vg[0] + '–' + vg[1] + ' (premium regime)' : '', vixOk ? 'ok' : 'bad');
      if (d.orb_high != null) {
        const inOrb = d.spot >= d.orb_low && d.spot <= d.orb_high;
        add('Opening Range', inOrb ? 'INSIDE' : (d.spot > d.orb_high ? 'ABOVE' : 'BELOW'), 'ORB ' + Number(d.orb_high).toLocaleString('en-IN') + ' / ' + Number(d.orb_low).toLocaleString('en-IN'), inOrb ? 'wait' : (d.spot > d.orb_high ? 'ok' : 'bad'));
      }
      g.innerHTML = rows.join('');
    }
  } catch (e) {}
}

// ── Shared strategy-status row renderer (used by Nifty + BTC + BNF + Sensex cards) ──
function stratRowHTML(name, state, reason, cls) {
  const border = cls === 'ok' ? '#00c853' : cls === 'bad' ? '#ff1744' : cls === 'wait' ? '#ffab00' : '#64748b';
  const chip = 'strat-' + (cls === 'ok' ? 'ok' : cls === 'bad' ? 'bad' : cls === 'wait' ? 'wait' : 'off');
  return '<div class="strat-row" style="border-left-color:' + border + '"><span class="strat-name">' + name + '</span><span class="strat-state ' + chip + '">' + state + '</span><span class="strat-reason">' + (reason || '') + '</span></div>';
}

function renderStratCard(listId, updatedId, rows) {
  const list = document.getElementById(listId);
  if (!list) return;
  list.innerHTML = rows.join('');
  const upd = document.getElementById(updatedId);
  if (upd) upd.textContent = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}

// BTC-style signal payload rows (used by BTC / Bank Nifty / Sensex)
function btcStyleRows(d) {
  const rows = [];
  const add = (n, st, r, c) => rows.push(stratRowHTML(n, st, r, c));
  const fmt = v => v != null ? Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 }) : '--';
  const sig = d.signal || 'WAIT';
  if (sig === 'BUY_LONG') add('200 EMA Bounce', 'BUY', d.reason || 'Setup active', 'ok');
  else if (sig === 'BUY_SHORT') add('200 EMA Bounce', 'SELL', d.reason || 'Setup active', 'bad');
  else add('200 EMA Bounce', 'WAIT', d.reason || 'No setup', 'wait');
  const adx = d.adx;
  const trend = adx >= 20 ? 'TRENDING' : adx >= 15 ? 'WEAK' : 'RANGING';
  add('Trend Strength', trend, 'ADX ' + (adx != null ? adx.toFixed(1) : '--') + ' | DI+ ' + (d.di_plus != null ? d.di_plus.toFixed(1) : '--') + ' vs DI- ' + (d.di_minus != null ? d.di_minus.toFixed(1) : '--'), trend === 'TRENDING' ? (d.di_plus > d.di_minus ? 'ok' : 'bad') : 'wait');
  const rsi = d.rsi;
  if (rsi != null) add('Momentum (RSI)', rsi > 70 ? 'OVERBOUGHT' : rsi < 30 ? 'OVERSOLD' : 'NEUTRAL', 'RSI ' + rsi.toFixed(1), 'wait');
  else add('Momentum (RSI)', '--', 'no data', 'off');
  if (d.entry_zone) add('Entry Zone', 'IN ZONE', 'Price at 200 EMA (' + fmt(d.ema_200) + ') — watch for bounce', 'ok');
  else if (d.ema_distance_pct != null) {
    const dist = d.ema_distance_pct;
    add('Entry Zone', 'AWAY', (dist >= 0 ? '+' : '') + dist.toFixed(2) + '% from 200 EMA (' + fmt(d.ema_200) + ')', 'wait');
  } else add('Entry Zone', 'AWAY', 'No 200 EMA data', 'wait');
  return rows;
}

async function refreshBtcStrategies() {
  const rows = btcStyleRows(window._lastBtc || {});
  const s15 = window._lastBtc15;
  if (s15 && s15.signal) {
    const st = s15.signal === 'BUY_LONG' ? 'BUY' : s15.signal === 'BUY_SHORT' ? 'SELL' : 'WAIT';
    rows.push(stratRowHTML('15m Signal', st, (s15.reason || '').slice(0, 90), st === 'BUY' ? 'ok' : st === 'SELL' ? 'bad' : 'wait'));
  }
  renderStratCard('btcStrategiesList', 'btcStratUpdated', rows);
}

async function refreshBnfStrategies(d) {
  const rows = btcStyleRows(d || window._lastBnf || {});
  try {
    const resp = await fetch('/api/oi?asset=bnf&_=' + Date.now());
    if (resp.ok) {
      const oi = await resp.json();
      const ob = oi.bias || 'WAIT';
      const st = ob === 'BULLISH' ? 'BUY' : ob === 'BEARISH' ? 'SELL' : ob;
      rows.push(stratRowHTML('OI Buildup', st, (oi.reason || '').slice(0, 90), ob === 'BULLISH' ? 'ok' : ob === 'BEARISH' ? 'bad' : 'wait'));
    }
  } catch (e) {}
  renderStratCard('bnfStrategiesList', 'bnfStratUpdated', rows);
}

async function refreshSensexStrategies(d) {
  renderStratCard('sensexStrategiesList', 'sensexStratUpdated', btcStyleRows(d || window._lastSensex || {}));
}

// ── Nifty Strategy Status (positional + intraday breakdown — always visible) ──
async function refreshStrategies() {
  const list = document.getElementById('strategiesList');
  if (!list) return;
  const renderRows = (orb, intra, oi, gap) => {
    const s = window._lastSignal || {};
    const rows = [];
    const add = (name, state, reason, cls) => rows.push(stratRowHTML(name, state, reason, cls));
    // 200 EMA Bounce (1h)
    if (s.signal === 'BUY_CALLS') add('200 EMA Bounce', 'BUY', s.reason || 'Setup active — buy CE', 'ok');
    else if (s.signal === 'BUY_PUTS') add('200 EMA Bounce', 'SELL', s.reason || 'Setup active — buy PE', 'bad');
    else {
      const distTxt = s.distance_pct != null ? 'spot ' + (s.distance_pct >= 0 ? '+' : '') + s.distance_pct + '% vs 200 EMA (' + (s.ema_200 ? s.ema_200.toLocaleString('en-IN') : '--') + ')' : '';
      add('200 EMA Bounce', 'WAIT', 'No bounce yet — ' + distTxt, 'wait');
    }
    // BTST (positional)
    if (s.btst_recommended) add('BTST (Positional)', 'ACTIVE', s.btst_recommended, 'ok');
    else add('BTST (Positional)', 'WAIT', 'No setup — only triggers on a BUY_CALLS/BUY_PUTS signal', 'wait');
    // ORB
    if (orb && orb.reason) {
      const st = orb.signal === 'ORB_BUY' ? 'BUY' : orb.signal === 'ORB_SELL' ? 'SELL' : 'WAIT';
      add('ORB Breakout', st, (orb.reason || '').slice(0, 90), st === 'BUY' ? 'ok' : st === 'SELL' ? 'bad' : 'wait');
    } else add('ORB Breakout', 'WAIT', 'No setup — window 9:30-10:15 AM', 'wait');
    // VWAP
    if (intra && intra.vwap && intra.vwap.reason) {
      const v = intra.vwap;
      const st = v.signal === 'VWAP_BUY' ? 'BUY' : v.signal === 'VWAP_SELL' ? 'SELL' : (v.signal || 'WAIT');
      add('VWAP Reversion', st, (v.reason || '').slice(0, 90), st === 'BUY' ? 'ok' : st === 'SELL' ? 'bad' : 'wait');
    } else add('VWAP Reversion', 'WAIT', 'No data yet', 'wait');
    // EMA Cross (5m)
    if (intra && intra.ema && intra.ema.reason) {
      const e = intra.ema;
      const st = e.signal === 'EMA_BUY' ? 'BUY' : e.signal === 'EMA_SELL' ? 'SELL' : (e.signal || 'WAIT');
      add('EMA Cross (5m)', st, (e.reason || '').slice(0, 90), st === 'BUY' ? 'ok' : st === 'SELL' ? 'bad' : 'wait');
    } else add('EMA Cross (5m)', 'WAIT', 'No data yet', 'wait');
    // Contrarian
    if (s.contrarian_signal) {
      const cs = s.contrarian_signal;
      if (cs === 'NEUTRAL') add('Contrarian PCR', 'NEUTRAL', (s.contrarian_reason || '').slice(0, 90), 'wait');
      else if (cs === 'SELL_CALLS') add('Contrarian PCR', 'BEARISH', (s.contrarian_reason || '').slice(0, 90), 'bad');
      else if (cs === 'SELL_PUTS') add('Contrarian PCR', 'BULLISH', (s.contrarian_reason || '').slice(0, 90), 'ok');
    }
    // Gap & Go
    if (gap && gap.reason) {
      const st = gap.signal && gap.signal !== 'WAIT' ? gap.signal : 'WAIT';
      add('Gap & Go', st, (gap.reason || '').slice(0, 90), st === 'WAIT' ? 'wait' : 'ok');
    } else add('Gap & Go', 'WAIT', 'No data yet', 'wait');
    // OI Buildup
    if (oi && oi.reason) {
      const ob = oi.bias || 'WAIT';
      const st = ob === 'BULLISH' ? 'BUY' : ob === 'BEARISH' ? 'SELL' : ob;
      add('OI Buildup', st, (oi.reason || '').slice(0, 90), ob === 'BULLISH' ? 'ok' : ob === 'BEARISH' ? 'bad' : 'wait');
    } else add('OI Buildup', 'WAIT', 'No data yet', 'wait');
    list.innerHTML = rows.join('');
    const upd = document.getElementById('stratUpdated');
    if (upd) upd.textContent = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  };
  // Phase 1: signal-based rows immediately (never blank)
  const state = { orb: null, intra: null, oi: null, gap: null };
  const renderAll = () => renderRows(state.orb, state.intra, state.oi, state.gap);
  renderAll();
  // Phase 2: independent per-endpoint fetches — each row updates as its data arrives
  const fetchT = (url) => {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 20000);
    return fetch(url, { signal: ctrl.signal }).then(r => r.json()).catch(() => null).finally(() => clearTimeout(t));
  };
  fetchT('/api/orb').then(d => { state.orb = d; renderAll(); });
  fetchT('/api/intraday').then(d => { state.intra = d; renderAll(); });
  fetchT('/api/oi').then(d => { state.oi = d; renderAll(); });
  fetchT('/api/gapgo').then(d => { state.gap = d; renderAll(); });
}

// ── Bank Nifty ──
async function fetchBnf() {
  try {
    const resp = await fetch('/api/banknifty?_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const d = await resp.json();
    window._lastBnf = d;
    renderBnf(d);
  } catch(e) {}
}

// ── OI Buildup (Smart Money) ──
async function fetchOi(prefix) {
  prefix = prefix || '';
  try {
    const resp = await fetch((prefix ? '/api/bnf/oi' : '/api/oi') + '?_=' + Date.now());
    if (!resp.ok) return;
    renderOi(await resp.json(), prefix);
  } catch(e) {}
}

function renderOi(d, prefix) {
  prefix = prefix || '';
  const P = s => prefix ? prefix + s.charAt(0).toUpperCase() + s.slice(1) : s;
  const id = s => document.getElementById(P(s));
    const bias = id('oiBias');
    if (!bias) return;
    const colors = {BULLISH: 'var(--green)', BEARISH: 'var(--red)', NEUTRAL: 'var(--yellow)'};
    bias.textContent = d.bias || '--';
    bias.style.color = colors[d.bias] || 'var(--text-dim)';
    bias.style.background = (colors[d.bias] || '#222') + '22';
    id('oiReason').textContent =
      d.reason || d.error || 'Collecting OI snapshots… (need 2 samples, ~10 min)';
    const ce = d.ce_buildup || [], pe = d.pe_buildup || [];
    id('oiCe').innerHTML =
      '<b style="color:var(--green)">▲ CE loading</b><br>' +
      (ce.length ? ce.slice(0, 4).map(r => `${r.strike} +${r.oi_gain.toLocaleString('en-IN')} OI`).join('<br>')
                 : '<span style="color:var(--text-dim)">none</span>');
    id('oiPe').innerHTML =
      '<b style="color:var(--red)">▼ PE loading</b><br>' +
      (pe.length ? pe.slice(0, 4).map(r => `${r.strike} +${r.oi_gain.toLocaleString('en-IN')} OI`).join('<br>')
                 : '<span style="color:var(--text-dim)">none</span>');
}

// ── Gap & Go / Gap Fade ──
async function fetchGap() {
  try {
    const resp = await fetch('/api/gapgo?_=' + Date.now());
    if (!resp.ok) return;
    const d = await resp.json();
    const sig = document.getElementById('gapSignal');
    if (!sig) return;
    const map = {GAP_GO_BUY: '🟢 GAP & GO → BUY CE', GAP_FADE_BUY: '🔴 GAP FADE → BUY PE',
                 GAP_FILL_WATCH: '⏳ WATCH FILL', WAIT: 'WAIT'};
    sig.textContent = map[d.signal] || d.signal || '--';
    sig.style.color = d.signal === 'GAP_GO_BUY' ? 'var(--green)'
      : d.signal === 'GAP_FADE_BUY' ? 'var(--red)' : 'var(--yellow)';
    document.getElementById('gapDetail').textContent =
      `Gap ${d.gap_pct != null ? d.gap_pct + '%' : '--'} | Open ${d.open || '--'} | VWAP ${d.vwap || '--'} | Price ${d.price || '--'}`;
    document.getElementById('gapReason').textContent = d.reason || d.error || '';
  } catch(e) {}
}

function renderBnf(d) {
  const el = id => document.getElementById(id);
  if (!el('bnfSpot')) return;
  refreshBnfStrategies(d);
  el('bnfSpot').textContent = d.spot != null ? Number(d.spot).toLocaleString('en-IN', {maximumFractionDigits: 0}) : '--';
  el('bnfSpot').style.color = d.ema_distance_pct != null && d.ema_distance_pct < 0 ? 'var(--red)' : 'var(--green)';
  const sigEl = el('bnfSignal');
  const sig = d.signal || 'WAIT';
  sigEl.textContent = sig === 'BUY_LONG' ? '🟢 LONG' : sig === 'BUY_SHORT' ? '🔴 SHORT' : sig === 'EXIT_LONGS' ? '⚠️ EXIT L' : sig === 'EXIT_SHORTS' ? '⚠️ EXIT S' : '⏳ WAIT';
  sigEl.style.color = sig === 'BUY_LONG' ? 'var(--green)' : sig === 'BUY_SHORT' ? 'var(--red)' : 'var(--yellow)';
  el('bnfAdx').textContent = d.adx != null ? d.adx : '--';
  el('bnfRsi').textContent = d.rsi != null ? d.rsi : '--';
  el('bnfReason').textContent = d.reason || '';
  el('bnfEma').textContent = d.ema_200 != null ? Number(d.ema_200).toLocaleString('en-IN', {maximumFractionDigits: 0}) : '--';
  el('bnfDi').textContent = d.di_plus != null && d.di_minus != null ? d.di_plus + ' / ' + d.di_minus : '--';
  const dist = d.ema_distance_pct;
  const distEl = el('bnfDist');
  distEl.textContent = dist != null ? (dist > 0 ? '+' : '') + dist + '%' : '--';
  distEl.style.color = dist > 0 ? 'var(--green)' : dist < 0 ? 'var(--red)' : 'var(--yellow)';
  const lv = el('bnfLevels');
  lv.innerHTML = '';
  if (d.stop_level && d.target_level) {
    lv.innerHTML = '<div style="display:flex;gap:12px;flex-wrap:wrap">' +
      '<span style="color:var(--red);font-weight:700">🛑 Stop: ' + Number(d.stop_level).toLocaleString('en-IN', {maximumFractionDigits: 0}) + '</span>' +
      '<span style="color:var(--green);font-weight:700">🎯 Target: ' + Number(d.target_level).toLocaleString('en-IN', {maximumFractionDigits: 0}) + '</span></div>';
  } else {
    lv.innerHTML = '<span style="color:var(--yellow);font-weight:600">⏳ HOLD — no trade</span> <span style="color:var(--text-dim)">' + (d.reason || 'waiting for 200 EMA bounce setup') + '</span>';
  }
  // BNF recommendation banner
  const rec = document.getElementById('bnfRec');
  if (rec && d.recommendation) {
    rec.style.display = 'block';
    rec.textContent = '💡 ' + d.recommendation;
    rec.style.background = d.action === 'BUY' ? 'rgba(0,200,83,0.12)' : d.action === 'SELL' ? 'rgba(255,23,68,0.12)' : 'rgba(255,193,7,0.08)';
    rec.style.color = d.action === 'BUY' ? 'var(--green)' : d.action === 'SELL' ? 'var(--red)' : 'var(--yellow)';
  }
  // BNF alerts
  const al = document.getElementById('bnfAlertsList');
  if (al && d.alerts && d.alerts.length) {
    al.innerHTML = d.alerts.slice().reverse().map(a => {
      const color = a.signal === 'BUY_LONG' ? 'var(--green)' : a.signal === 'BUY_SHORT' ? 'var(--red)' : 'var(--yellow)';
      return '<div style="padding:4px 6px;border-left:3px solid ' + color + ';background:rgba(124,58,237,0.05);margin:3px 0;border-radius:4px">' +
        '<b style="color:' + color + '">' + a.signal + '</b> <span style="color:var(--text-dim)">' + a.date + ' ' + a.time + ' <span style="opacity:0.6">(was ' + a.prev + ')</span></span><br>' +
        '<span style="color:var(--text-dim)">' + a.reason + '</span></div>';
    }).join('');
  } else if (al) {
    al.innerHTML = '<div style="color:var(--text-dim);padding:8px;text-align:center">No signal changes yet today</div>';
  }
}

// ── Expiry Countdown ──
async function fetchExpiry(prefix) {
  prefix = prefix || '';
  try {
    const resp = await fetch((prefix ? '/api/bnf/expiry' : '/api/expiry') + '?_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    renderExpiry(await resp.json(), prefix);
  } catch(e) {}
}

function renderExpiry(d, prefix) {
  prefix = prefix || '';
  const P = s => prefix ? prefix + s.charAt(0).toUpperCase() + s.slice(1) : s;
  const el = id => document.getElementById(P(id));
  if (!el('expiryRead')) return;
  const g = el('expiryGamma');
  g.textContent = (d.gamma_risk || '--').toUpperCase();
  g.style.background = d.gamma_risk === 'extreme' ? 'rgba(255,23,68,0.2)' : d.gamma_risk === 'high' ? 'rgba(255,23,68,0.12)' : d.gamma_risk === 'medium' ? 'rgba(255,193,7,0.15)' : 'rgba(0,200,83,0.15)';
  g.style.color = d.gamma_risk === 'extreme' || d.gamma_risk === 'high' ? 'var(--red)' : d.gamma_risk === 'medium' ? 'var(--yellow)' : 'var(--green)';
  el('expiryRead').textContent = d.read || '';
}

// ── Weekly Review ──
async function fetchWeekly() {
  try {
    const resp = await fetch('/api/weeklyreview?_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    renderWeekly(await resp.json());
  } catch(e) {}
}

function renderWeekly(d) {
  const el = id => document.getElementById(id);
  if (!el('weeklyPnl')) return;
  if (d.error || (d.trades === 0 && !d.pnl)) { return; }
  el('weeklyWeek').textContent = d.week || '';
  const p = el('weeklyPnl');
  p.textContent = d.pnl > 0 ? '₹' + Math.round(d.pnl).toLocaleString('en-IN') : d.pnl < 0 ? '-₹' + Math.round(Math.abs(d.pnl)).toLocaleString('en-IN') : '₹0';
  p.style.color = d.pnl > 0 ? 'var(--green)' : d.pnl < 0 ? 'var(--red)' : 'var(--text-dim)';
  el('weeklyTrades').textContent = d.trades;
  const wr = el('weeklyWR');
  wr.textContent = d.win_rate + '%';
  wr.style.color = d.win_rate >= 50 ? 'var(--green)' : d.win_rate >= 40 ? 'var(--yellow)' : 'var(--red)';
  el('weeklyRead').textContent = d.read || '';
}

// ── Init ──
// Stagger initial loads: light first, heavy progressively — avoids cold-start pileup
fetchSignal(); fetchChain(); fetchBnfChain(); fetchChart(); fetchBtcChart(); fetchBnfChart(); fetchSensexChart();
refreshStrategies(); refreshBtcStrategies(); refreshBnfStrategies(); refreshSensexStrategies();
async function fetchStockMovers() {
  const card = document.getElementById('stockMoversCard');
  if (!card) return;
  try {
    const resp = await fetch('/api/stocks/movers?_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const d = await resp.json();
    const upd = document.getElementById('stockMoversUpd');
    if (upd) upd.textContent = d.timestamp || '';
    const note = document.getElementById('stockMoversNote');
    if (d.error) {
      note.textContent = '⚠️ ' + d.error;
      return;
    }
    if (note) note.textContent = d.screened ? 'Screened ' + d.screened + ' NIFTY-50 names · ' + (d.source || '') : '';
    const dayList = document.getElementById('stockDayList');
    const swingList = document.getElementById('stockSwingList');
    const rowHTML = (r, primary) => {
      const up = r.direction === 'UP';
      const col = up ? 'var(--green)' : 'var(--red)';
      const arrow = up ? '🟢' : '🔴';
      const pctTxt = (primary === 'day' ? r.day_pct : r.mom5) != null ? ((primary === 'day' ? r.day_pct : r.mom5) >= 0 ? '+' : '') + (primary === 'day' ? r.day_pct : r.mom5) + '%' : '--';
      const detail = (r.trend ? r.trend + ' · ' : '') + 'Vol ' + (r.vol_ratio ? r.vol_ratio + '×' : '--') + ' · RSI ' + (r.rsi != null ? r.rsi : '--') + ' · ATR ' + (r.atr != null ? r.atr : '--');
      return '<div class="strat-row" style="border-left-color:' + col + '">' +
        '<span class="strat-name">' + arrow + ' <b>' + r.name + '</b> <span style="opacity:.55;font-size:10px">' + r.symbol + '</span><br>' +
        '<span style="font-size:10px;color:var(--text-dim)">' + detail + '</span></span>' +
        '<span class="strat-state ' + (up ? 'strat-ok' : 'strat-bad') + '">' + pctTxt + '</span>' +
        '<span class="strat-reason">₹' + Number(r.price).toLocaleString('en-IN') + ' → 🎯 ₹' + Number(r.target).toLocaleString('en-IN') + ' (' + (r.target_pct >= 0 ? '+' : '') + r.target_pct + '%)<br>' +
        '<span style="font-size:10px;color:var(--text-dim)">⏳ ' + r.timeline + '</span></span></div>';
    };
    dayList.innerHTML = (d.day_trade || []).length
      ? d.day_trade.map(r => rowHTML(r, 'day')).join('')
      : '<div style="color:var(--text-dim);padding:6px;text-align:center;font-size:12px">No big movers right now</div>';
    swingList.innerHTML = (d.swing || []).length
      ? d.swing.map(r => rowHTML(r, 'swing')).join('')
      : '<div style="color:var(--text-dim);padding:6px;text-align:center;font-size:12px">No swing setups right now</div>';
  } catch (e) {
    const note = document.getElementById('stockMoversNote');
    if (note) note.textContent = '⚠️ Stock movers unavailable';
  }
}

async function fetchAssetScalper(asset, p) {
  const banner = document.getElementById(p + 'ScalperBanner');
  if (!banner) return;
  const cur = asset === 'btc' ? '$' : '₹';
  try {
    const resp = await fetch('/api/scalper?asset=' + asset + '&_=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const d = await resp.json();
    const upd = document.getElementById(p + 'ScalperUpd');
    if (upd) upd.textContent = d.timestamp || '';
    const levels = document.getElementById(p + 'ScalperLevels');
    if (d.signal === 'SCALP_LONG' && d.call && !d.call.blocked) {
      banner.innerHTML = '<span class="live-badge live-long">🟢 LIVE</span>🟢 LONG — ' + d.call.option + ' @ ' + cur + d.call.entry + ' (score ' + (d.score >= 0 ? '+' : '') + d.score + ') ⏳ ' + (d.call.expires_at || '');
      banner.style.background = '#0a2816'; banner.style.color = '#80ffb4';
      document.getElementById(p + 'ScalperEntry').textContent = 'Entry ' + cur + d.call.entry;
      document.getElementById(p + 'ScalperTarget').textContent = '🎯 ' + cur + d.call.target;
      document.getElementById(p + 'ScalperStop').textContent = '🛑 ' + cur + d.call.stop;
      levels.style.display = 'flex';
    } else if (d.signal === 'SCALP_SHORT' && d.call && !d.call.blocked) {
      banner.innerHTML = '<span class="live-badge live-short">🔴 LIVE</span>🔴 SHORT — ' + d.call.option + ' @ ' + cur + d.call.entry + ' (score ' + (d.score >= 0 ? '+' : '') + d.score + ') ⏳ ' + (d.call.expires_at || '');
      banner.style.background = '#280a0a'; banner.style.color = '#ff8080';
      document.getElementById(p + 'ScalperEntry').textContent = 'Entry ' + cur + d.call.entry;
      document.getElementById(p + 'ScalperTarget').textContent = '🎯 ' + cur + d.call.target;
      document.getElementById(p + 'ScalperStop').textContent = '🛑 ' + cur + d.call.stop;
      levels.style.display = 'flex';
    } else if (d.call && d.call.blocked) {
      banner.textContent = '🚫 ' + (d.signal === 'SCALP_LONG' ? 'LONG' : 'SHORT') + ' blocked — ' + (d.call.block_reason || 'spread too wide');
      banner.style.background = '#2a1a0a'; banner.style.color = '#ffab00';
      levels.style.display = 'none';
    } else {
      const win = d.window === 'BLOCKED' ? ' ⏸ ' + (d.window_reason || '') : '';
      banner.textContent = '⏳ No scalp — ' + (d.reason || 'waiting for 5m data') + win;
      banner.style.background = '#141b22'; banner.style.color = '#ffab00';
      levels.style.display = 'none';
    }
    // mini history
    const hist = document.getElementById(p + 'ScalperHistory');
    if (hist) {
      const calls = d.calls || [];
      if (!calls.length) {
        hist.innerHTML = '<div style="color:var(--text-dim);padding:4px;text-align:center;font-size:11px">No calls fired today</div>';
      } else {
        hist.innerHTML = calls.map(c => {
          const st = c.status || 'ACTIVE';
          const border = st === 'TARGET_HIT' ? '#00c853' : st === 'STOP_HIT' ? '#ff1744' : st === 'EXPIRED' ? '#64748b' : '#ffab00';
          const label = st === 'TARGET_HIT' ? '🎯 HIT' : st === 'STOP_HIT' ? '🛑 STOP' : st === 'EXPIRED' ? 'EXPIRED' : '● ACTIVE';
          const chip = st === 'TARGET_HIT' ? 'strat-ok' : st === 'STOP_HIT' ? 'strat-bad' : st === 'EXPIRED' ? 'strat-off' : 'strat-wait';
          return stratRowHTML(c.time + ' · exp ' + (c.expires_at || '--'), label, c.option + ' @ ' + cur + c.entry + ' → 🎯 ' + cur + c.target + ' / 🛑 ' + cur + c.stop, chip === 'strat-ok' ? 'ok' : chip === 'strat-bad' ? 'bad' : chip === 'strat-off' ? 'off' : 'wait')
            .replace('<div class="strat-row"', '<div class="strat-row" style="border-left-color:' + border + '"');
        }).join('');
      }
    }
  } catch (e) { /* best-effort */ }
}

fetchScalper();
// multi-asset scalper cards
fetchAssetScalper('bnf', 'bnf');
fetchAssetScalper('sensex', 'sx');
fetchAssetScalper('btc', 'btc');
fetchExpiry(); fetchExpiry('bnf'); fetchGap(); fetchWeekly(); initTimeframeToggles(); initQuickNav();
setTimeout(() => { fetchBtc(); fetchBnf(); fetchSensex(); fetchOi(); fetchOi('bnf'); }, 800);
setTimeout(() => { fetchIvRank(); fetchIvRank('bnf'); fetchFiiDii(); fetchOutlook(); }, 2500);
setTimeout(() => { fetchBacktest(); fetchBacktest('bnf'); }, 5000);
setTimeout(fetchStockMovers, 8000);
setInterval(fetchStockMovers, 15 * 60 * 1000);  // movers refresh every 15 min
fetchFiiDii();
fetchOutlook();
fetchBtc();
fetchBnf();
fetchJournal();
fetchAlerts();
fetchTunnelURL();
fetchORB();
fetchIntraday();
fetchAlgoStatus();
setInterval(fetchSignal, 60000);
setInterval(fetchScalper, 30000);
setInterval(() => { fetchAssetScalper('bnf', 'bnf'); fetchAssetScalper('sensex', 'sx'); fetchAssetScalper('btc', 'btc'); }, 30000);
setInterval(refreshStrategies, 120000);
setInterval(refreshBtcStrategies, 60000);

// ── Version badge: show git commit hash (Mac ⇄ Render parity at a glance) ──
async function fetchVersion() {
  try {
    const r = await fetch('/api/health?_=' + Date.now());
    const d = await r.json();
    const el = document.getElementById('versionBadge');
    if (el) el.textContent = 'v' + (d.version || '?') + (d.host ? ' · cloud' : '');
  } catch (e) {}
}
fetchVersion();
setInterval(fetchVersion, 120000);
setInterval(refreshBnfStrategies, 60000);
setInterval(refreshSensexStrategies, 60000);
setInterval(fetchIvRank, 300000);
setInterval(fetchChain, 60000);
setInterval(fetchExpiry, 600000);
setInterval(fetchFiiDii, 300000);
setInterval(fetchOutlook, 300000);
setInterval(fetchBtc, 60000);
setInterval(fetchOi, 120000);
setInterval(() => fetchOi('bnf'), 120000);
setInterval(fetchGap, 60000);
setInterval(fetchBnfChain, 60000);
setInterval(() => fetchExpiry('bnf'), 600000);
setInterval(() => fetchIvRank('bnf'), 300000);
setInterval(() => fetchBacktest('bnf'), 3600000);
setInterval(fetchBnf, 60000);
setInterval(fetchJournal, 120000);
setInterval(fetchAlerts, 30000);
setInterval(fetchORB, 60000);
setInterval(fetchIntraday, 60000);
setInterval(fetchAlgoStatus, 30000);

// Service worker disabled — was causing blank dashboard
// To re-enable: uncomment below after clearing browser cache
