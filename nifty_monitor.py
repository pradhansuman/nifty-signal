#!/usr/bin/env python3
"""
Nifty 50 Entry Monitor v3 — Full Long/Short with Exit Signals
=============================================================
- BUY_CALLS: 200 EMA bounce with bullish trend
- BUY_PUTS: 200 EMA breakdown with bearish trend
- EXIT_LONGS: trend weakening or target/stop hit
- WAIT: no clear signal
"""

import json, sys, math, time, os
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd

SYMBOL = "^NSEI"
VIX_SYMBOL = "^INDIAVIX"
ENTRY_ZONE_PCT = 0.5       # Within 0.5% of 200 EMA for entry
MIN_ADX = 18                # Minimum trending strength
MAX_RSI = 70                # Not overbought for longs
MIN_RSI = 30                # Not oversold for shorts
BROKEN_BELOW_PCT = -0.8     # -0.8% below 200 EMA = trend broken (exit longs)
BROKEN_ABOVE_PCT = 0.8      # +0.8% above 200 EMA after breakdown = exit puts
ADX_WEAKENING = 15          # ADX below this = trend dying (exit signal)

# ── Expiry Calendar ──

def get_nifty_expiries(from_date=None):
    """Nifty expiries: Weekly=Tuesday, Monthly=last Tuesday."""
    if from_date is None: from_date = datetime.now()
    today = from_date.date()
    expiries = []; seen_months = set()
    for i in range(46):
        d = today + timedelta(days=i)
        if d.weekday() != 1: continue
        last_day_ref = datetime(d.year, d.month, 28)
        days_back = (last_day_ref.weekday() - 1) % 7
        last_tue = last_day_ref.date() - timedelta(days=days_back)
        if d == last_tue and d.month not in seen_months:
            seen_months.add(d.month)
            expiries.append({"date": d.strftime("%Y-%m-%d"), "display": d.strftime("%d-%b-%Y"), "type": "monthly", "dte": (d-today).days})
        else:
            expiries.append({"date": d.strftime("%Y-%m-%d"), "display": d.strftime("%d-%b-%Y"), "type": "weekly", "dte": (d-today).days})
    expiries.sort(key=lambda x: x["dte"])
    return expiries


def select_expiry(expiries, strategy="buy"):
    viable = [e for e in expiries if e["dte"] >= 2]
    if strategy == "buy":
        monthly = [e for e in viable if e["type"] == "monthly" and e["dte"] >= 7]
        if monthly: return monthly[0]
        weekly = [e for e in viable if e["type"] == "weekly" and e["dte"] >= 5]
        if weekly: return weekly[0]
        return viable[0] if viable else expiries[0]
    elif strategy == "sell":
        weekly = [e for e in viable if e["type"] == "weekly" and e["dte"] <= 7]
        if weekly: return weekly[0]
        return viable[0] if viable else expiries[0]
    return viable[0] if viable else expiries[0]


def select_btst_expiry(expiries):
    viable = [e for e in expiries if e["type"] == "weekly" and 1 <= e["dte"] <= 5]
    if viable: return viable[0]
    viable2 = [e for e in expiries if e["type"] == "weekly" and e["dte"] >= 1]
    return viable2[0] if viable2 else expiries[1] if len(expiries) > 1 else expiries[0]


def ema(data, period):
    if len(data) < period: return None
    alpha = 2 / (period + 1)
    result = data[0]
    for v in data[1:]: result = alpha * v + (1 - alpha) * result
    return result

def rsi(prices, period=14):
    if len(prices) < period + 1: return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains[:period]) / period; al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period-1) + gains[i]) / period
        al = (al * (period-1) + losses[i]) / period
    if al == 0: return 100.0
    return 100 - (100 / (1 + ag / al))


def main():
    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S IST"),
        "signal": "WAIT",
        "spot": None, "ema_200": None, "distance_pct": None,
        "adx": None, "di_plus": None, "di_minus": None,
        "rsi_14": None, "vix": None,
        # Positional trade
        "selected_expiry": None, "expiry_type": None,
        "dte": None, "theta_zone": None, "atm_strike": None,
        "recommended_trade": None,
        "entry_strike": None, "target_strike": None, "stop_level": None,
        "trade_direction": None,
        # BTST
        "btst_expiry": None, "btst_dte": None,
        "btst_strike": None, "btst_target": None, "btst_stop": None,
        "btst_recommended": None,
        # Exit signal data
        "exit_reason": None,
        "expected_move_1sd": None, "expected_move_pct": None,
        "reason": "",
    }
    
    try:
        t = yf.Ticker(SYMBOL); nf = t.fast_info
        spot = getattr(nf, "last_price", None)
        if not spot: spot = (t.info or {}).get("regularMarketPrice")
        if not spot: result["signal"] = "ERROR"; result["reason"] = "No spot data"; return result
        
        vt = yf.Ticker(VIX_SYMBOL); vf = vt.fast_info
        vix_val = getattr(vf, "last_price", None)
        
        hist = yf.download(SYMBOL, period="1y", interval="1d", progress=False, auto_adjust=False)
        if isinstance(hist.columns, pd.MultiIndex):
            cc = ("Close", SYMBOL) if ("Close", SYMBOL) in hist.columns else hist.columns[0]
        else:
            cc = "Close"
        closes = pd.Series(hist[cc]).dropna().values.tolist()
        
        # Previous close for gap detection
        prev_close = closes[-1] if len(closes) > 1 else None
        
        ema_200 = ema(closes, 200); ema_20 = ema(closes, 20); ema_50 = ema(closes, 50)
        rsi_14 = rsi(closes, 14)
        if not ema_200 or not spot: result["signal"] = "ERROR"; result["reason"] = "Cannot compute 200 EMA"; return result
        
        # ADX/DI
        adx_val = di_plus = di_minus = None
        if len(closes) >= 15:
            rc = closes[-15:]
            if isinstance(hist.columns, pd.MultiIndex):
                hc = ("High", SYMBOL) if ("High", SYMBOL) in hist.columns else None
                lc = ("Low", SYMBOL) if ("Low", SYMBOL) in hist.columns else None
            else:
                hc = "High" if "High" in hist.columns else None
                lc = "Low" if "Low" in hist.columns else None
            highs_raw = pd.Series(hist[hc]).dropna().values.tolist() if hc else [c*1.01 for c in closes]
            lows_raw = pd.Series(hist[lc]).dropna().values.tolist() if lc else [c*0.99 for c in closes]
            rh = highs_raw[-15:]; rl = lows_raw[-15:]
            dmp, dmm, trs = [], [], []
            for i in range(1, 15):
                trs.append(max(rh[i]-rl[i], abs(rh[i]-rc[i-1]), abs(rl[i]-rc[i-1])))
                dmp.append(max(rh[i]-rh[i-1], 0)); dmm.append(max(rl[i-1]-rl[i], 0))
            a14 = sum(trs)/len(trs) if trs else 1
            di_plus = round(sum(dmp)/len(dmp)/a14*100, 1) if dmp and a14>0 else 0
            di_minus = round(sum(dmm)/len(dmm)/a14*100, 1) if dmm and a14>0 else 0
            adx_val = round(abs(di_plus-di_minus)/max(di_plus+di_minus, 0.01)*100, 1)
        
        distance_pct = round((spot - ema_200) / ema_200 * 100, 2)
        
        # ── Expiry + Theta ──
        expiries = get_nifty_expiries()
        
        # ── Vol calculations ──
        ann_vol = (vix_val or 15) / 100
        daily_vol = ann_vol / math.sqrt(252)
        
        def setup_trade(direction, expiries):
            """Setup positional trade for given direction (long/short)."""
            strat = "buy" if direction == "long" else "sell"
            selected = select_expiry(expiries, strat)
            dte = selected["dte"]
            atm_strike = round(spot / 50) * 50
            
            period_vol = daily_vol * math.sqrt(max(dte, 1))
            exp_move_1sd = round(spot * period_vol, 1)
            exp_move_pct = round(period_vol * 100, 2)
            
            if direction == "long":
                entry_strike = atm_strike
                target_price = atm_strike + exp_move_1sd * 0.5
                target_strike = round(target_price / 50) * 50
                if target_strike <= entry_strike: target_strike = entry_strike + 50
                stop_level = round(ema_200 * 0.995 / 10) * 10
                trade_type = "Bull Call Spread"
                trade_desc = f"Buy {entry_strike} CE, Sell {target_strike} CE"
            else:  # short
                entry_strike = atm_strike
                target_price = atm_strike - exp_move_1sd * 0.5
                target_strike = round(target_price / 50) * 50
                if target_strike >= entry_strike: target_strike = entry_strike - 50
                stop_level = round(ema_200 * 1.005 / 10) * 10
                trade_type = "Bear Put Spread"
                trade_desc = f"Buy {entry_strike} PE, Sell {target_strike} PE"
            
            if dte > 15: theta_zone = "slow_decay"
            elif dte > 7: theta_zone = "moderate_decay"
            elif dte > 3: theta_zone = "fast_decay"
            else: theta_zone = "gamma_zone"
            
            return {
                "expiry": selected["display"], "expiry_type": selected["type"],
                "dte": dte, "theta_zone": theta_zone, "atm_strike": atm_strike,
                "trade_desc": trade_desc, "trade_type": trade_type,
                "entry_strike": entry_strike, "target_strike": target_strike,
                "stop_level": stop_level,
                "expected_move_1sd": exp_move_1sd, "expected_move_pct": exp_move_pct,
                "action": (f"{trade_type}: {trade_desc} | Expiry: {selected['display']} ({dte}DTE) | "
                          f"Stop: {stop_level} | Expected ±{exp_move_pct}%")
            }
        
        # ── BTST setup ──
        def setup_btst(direction):
            btst_exp = select_btst_expiry(expiries)
            btst_dte = btst_exp["dte"]
            atm_strike = round(spot / 50) * 50
            btst_vol = daily_vol * math.sqrt(2)
            btst_move = round(spot * btst_vol, 1)
            btst_move_pct = round(btst_vol * 100, 2)
            
            if direction == "long":
                target_price = atm_strike + btst_move * 0.8
                target_strike = round(target_price / 50) * 50
                if target_strike <= atm_strike: target_strike = atm_strike + 50
                stop = round((spot - btst_move * 0.5) / 10) * 10
                return (btst_exp["display"], btst_dte, atm_strike, target_strike, stop,
                       f"BTST Long: Buy {atm_strike} CE | {btst_exp['display']} ({btst_dte}DTE) | "
                       f"Target: {target_strike} | Stop: {stop} | ±{btst_move_pct}%")
            else:
                target_price = atm_strike - btst_move * 0.8
                target_strike = round(target_price / 50) * 50
                if target_strike >= atm_strike: target_strike = atm_strike - 50
                stop = round((spot + btst_move * 0.5) / 10) * 10
                return (btst_exp["display"], btst_dte, atm_strike, target_strike, stop,
                       f"BTST Short: Buy {atm_strike} PE | {btst_exp['display']} ({btst_dte}DTE) | "
                       f"Target: {target_strike} | Stop: {stop} | ±{btst_move_pct}%")
        
        # ── Fill basic fields ──
        result.update({
            "spot": round(spot, 2), "ema_200": round(ema_200, 2),
            "ema_20": round(ema_20, 2) if ema_20 else None,
            "ema_50": round(ema_50, 2) if ema_50 else None,
            "distance_pct": distance_pct,
            "adx": adx_val, "di_plus": di_plus, "di_minus": di_minus,
            "rsi_14": round(rsi_14, 1) if rsi_14 else None,
            "vix": round(vix_val, 2) if vix_val else None,
            "prev_close": round(prev_close, 2) if prev_close else None,
        })
        
        # ── Signal Logic: EXIT checks first ──
        
        # EXIT LONGS: trend broken below 200 EMA
        if distance_pct < BROKEN_BELOW_PCT and adx_val and adx_val > MIN_ADX:
            result["signal"] = "EXIT_LONGS"
            result["exit_reason"] = f"Nifty closed {abs(distance_pct)}% below 200 EMA ({ema_200:.0f}). Uptrend broken. Exit all long positions."
            result["action"] = "Close all call positions immediately. Do not re-enter until 200 EMA reclaim."
            result["trade_direction"] = "exit"
        
        # EXIT LONGS: trend weakening
        if distance_pct > 0 and adx_val and adx_val < ADX_WEAKENING and di_plus and di_minus and di_plus < di_minus:
            result["signal"] = "EXIT_LONGS"
            result["exit_reason"] = f"ADX dropped to {adx_val} (below {ADX_WEAKENING}) and DI+ < DI-. Trend exhausted. Exit longs."
            result["action"] = "Close call positions. Trend has weakened — wait for fresh signal."
            result["trade_direction"] = "exit"
        
        # EXIT SHORTS: reclaimed above 200 EMA
        if distance_pct > BROKEN_ABOVE_PCT and adx_val and adx_val > MIN_ADX and di_plus and di_minus and di_plus > di_minus:
            result["signal"] = "EXIT_SHORTS"
            result["exit_reason"] = f"Nifty reclaimed {distance_pct}% above 200 EMA with DI+ > DI-. Short trade invalid. Exit puts."
            result["action"] = "Close all put positions. Bullish trend resuming."
            result["trade_direction"] = "exit"
        
        # ── Signal Logic: ENTRY ──
        
        # BUY CALLS: bounce off 200 EMA with bullish trend
        in_entry_zone_long = 0 < distance_pct <= ENTRY_ZONE_PCT
        trend_bullish = adx_val and adx_val > MIN_ADX and di_plus and di_minus and di_plus > di_minus
        rsi_ok_long = rsi_14 and rsi_14 < MAX_RSI
        ema_stack_bullish = ema_20 and ema_50 and ema_20 > ema_50 and spot > ema_20
        
        if in_entry_zone_long and trend_bullish and rsi_ok_long and ema_stack_bullish:
            trade = setup_trade("long", expiries)
            btst = setup_btst("long")
            result["signal"] = "BUY_CALLS"
            result["trade_direction"] = "long"
            result.update({
                "selected_expiry": trade["expiry"], "expiry_type": trade["expiry_type"],
                "dte": trade["dte"], "theta_zone": trade["theta_zone"],
                "atm_strike": trade["atm_strike"],
                "recommended_trade": (
                    f"{trade['trade_type']}: {trade['trade_desc']} | "
                    f"Expiry: {trade['expiry']} ({trade['expiry_type']}, {trade['dte']} DTE) | "
                    f"Max profit if Nifty {'above' if 'Call' in trade['trade_type'] else 'below'} {trade['target_strike']} | "
                    f"Expected 1σ: ±{trade['expected_move_pct']}%"
                ),
                "entry_strike": trade["entry_strike"], "target_strike": trade["target_strike"],
                "stop_level": trade["stop_level"],
                "expected_move_1sd": trade["expected_move_1sd"],
                "expected_move_pct": trade["expected_move_pct"],
                "btst_expiry": btst[0], "btst_dte": btst[1],
                "btst_strike": btst[2], "btst_target": btst[3], "btst_stop": btst[4],
                "btst_recommended": btst[5],
                "action": trade["action"],
                "reason": (
                    f"200 EMA bounce + bullish trend. {trade['expiry_type']} {trade['expiry']} ({trade['dte']}DTE). "
                    f"Spot {spot:.0f} at {distance_pct}% > 200 EMA. ADX {adx_val}, DI+ {di_plus} > DI- {di_minus}."
                ),
            })
        
        # BUY PUTS: breakdown below 200 EMA with bearish trend
        in_entry_zone_short = -ENTRY_ZONE_PCT <= distance_pct < 0
        trend_bearish = adx_val and adx_val > MIN_ADX and di_plus and di_minus and di_minus > di_plus
        rsi_ok_short = rsi_14 and rsi_14 > MIN_RSI
        
        if in_entry_zone_short and trend_bearish and rsi_ok_short:
            trade = setup_trade("short", expiries)
            btst = setup_btst("short")
            result["signal"] = "BUY_PUTS"
            result["trade_direction"] = "short"
            result.update({
                "selected_expiry": trade["expiry"], "expiry_type": trade["expiry_type"],
                "dte": trade["dte"], "theta_zone": trade["theta_zone"],
                "atm_strike": trade["atm_strike"],
                "recommended_trade": (
                    f"{trade['trade_type']}: {trade['trade_desc']} | "
                    f"Expiry: {trade['expiry']} ({trade['expiry_type']}, {trade['dte']} DTE) | "
                    f"Max profit if Nifty below {trade['target_strike']} | "
                    f"Expected 1σ: ±{trade['expected_move_pct']}%"
                ),
                "entry_strike": trade["entry_strike"], "target_strike": trade["target_strike"],
                "stop_level": trade["stop_level"],
                "expected_move_1sd": trade["expected_move_1sd"],
                "expected_move_pct": trade["expected_move_pct"],
                "btst_expiry": btst[0], "btst_dte": btst[1],
                "btst_strike": btst[2], "btst_target": btst[3], "btst_stop": btst[4],
                "btst_recommended": btst[5],
                "action": trade["action"],
                "reason": (
                    f"200 EMA breakdown + bearish trend. {trade['expiry_type']} {trade['expiry']} ({trade['dte']}DTE). "
                    f"Spot {spot:.0f} at {distance_pct}% < 200 EMA. ADX {adx_val}, DI- {di_minus} > DI+ {di_plus}."
                ),
            })
        
        # ── WAIT states ──
        if result["signal"] == "STAND_ASIDE":
            if adx_val and adx_val < ADX_WEAKENING:
                result["reason"] = f"ADX {adx_val} below {ADX_WEAKENING} — market is ranging. No directional trade."
            elif in_entry_zone_long and not trend_bullish:
                result["reason"] = f"At 200 EMA but trend not bullish (DI+={di_plus}, DI-={di_minus})"
            elif in_entry_zone_short and not trend_bearish:
                result["reason"] = f"Below 200 EMA but trend not bearish (DI+={di_plus}, DI-={di_minus})"
            elif distance_pct > ENTRY_ZONE_PCT:
                result["reason"] = f"Above entry zone ({distance_pct}% > 200 EMA). Wait for pullback to {ema_200:.0f}."
                result["action"] = f"Long entry zone: {ema_200:.0f} to {ema_200*1.005:.0f}"
            elif distance_pct < -ENTRY_ZONE_PCT:
                result["reason"] = f"Well below 200 EMA ({distance_pct}%). Wait for reclaim or fresh breakdown signal."
            else:
                result["reason"] = "Monitoring — no clear entry or exit signal"
    
    except Exception as e:
        result["signal"] = "ERROR"
        result["reason"] = str(e)
    
    # ── Enrich with Upstox option chain if token available ──
    try:
        import importlib.util
        token = os.environ.get("UPSTOX_TOKEN", "")
        if not token:
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".openclaw", "tmp", "upstox_config.py")
            if os.path.exists(config_path):
                spec = importlib.util.spec_from_file_location("upstox_config", config_path)
                upstox_cfg = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(upstox_cfg)
                token = getattr(upstox_cfg, "UPSTOX_ACCESS_TOKEN", "")
        
        # Debug
        if not token:
            result["option_chain_source"] = "no_token"
        elif not result.get("selected_expiry"):
            result["option_chain_source"] = "no_expiry"
        else:
            enriched = enrich_from_upstox(result, token)
            if enriched:
                if enriched.get("chain_spot"):
                    result["spot"] = enriched["chain_spot"]
                result.update(enriched)
                
                # ── PCR Reversal (Contrarian) Signal ──
                pcr = enriched.get("weekly_pcr") or enriched.get("oi_pcr")  # Prefer weekly
                if pcr is not None:
                    if pcr < 0.7:
                        result["contrarian_signal"] = "SELL_CALLS"
                        result["contrarian_reason"] = f"PCR={pcr} — excessive call buying (euphoria). Fade the crowd."
                    elif pcr > 1.4:
                        result["contrarian_signal"] = "SELL_PUTS"
                        result["contrarian_reason"] = f"PCR={pcr} — excessive put buying (panic). Fade the crowd."
                    else:
                        result["contrarian_signal"] = "NEUTRAL"
                        result["contrarian_reason"] = f"PCR={pcr} — balanced positioning, no contrarian edge."
            else:
                result["option_chain_source"] = "enrich_returned_none"
    except Exception as e:
        pass  # Non-critical — main signal still works
    
    return result


def _vix_sizing_multiplier(vix):
    """Scale position size by VIX. Low VIX = full size, high VIX = reduce."""
    if not vix or vix <= 0: return 1.0
    if vix < 12: return 1.0     # Low fear — full size
    if vix < 16: return 1.0     # Normal — full size
    if vix < 20: return 0.75    # Elevated — reduce 25%
    if vix < 25: return 0.5     # High — cut in half
    return 0.25                  # Extreme — minimal exposure


def enrich_from_upstox(result, token):
    """Fetch real OI/PCR/IV data from Upstox and merge into result."""
    try:
        import requests as req
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        expiry_display = result.get("selected_expiry", "")
        
        # Convert DD-Mon-YYYY to YYYY-MM-DD for Upstox API
        try:
            expiry_dt = datetime.strptime(expiry_display, "%d-%b-%Y")
            expiry_api = expiry_dt.strftime("%Y-%m-%d")
        except ValueError:
            expiry_api = expiry_display  # already in YYYY-MM-DD?
        
        resp = req.get(
            "https://api.upstox.com/v2/option/chain",
            headers=headers,
            params={"instrument_key": "NSE_INDEX|Nifty 50", "expiry_date": expiry_api},
            timeout=15
        )
        if resp.status_code != 200:
            return None
        
        data = resp.json().get("data", [])
        if not data:
            return None
        
        tco = tpo = tco_chg = tpo_chg = tcv = tpv = 0
        atm_iv = None
        all_ivs = []
        spot = result.get("spot")
        atm_strike = round(spot / 50) * 50 if spot else None
        mp_strike = None
        mp_oi = 0
        
        for item in data:
            ce = item.get("call_options", {})
            pe = item.get("put_options", {})
            s = item.get("strike_price", 0)
            
            # Upstox nests market data inside market_data key
            ce_md = ce.get("market_data", {}) if ce else {}
            pe_md = pe.get("market_data", {}) if pe else {}
            ce_gr = ce.get("option_greeks", {}) if ce else {}
            pe_gr = pe.get("option_greeks", {}) if pe else {}
            
            if ce_md:
                oi = ce_md.get("oi", 0) or 0
                prev_oi = ce_md.get("prev_oi", 0) or 0
                tco += oi
                tco_chg += (oi - prev_oi)
                tcv += ce_md.get("volume", 0) or 0
                iv = ce_gr.get("iv", ce_gr.get("implied_volatility", 0)) or 0
                if iv > 0: all_ivs.append(iv)
                if s == atm_strike: atm_iv = iv
                if oi > mp_oi: mp_oi = oi; mp_strike = s
            
            if pe_md:
                oi = pe_md.get("oi", 0) or 0
                prev_oi = pe_md.get("prev_oi", 0) or 0
                tpo += oi
                tpo_chg += (oi - prev_oi)
                tpv += pe_md.get("volume", 0) or 0
                iv = pe_gr.get("iv", pe_gr.get("implied_volatility", 0)) or 0
                if iv > 0: all_ivs.append(iv)
                if s == atm_strike and atm_iv is None: atm_iv = iv
                if oi > mp_oi: mp_oi = oi; mp_strike = s
        
        # Also get spot from the chain data
        chain_spot = None
        if data:
            chain_spot = data[0].get("underlying_spot_price")
        
        # Look up premiums for recommended strikes
        entry_strike = result.get("entry_strike")
        target_strike = result.get("target_strike")
        btst_strike = result.get("btst_strike")
        
        entry_premium = None; target_premium = None; btst_premium = None
        entry_delta = None
        for item in data:
            s = item.get("strike_price", 0)
            if s == entry_strike:
                md = item.get("call_options", {}).get("market_data", {})
                gr = item.get("call_options", {}).get("option_greeks", {})
                entry_premium = md.get("ltp")
                entry_delta = gr.get("delta")
            if s == target_strike:
                md = item.get("call_options", {}).get("market_data", {})
                target_premium = md.get("ltp")
        
        # ── BTST premium from WEEKLY expiry (separate chain) ──
        btst_expiry_display = result.get("btst_expiry")
        weekly_pcr = None; weekly_spot = None
        if btst_expiry_display and btst_strike:
            try:
                btst_expiry_dt = datetime.strptime(btst_expiry_display, "%d-%b-%Y")
                btst_expiry_api = btst_expiry_dt.strftime("%Y-%m-%d")
                btst_resp = req.get(
                    "https://api.upstox.com/v2/option/chain",
                    headers=headers,
                    params={"instrument_key": "NSE_INDEX|Nifty 50", "expiry_date": btst_expiry_api},
                    timeout=10
                )
                if btst_resp.status_code == 200:
                    btst_data = btst_resp.json().get("data", [])
                    # BTST premium
                    for item in btst_data:
                        if item.get("strike_price") == btst_strike:
                            btst_premium = item.get("call_options", {}).get("market_data", {}).get("ltp")
                            break
                    # Weekly PCR (near-term sentiment)
                    wco = sum((it.get("call_options", {}).get("market_data", {}).get("oi", 0) or 0) for it in btst_data)
                    wpo = sum((it.get("put_options", {}).get("market_data", {}).get("oi", 0) or 0) for it in btst_data)
                    weekly_pcr = round(wpo / wco, 3) if wco > 0 else None
                    weekly_spot = btst_data[0].get("underlying_spot_price") if btst_data else None
            except:
                pass
        
        # Net debit for spread (entry - target)
        net_debit = None
        if entry_premium is not None and target_premium is not None:
            net_debit = round(entry_premium - target_premium, 2)
        
        return {
            "oi_pcr": round(tpo / tco, 3) if tco > 0 else None,
            "vol_pcr": round(tpv / tcv, 3) if tcv > 0 else None,
            "total_call_oi": tco,
            "total_put_oi": tpo,
            "call_oi_change": tco_chg,
            "put_oi_change": tpo_chg,
            "atm_iv": round(atm_iv, 2) if atm_iv else None,
            "iv_mean": round(sum(all_ivs) / len(all_ivs), 2) if all_ivs else None,
            "max_pain_estimate": mp_strike,
            "chain_spot": chain_spot,
            "entry_premium": entry_premium,
            "target_premium": target_premium,
            "net_debit": net_debit,
            "btst_premium": btst_premium,
            # Weekly PCR (near-term sentiment, more OI-intensive)
            "weekly_pcr": weekly_pcr,
            # Real delta from Upstox (not hardcoded 0.5)
            "entry_delta": round(entry_delta, 3) if entry_delta else None,
            # VIX-adjusted sizing multiplier
            "vix_level": result.get("vix", 0),
            "vix_multiplier": round(_vix_sizing_multiplier(result.get("vix", 0)), 2),
            # Trailing stop
            "trail_stop": round(chain_spot * 0.995, 1) if chain_spot else None,
            "trail_pct": 0.5,
            "option_chain_source": "Upstox API",
        }
    except Exception:
        return None


if __name__ == "__main__":
    r = main()
    print(json.dumps(r, indent=2))
    
    exits = {"BUY_CALLS": 10, "BUY_PUTS": 11, "EXIT_LONGS": 20, "EXIT_SHORTS": 21, "STAND_ASIDE": 30}
    sys.exit(exits.get(r["signal"], 0))
