#!/usr/bin/env python3
"""
Nifty Signal API Server — Flask backend for the mobile dashboard
Serves the analysis pipeline as a REST API + hosts the PWA frontend.
Run this on the Mac, access from mobile via local network.
"""

import json, math, sys, os, time, subprocess
from datetime import datetime
from flask import Flask, jsonify, send_from_directory, request
import warnings
warnings.filterwarnings("ignore")

from trade_journal import add_trade, update_trade, get_all
from algo_trader import get_algo_status, toggle_live_mode, toggle_strategy, execute_trade, track_paper_entry, track_paper_exit, track_paper_exit_all

app = Flask(__name__, static_folder="pwa_static", static_url_path="")

PORT = int(os.environ.get("PORT", 5099))
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
IS_CLOUD = os.environ.get("RENDER", "") == "true" or os.environ.get("RAILWAY", "") == "true"
VENV_PYTHON = sys.executable if IS_CLOUD else os.path.join(WORKSPACE, ".openclaw/tmp/venv/bin/python")

# Cache
_last_signal = None
_last_full = None
_last_update = 0
CACHE_TTL = 60  # seconds

def run_script(script_name):
    """Run a Python script and return parsed JSON."""
    if IS_CLOUD:
        return _run_script_import(script_name)
    return _run_script_subprocess(script_name)

def _run_script_import(script_name):
    """Import module and call main() directly (no subprocess, works on Render)."""
    try:
        mod_name = script_name.replace(".py", "")
        mod = __import__(mod_name)
        result = mod.main()
        return result if isinstance(result, dict) else {"error": f"Bad return"}
    except Exception as e:
        return {"error": f"Import error: {str(e)}"}

def _run_script_subprocess(script_name):
    """Run script via subprocess with venv Python (local Mac)."""
    try:
        script_path = os.path.join(WORKSPACE, script_name)
        proc = subprocess.run(
            [VENV_PYTHON, script_path],
            capture_output=True, text=True, timeout=60, cwd=WORKSPACE,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        lines = stdout.split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        if stdout:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                pass
        return {"error": f"No JSON in output", "stdout": stdout[:200], "stderr": stderr[:200]}
    except subprocess.TimeoutExpired:
        return {"error": "Script timed out (60s)"}
    except Exception as e:
        return {"error": str(e)}

def get_signal():
    """Get cached or fresh signal."""
    global _last_signal, _last_update
    now = time.time()
    if _last_signal and (now - _last_update) < CACHE_TTL:
        return _last_signal
    _last_signal = run_script("nifty_monitor.py")
    _last_update = now
    return _last_signal

def get_full_analysis():
    """Get cached or fresh full analysis."""
    global _last_full, _last_update
    now = time.time()
    if _last_full and (now - _last_update) < CACHE_TTL:
        return _last_full
    _last_full = run_script("nifty_pipeline_v2.py")
    _last_update = now
    return _last_full


# ── API Routes ──

@app.route("/api/signal")
def api_signal():
    signal = get_signal()
    emoji = {"BUY_CALLS": "🟢", "BUY_PUTS": "🔴", "WAIT": "🟡", "STAND_ASIDE": "🔴", "ERROR": "⚪"}
    
    # Auto-track paper positions when entry/exit signals fire
    try:
        sig_name = signal.get("signal", "")
        if sig_name in ("BUY_CALLS", "BUY_PUTS"):
            direction = "BUY" if sig_name == "BUY_CALLS" else "SELL"
            strike = signal.get("entry_strike", 0)
            premium = signal.get("entry_premium") or 0
            # Check if we already have an active position
            from algo_trader import load_state
            st = load_state()
            existing = [p for p in st.get("active_positions", []) if p.get("direction") == direction and p.get("signal_type","") == "ema_bounce"]
            if not existing:
                pos = track_paper_entry("ema_bounce", direction, strike, 1, premium)
                signal["paper_entry"] = pos
        elif sig_name in ("EXIT_LONGS", "EXIT_SHORTS"):
            current_premium = signal.get("entry_premium") or signal.get("btst_premium") or 0
            results = track_paper_exit_all(current_premium, "long" if sig_name == "EXIT_LONGS" else "short")
            if results:
                signal["paper_exit"] = {"count": len(results), "total_pnl": sum(r["pnl"] for r in results)}
    except Exception:
        pass  # Non-critical
    
    return jsonify({
        **signal,
        "emoji": emoji.get(sig_name, "⚪"),
        "updated": datetime.now().strftime("%H:%M:%S"),
    })

@app.route("/api/full")
def api_full():
    """Full 15-step pipeline (expensive — cached 60s)."""
    return jsonify(get_full_analysis())

@app.route("/api/summary")
def api_summary():
    """Lightweight summary from the full analysis."""
    full = get_full_analysis()
    exec_summary = full.get("15_executive_summary", {})
    regime = full.get("12_market_regime", {})
    scenario = full.get("14_scenario_analysis", {})
    
    return jsonify({
        "symbol": exec_summary.get("symbol"),
        "spot": exec_summary.get("spot"),
        "change_pct": exec_summary.get("change_pct"),
        "trend": exec_summary.get("trend"),
        "adx": exec_summary.get("adx"),
        "rsi": exec_summary.get("rsi_14"),
        "vix": exec_summary.get("india_vix"),
        "vix_regime": exec_summary.get("vix_regime"),
        "regime": regime.get("label"),
        "regime_confidence": regime.get("confidence"),
        "transition": regime.get("transition_state"),
        "option_bias": exec_summary.get("option_bias"),
        "preferred_strategy": exec_summary.get("preferred_strategy"),
        "scenario_probs": exec_summary.get("scenario_probabilities"),
        "theta_zone": exec_summary.get("theta_zone"),
        "expected_move": exec_summary.get("expected_1sd_move"),
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    })

@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


# ── ORB Scalp ──

@app.route("/api/orb")
def api_orb():
    """Opening Range Breakout signal. Only valid 9:30-10:15 AM IST."""
    return jsonify(run_script("orb_scalp.py"))


@app.route("/api/intraday")
def api_intraday():
    """VWAP + EMA intraday signals. Valid during market hours."""
    return jsonify(run_script("intraday_signals.py"))


# ── Algo Trading ──

@app.route("/api/algo/status")
def api_algo_status():
    return jsonify(get_algo_status())

@app.route("/api/algo/toggle", methods=["POST"])
def api_algo_toggle():
    data = request.get_json() or {}
    enable = data.get("enable", False)
    confirm = data.get("confirm")
    return jsonify(toggle_live_mode(enable, confirm))

@app.route("/api/algo/strategy", methods=["POST"])
def api_algo_strategy():
    data = request.get_json() or {}
    name = data.get("strategy", "")
    enable = data.get("enable", False)
    return jsonify(toggle_strategy(name, enable))


# ── Position Sizing ──

@app.route("/api/position-size")
def api_position_size():
    """Calculate position size based on capital and risk.
    Query params: capital (total trading capital), risk_pct (risk per trade %)
    Uses current signal's stop_level and entry_strike."""
    try:
        capital = float(request.args.get("capital", 100000))
        risk_pct = float(request.args.get("risk_pct", 2))
    except ValueError:
        return jsonify({"error": "Invalid capital or risk_pct"}), 400
    
    signal = get_signal()
    spot = signal.get("spot", 0)
    stop_level = signal.get("stop_level", 0)
    entry_premium = signal.get("entry_premium") or signal.get("btst_premium") or 0
    delta = signal.get("entry_delta") or 0.5  # Real delta from Upstox
    vix = signal.get("vix_level", 0)
    vix_mult = signal.get("vix_multiplier", 1.0)
    prev_close = signal.get("prev_close")
    
    if not stop_level or not spot:
        return jsonify({"error": "No stop loss or spot price available", "lots": 0})
    
    # ── Gap Check ──
    gap_pct = 0
    gap_warning = None
    if prev_close and spot:
        gap_pct = round((spot - prev_close) / prev_close * 100, 2)
        if abs(gap_pct) > 0.5:
            direction = "up" if gap_pct > 0 else "down"
            gap_warning = f"Gap {direction} {abs(gap_pct)}% — widen stops or stand aside"
            # Widen stop by gap amount for gap-down on longs
            if gap_pct < 0 and signal.get("trade_direction") == "long":
                pass  # Keep original stop but warn
    
    risk_amount = capital * (risk_pct / 100)
    stop_distance = abs(spot - stop_level)
    stop_pct = round(stop_distance / spot * 100, 2)
    
    # Option risk using REAL delta from Upstox
    option_move = stop_distance * (delta or 0.5)
    option_risk_per_lot = round(option_move * 65, 2)
    
    # Capital required to buy 1 lot
    capital_per_lot = round((entry_premium or 0) * 65, 2)
    
    # Max lots by risk
    if option_risk_per_lot > 0:
        lots_by_risk = int(risk_amount / option_risk_per_lot)
    else:
        lots_by_risk = 0
    
    # Apply VIX sizing multiplier
    if vix_mult < 1.0:
        lots_by_risk = int(lots_by_risk * vix_mult)
    
    # Max lots by capital
    if capital_per_lot > 0:
        lots_by_capital = int(capital / capital_per_lot)
    else:
        lots_by_capital = 0
    
    lots = min(lots_by_risk, lots_by_capital, 36)  # NSE cap = 36
    lots = max(0, lots)
    
    capital_at_risk = round(lots * option_risk_per_lot, 2)
    capital_required = round(lots * capital_per_lot, 2)
    
    return jsonify({
        "capital": capital,
        "risk_pct": risk_pct,
        "risk_amount": round(risk_amount, 2),
        "spot": spot,
        "stop_level": stop_level,
        "stop_distance_pts": round(stop_distance, 1),
        "stop_distance_pct": stop_pct,
        "entry_premium": entry_premium,
        "delta": delta,
        "delta_source": "Upstox" if signal.get("entry_delta") else "estimated",
        "option_move_pts": round(option_move, 1),
        "option_risk_per_lot": option_risk_per_lot,
        "capital_per_lot": capital_per_lot,
        "lots": lots,
        "lots_by_risk": lots_by_risk,
        "lots_by_capital": lots_by_capital,
        "capital_required": capital_required,
        "capital_at_risk": capital_at_risk,
        "capital_at_risk_pct": round(capital_at_risk / capital * 100, 2) if capital else 0,
        "vix_level": vix,
        "vix_multiplier": vix_mult,
        "gap_pct": gap_pct,
        "gap_warning": gap_warning,
    })


# ── Trade Journal ──

@app.route("/api/journal", methods=["GET", "POST"])
def api_journal():
    """GET: list all trades + stats. POST: add a new trade."""
    if request.method == "GET":
        data = get_all()
        return jsonify(data)
    
    if request.method == "POST":
        try:
            trade = request.get_json()
            if not trade:
                return jsonify({"error": "No JSON body"}), 400
            result = add_trade(trade)
            return jsonify(result), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400


@app.route("/api/journal/<int:trade_id>", methods=["PATCH"])
def api_journal_update(trade_id):
    """Update a trade (e.g., close position with exit_price)."""
    try:
        updates = request.get_json()
        if not updates:
            return jsonify({"error": "No JSON body"}), 400
        result = update_trade(trade_id, updates)
        if result:
            return jsonify(result)
        return jsonify({"error": "Trade not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/journal/stats")
def api_journal_stats():
    """Get aggregate trading statistics."""
    data = get_all()
    return jsonify(data.get("stats", {}))


# ── Tunnel URL ──

_tunnel_url = None
TUNNEL_FILE = os.path.join(WORKSPACE, ".openclaw", "tmp", "tunnel_url.txt")

@app.route("/api/tunnel")
def api_tunnel():
    """Return the current Cloudflare tunnel URL."""
    global _tunnel_url
    if _tunnel_url:
        return jsonify({"url": _tunnel_url, "status": "active"})
    # Try reading from file
    if os.path.exists(TUNNEL_FILE):
        with open(TUNNEL_FILE) as f:
            saved = f.read().strip()
        if saved:
            return jsonify({"url": saved, "status": "saved"})
    return jsonify({"url": None, "status": "not_found"})


def detect_tunnel_url():
    """Find the active cloudflared tunnel URL."""
    global _tunnel_url
    try:
        result = subprocess.run(
            ["pgrep", "-fl", "cloudflared"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().split("\n"):
            if "http://localhost:" + str(PORT) in line or "--url" in line:
                # Extract URL from cloudflared output: try common patterns
                pass
        
        # Alternative: check recent cloudflared logs
        import glob
        log_files = glob.glob(os.path.expanduser("~/.cloudflared/*.log"))
        for lf in sorted(log_files, key=os.path.getmtime, reverse=True)[:3]:
            try:
                with open(lf) as f:
                    for line in f:
                        if "trycloudflare.com" in line and "https://" in line:
                            import re
                            match = re.search(r'(https://[a-z0-9-]+\.trycloudflare\.com)', line)
                            if match:
                                _tunnel_url = match.group(1)
                                # Save for dashboard
                                os.makedirs(os.path.dirname(TUNNEL_FILE), exist_ok=True)
                                with open(TUNNEL_FILE, "w") as tf:
                                    tf.write(_tunnel_url)
                                return _tunnel_url
            except:
                continue
    except:
        pass
    return None


# ── Background Alert Scheduler ──

import threading
from datetime import datetime, time as dtime
import pytz

_alert_log = []  # Store recent alerts for the dashboard
ALERT_LOG_FILE = os.path.join(WORKSPACE, ".openclaw", "tmp", "alerts.json")
ALERT_MAX = 50

def _save_alerts():
    try:
        os.makedirs(os.path.dirname(ALERT_LOG_FILE), exist_ok=True)
        with open(ALERT_LOG_FILE, "w") as f:
            json.dump(_alert_log[-ALERT_MAX:], f, default=str)
    except:
        pass

def _add_alert(level, title, body):
    alert = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "level": level,  # info, warning, critical
        "title": title,
        "body": body,
    }
    _alert_log.append(alert)
    if len(_alert_log) > ALERT_MAX:
        _alert_log.pop(0)
    _save_alerts()
    print(f"[ALERT {level.upper()}] {title}: {body[:100]}")

@app.route("/api/alerts")
def api_alerts():
    """Recent alerts from the background scheduler."""
    return jsonify(_alert_log[-20:])

def _is_market_open():
    """Check if NSE is open now (Mon-Fri, 9:15-15:30 IST)."""
    try:
        tz = pytz.timezone("Asia/Kolkata")
        now = datetime.now(tz)
        if now.weekday() >= 5:
            return False
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_open <= now <= market_close
    except:
        return True  # Fallback

def alert_scheduler():
    """Background thread: checks every 30s and fires alerts for ALL strategies."""
    last_premarket_date = None
    last_monitor_minute = None
    last_btst_date = None
    last_orb_check = None
    last_intraday_check = None
    
    while True:
        try:
            tz = pytz.timezone("Asia/Kolkata")
            now = datetime.now(tz)
            today = now.date()
            current_minute = now.strftime("%H:%M")
            
            if now.weekday() >= 5:  # Weekend
                time.sleep(60)
                continue
            
            in_market = _is_market_open()
            
            # ── Pre-market brief at 9:00 AM ──
            if current_minute == "09:00" and last_premarket_date != today:
                last_premarket_date = today
                try:
                    sig = get_signal()
                    spot = sig.get("spot", "N/A")
                    vix = sig.get("vix", "N/A")
                    pcr = sig.get("oi_pcr", "N/A")
                    signal = sig.get("signal", "N/A")
                    cs = sig.get("contrarian_signal", "")
                    cont_msg = f" | Contrarian: {cs}" if cs and cs != "NEUTRAL" else ""
                    _add_alert("info", "📅 Pre-Market Brief",
                        f"Nifty: {spot} | VIX: {vix} | PCR: {pcr} | Signal: {signal}{cont_msg} | "
                        f"200 EMA: {sig.get('ema_200', 'N/A')} | Stop: {sig.get('stop_level', 'N/A')}")
                except Exception as e:
                    _add_alert("warning", "Pre-Market Brief Failed", str(e)[:200])
            
            # ── 15-min EMA Entry/Exit Monitor ──
            if in_market and current_minute.endswith(("00", "15", "30", "45")) and last_monitor_minute != current_minute:
                last_monitor_minute = current_minute
                try:
                    sig = get_signal()
                    signal = sig.get("signal", "")
                    if signal in ("BUY_CALLS", "BUY_PUTS"):
                        _add_alert("critical", f"🔴 {signal} — 200 EMA",
                            f"Spot: {sig.get('spot')} | ADX: {sig.get('adx')} | "
                            f"PCR: {sig.get('oi_pcr')} | IV: {sig.get('atm_iv')}% | "
                            f"Trade: {sig.get('recommended_trade', '')[:100]}")
                    elif signal in ("EXIT_LONGS", "EXIT_SHORTS"):
                        _add_alert("critical", f"⚠️ {signal}", sig.get("exit_reason", ""))
                    # Contrarian PCR check
                    cs = sig.get("contrarian_signal", "")
                    if cs in ("SELL_CALLS", "SELL_PUTS"):
                        _add_alert("critical", f"🔄 Contrarian: {cs}",
                            sig.get("contrarian_reason", ""))
                except Exception as e:
                    _add_alert("warning", "Monitor Check Failed", str(e)[:200])
            
            # ── ORB signal (9:30-10:15, every 2 min) ──
            orb_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
            orb_end = now.replace(hour=10, minute=15, second=0, microsecond=0)
            if orb_start <= now <= orb_end and last_orb_check != current_minute:
                last_orb_check = current_minute
                try:
                    orb = run_script("orb_scalp.py")
                    if orb.get("signal") in ("ORB_BUY", "ORB_SELL"):
                        _add_alert("critical", f"⚡ ORB: {orb['signal']}",
                            f"{orb.get('reason', '')} | Entry: {orb.get('entry_strike')} | "
                            f"Target: {orb.get('target_strike')} | Stop: {orb.get('stop_strike')}")
                except Exception as e:
                    pass
            
            # ── Intraday (VWAP + EMA) every 5 min ──
            if in_market and current_minute.endswith(("00", "05")) and last_intraday_check != current_minute:
                last_intraday_check = current_minute
                try:
                    intra = run_script("intraday_signals.py")
                    # VWAP
                    vwap = intra.get("vwap", {})
                    if vwap and vwap.get("signal") in ("VWAP_BUY", "VWAP_SELL"):
                        _add_alert("critical", f"📊 VWAP: {vwap['signal']}",
                            f"{vwap.get('reason', '')} | Spot: {vwap.get('spot')} | VWAP: {vwap.get('vwap')}")
                    # EMA crossover
                    ema = intra.get("ema", {})
                    if ema and ema.get("signal") in ("EMA_BUY", "EMA_SELL"):
                        _add_alert("critical", f"📈 EMA: {ema['signal']}",
                            f"{ema.get('reason', '')} | Spot: {ema.get('spot')} | "
                            f"EMA9: {ema.get('ema9')} | EMA21: {ema.get('ema21')}")
                except Exception as e:
                    pass
            
            # ── BTST close-out at 3:25 PM ──
            if current_minute == "15:25" and last_btst_date != today:
                last_btst_date = today
                try:
                    sig = get_signal()
                    if sig.get("btst_strike"):
                        _add_alert("critical", "⚡ BTST Close-Out — 5 min to market close!",
                            f"Exit {sig.get('btst_strike')} CE ({sig.get('btst_expiry')}) NOW. "
                            f"Spot: {sig.get('spot')} | Premium: ₹{sig.get('btst_premium', 'N/A')}")
                except Exception as e:
                    _add_alert("warning", "BTST Alert Failed", str(e)[:200])
            
            time.sleep(30)
        except Exception as e:
            print(f"[SCHEDULER ERROR] {e}")
            time.sleep(60)


# ── Paper Trading Heartbeat (keeps paper P&L tracking alive) ──

def paper_tracking_heartbeat():
    """Pings the signal endpoint every 60s to auto-trigger paper P&L."""
    import requests as req
    while True:
        try:
            if _is_market_open():
                req.get(f"http://localhost:{PORT}/api/signal", timeout=30)
            time.sleep(60)
        except:
            time.sleep(30)


# ── Serve PWA Frontend ──

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(app.static_folder, path)


if __name__ == "__main__":
    print(f"🚀 Nifty Signal Server starting on port {PORT}")
    print(f"   Local:   http://localhost:{PORT}")
    if not IS_CLOUD:
        print(f"   Mobile:  http://<mac-ip>:{PORT}")
    print(f"   API:     http://localhost:{PORT}/api/signal")
    
    if IS_CLOUD:
        print("   Mode:    ☁️  Cloud (no background scheduler)")
    else:
        tunnel = detect_tunnel_url()
        if tunnel:
            print(f"   Tunnel:  {tunnel}")
        scheduler = threading.Thread(target=alert_scheduler, daemon=True)
        scheduler.start()
        print("   Alerts:  Background scheduler started")
    
    # Always start paper tracking heartbeat
    pth = threading.Thread(target=paper_tracking_heartbeat, daemon=True)
    pth.start()
    print("   Paper:   Auto-tracking enabled")
    
    print()
    
    app.run(host="0.0.0.0", port=PORT, debug=False)
