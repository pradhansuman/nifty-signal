
// JS entry — runs immediately (script at bottom, DOM already ready)
var _jsAlive = true;
document.getElementById('debugInfo').textContent = 'JS loaded ✅';
let cachedSignal = null;
let deferredPrompt = null;

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
    document.getElementById('debugInfo').textContent = 'Data: ' + JSON.stringify(cachedSignal).slice(0, 150);
    render(cachedSignal);
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
    sig === 'BUY_CALLS' ? 'buy' : sig === 'STAND_ASIDE' ? 'exit' : 'wait'
  );
  
  const icons = { BUY_CALLS: '🟢', WAIT: '🟡', STAND_ASIDE: '🔴', ERROR: '⚪' };
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

  // Levels card (only for BUY)
  if (sig === 'BUY_CALLS' || sig === 'BUY_PUTS') {
    document.getElementById('levelsCard').classList.remove('hidden');
    document.getElementById('targetLevel').textContent = s.stop_level
      ? '🛑 Stop Loss: ' + s.stop_level.toLocaleString('en-IN')
      : '🛑 Stop: --';
    document.getElementById('stopLevel').textContent = s.expected_move_pct
      ? '📐 Expected 1σ Move: ±' + s.expected_move_pct + '%'
      : '';
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
      document.getElementById('targetLevelPill').textContent = s.stop_level ? '🛑 Index Stop: ' + s.stop_level : '';
      document.getElementById('stopLevelPill').textContent = '';
    } else if (s.signal === 'BUY_PUTS' && s.recommended_trade) {
      document.getElementById('tradeType').textContent = '📉 Buy ' + s.entry_strike + ' PE';
      let tradeInfo = '';
      if (s.entry_premium != null) {
        tradeInfo = 'Premium: ₹' + s.entry_premium + ' (₹' + Math.round(s.entry_premium * 65).toLocaleString('en-IN') + '/lot)';
      }
      document.getElementById('entryLevel').textContent = tradeInfo || ('Entry: ' + (s.entry_strike || '--'));
      document.getElementById('targetLevelPill').textContent = s.stop_level ? '🛑 Index Stop: ' + s.stop_level : '';
      document.getElementById('stopLevelPill').textContent = '';
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

  // ── Trailing Stop ──
  const fixedStop = s.stop_level;
  const trailStopVal = s.trail_stop;
  document.getElementById('fixedStop').textContent = fixedStop ? fixedStop.toLocaleString('en-IN') : '--';
  document.getElementById('trailStop').textContent = trailStopVal ? trailStopVal.toLocaleString('en-IN') : '--';
  if (trailStopVal && fixedStop) {
    const gap = trailStopVal - fixedStop;
    const gapEl = document.getElementById('stopGap');
    gapEl.textContent = (gap > 0 ? '+' : '') + gap.toFixed(0) + ' pts';
    gapEl.style.color = gap > 0 ? 'var(--green)' : 'var(--red)';
    const trailEl = document.getElementById('trailStop');
    trailEl.style.color = gap > 50 ? 'var(--green)' : 'var(--yellow)';
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
      html += positions.map(p =>
        `<div style="font-size:10px;padding:2px 0;border-bottom:1px solid var(--border)">
          #${p.id} ${p.direction} ${p.strike} ${p.lots}L @ ₹${p.entry_premium} (${p.signal_type})
        </div>`
      ).join('');
    }
    
    if (closedTrades.length) {
      html += '<div style="font-size:10px;font-weight:700;color:var(--text-dim);margin-top:4px">Closed P&L:</div>';
      html += closedTrades.slice(-5).reverse().map(t => {
        const pnlClass = (t.pnl||0) >= 0 ? 'var(--green)' : 'var(--red)';
        return `<div style="font-size:10px;padding:2px 0;border-bottom:1px solid var(--border)">
          #${t.id} ${t.direction} ${t.strike}: <span style="color:${pnlClass}">₹${(t.pnl||0).toLocaleString('en-IN')} (${t.pnl_pct||0}%)</span>
        </div>`;
      }).join('');
    }
    
    document.getElementById('algoOrders').innerHTML = html || '<div style="font-size:10px;color:var(--text-dim)">No positions</div>';
  } catch(e) {}
}

// ── Init ──
fetchSignal();
fetchJournal();
fetchAlerts();
fetchTunnelURL();
fetchORB();
fetchIntraday();
fetchAlgoStatus();
setInterval(fetchSignal, 60000);
setInterval(fetchJournal, 120000);
setInterval(fetchAlerts, 30000);
setInterval(fetchORB, 60000);
setInterval(fetchIntraday, 60000);
setInterval(fetchAlgoStatus, 30000);

// Service worker disabled — was causing blank dashboard
// To re-enable: uncomment below after clearing browser cache
