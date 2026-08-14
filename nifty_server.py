#!/usr/bin/env python3
"""
Nifty Signal API Server — Flask backend for the mobile dashboard
Serves the analysis pipeline as a REST API + hosts the PWA frontend.
Run this on the Mac, access from mobile via local network.
"""

import json, math, sys, os, time, subprocess, threading
from datetime import datetime
from flask import Flask, jsonify, send_from_directory, request, Response
import warnings
warnings.filterwarnings("ignore")

from trade_journal import add_trade, update_trade, get_all
from algo_trader import get_algo_status, toggle_live_mode, toggle_strategy, execute_trade, track_paper_entry, track_paper_exit, track_paper_exit_all
from fii_dii import fiidii_summary
from tomorrow_outlook import get_outlook
from btc_monitor import get_btc_signal
from iv_rank import get_iv_rank
from backtest import get_backtest
from chain_table import get_chain
from telegram_alert import send_telegram, get_chat_id_from_updates, save_config, is_configured
import telegram_alert
from chart_data import get_chart_data
from banknifty_monitor import get_banknifty_signal
from sensex_monitor import get_sensex_signal
from expiry_countdown import get_expiry
from weekly_review import get_weekly_report, build_weekly_report
from oi_buildup import get_oi_buildup, take_snapshot
from gap_go import compute_gap_signal

app = Flask(__name__, static_folder="pwa_static", static_url_path="")
@app.before_request
def log_request():
    """Log every incoming request to /tmp/nifty_requests.log"""
    try:
        with open("/tmp/nifty_requests.log", "a") as f:
            f.write(f"{datetime.now().strftime('%H:%M:%S')} {request.remote_addr} {request.method} {request.path}\n")
    except:
        pass


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
    # In-process import everywhere: no subprocess cold-start (was ~60s per recompute).
    # Scripts must expose main() -> dict (all of ours do).
    return _run_script_import(script_name)

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
    # Single-flight lock: if another request is already recomputing, serve stale
    # data instead of stacking duplicate heavy computations.
    if not _signal_lock.acquire(blocking=False):
        if _last_signal:
            return _last_signal
        _signal_lock.acquire()
    try:
        _last_signal = run_script("nifty_monitor.py")
        _last_update = time.time()
    finally:
        _signal_lock.release()
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

_signal_cache = {"ts": 0, "data": None}
_btc_cache = {"ts": 0, "data": None}
_bnf_cache = {"ts": 0, "data": None}
_sensex_cache = {"ts": 0, "data": None}
_intraday_cache = {"ts": 0, "data": None}


def _clean_nan(obj):
    """Replace NaN/Inf floats with None so responses stay valid strict JSON (browsers reject literal NaN)."""
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return None
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nan(v) for v in obj]
    return obj
_last_tg_push = 0
_signal_lock = threading.Lock()
# ── Telegram queue: every alert is enqueued, batched sender flushes → nothing lost ──
_tg_queue = []
_tg_lock = threading.Lock()


def _push_tg(text):
    """Enqueue a Telegram message (batched sender flushes every ~20s)."""
    with _tg_lock:
        _tg_queue.append(text)
        if len(_tg_queue) > 50:  # hard cap — drop oldest if runaway
            _tg_queue.pop(0)


def tg_sender():
    """Background thread: drain queue → send batched Telegram messages.
    On the local Mac (non-cloud), checks the cloud instance first: if Render is
    awake, it pushes and we skip (one sender). If Render is down/sleeping,
    this instance takes over → no missed alerts."""
    while True:
        time.sleep(20)
        with _tg_lock:
            batch = _tg_queue[:8]
            del _tg_queue[:8]
        if not batch or not telegram_alert.is_configured():
            continue
        # Render is up → it handles the push (avoid duplicates) — UNLESS
        # MAC_FORCE_PUSH=1: used while Render runs older code that doesn't
        # generate the same alerts (e.g. multi-asset scalper); Mac then pushes
        # everything itself until Render is redeployed.
        if not IS_CLOUD and _render_alive() and not os.environ.get("MAC_FORCE_PUSH"):
            continue  # Render is up → it handles the push (avoid duplicates)
        try:
            msg = "\n\n".join(batch)
            if len(msg) > 3500:
                msg = msg[:3500] + "\n…"
            ok, err = telegram_alert.send_telegram(msg)
            print("[TG] sent {} msgs, ok={} err={}".format(len(batch), ok, err))
        except Exception as e:
            print("[TG] send failed:", e)

_asset_alerts = {}  # asset:date -> list of signal-change alerts
_asset_last_signal = {}  # asset -> last signal
_render_probe = {"ts": 0, "alive": False}
_algo_fired = {}  # signal_type -> "HH:MM" (dedup: at most one order per strategy per minute)


def _render_alive():
    """Is the Render cloud instance processing right now? (cached 45s)
    Fast answer (<7s) = scheduler running → it pushes. Slow/timeout = free-tier
    sleep or down → the local instance must push instead."""
    import time as _t
    now = _t.time()
    if now - _render_probe["ts"] < 45:
        return _render_probe["alive"]
    alive = False
    try:
        import urllib.request
        t0 = _t.time()
        with urllib.request.urlopen("https://nifty-signal-n684.onrender.com/api/health", timeout=7) as r:
            alive = r.status == 200 and (_t.time() - t0) < 7.0
    except Exception:
        alive = False
    _render_probe.update({"ts": now, "alive": alive})
    return alive


def _algo_trade(signal_type, direction, strike, expiry, lots, premium, option_type, reason=""):
    """Feed a signal into the algo engine (paper order now; real order when live).
    Dedup per strategy per minute; pushes the order to Telegram; logs failures."""
    try:
        from algo_trader import execute_trade
        now_hm = datetime.now().strftime("%H:%M")
        if _algo_fired.get(signal_type) == now_hm:
            return None
        _algo_fired[signal_type] = now_hm
        res = execute_trade(signal_type, direction, strike, expiry, lots, premium, option_type)
        status = res.get("status")
        if status in ("dry_run", "live"):
            order = res.get("order", {})
            if telegram_alert.is_configured():
                mode = "DRY RUN" if status == "dry_run" else "LIVE"
                _push_tg("🤖 <b>{} {}: {} {} {} {}</b>\nPremium ₹{} | {} lot(s) | {}".format(
                    mode, signal_type.upper(), direction, int(strike) if strike else "--",
                    option_type, expiry or "", premium or 0, lots, reason or ""))
        elif status == "error":
            _add_alert("warning", "⚠️ Algo {} order FAILED".format(signal_type),
                       str(res.get("detail") or res.get("reason") or "")[:200])
        return res
    except Exception:
        return None


def _track_asset_alert(asset, signal, reason):
    """Log signal-change alerts for BTC / Bank Nifty, push Telegram on change."""
    try:
        key = f"{asset}:{datetime.now().date()}"
        last = _asset_last_signal.get(asset)
        if last == signal:
            return
        _asset_last_signal[asset] = signal
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "date": datetime.now().strftime("%d-%b"),
            "signal": signal,
            "reason": reason[:120] if reason else "",
            "prev": last or "—",
        }
        lst = _asset_alerts.setdefault(key, [])
        lst.append(entry)
        if len(lst) > 15:
            lst.pop(0)
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".openclaw", "tmp", f"{asset}_alerts.json")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(lst, f, default=str)
        except Exception:
            pass
        try:
            if telegram_alert.is_configured():
                emoji = "🟢" if signal == "BUY_LONG" else "🔴" if signal == "BUY_SHORT" else "⏳"
                label = "₿ BTC" if asset == "btc" else "🏦 BNF" if asset == "banknifty" else "🇮🇳 SENSEX"
                _push_tg(f"{emoji} <b>{label} signal: {signal}</b>\n{reason[:150]}")
        except Exception:
            pass
    except Exception:
        pass


def _asset_alert_list(asset):
    key = f"{asset}:{datetime.now().date()}"
    if key in _asset_alerts:
        return _asset_alerts[key]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".openclaw", "tmp", f"{asset}_alerts.json")
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


@app.route("/api/signal")
def api_signal():
    # Serve cached result for 60s — API responds instantly instead of recomputing
    import time as _t
    now = _t.time()
    if _signal_cache["data"] is None or (now - _signal_cache["ts"]) > 60:
        _signal_cache["data"] = get_signal()
        _signal_cache["ts"] = now
    signal = _signal_cache["data"]
    emoji = {"BUY_CALLS": "🟢", "BUY_PUTS": "🔴", "WAIT": "🟡", "STAND_ASIDE": "🔴", "ERROR": "⚪"}
    
    # Auto-track paper positions when entry/exit signals fire
    try:
        sig_name = signal.get("signal", "")
        if sig_name in ("BUY_CALLS", "BUY_PUTS"):
            direction = "BUY"
            option_type = "CE" if sig_name == "BUY_CALLS" else "PE"
            strike = signal.get("entry_strike", 0)
            premium = signal.get("entry_premium") or 0
            expiry = signal.get("expiry") or signal.get("selected_expiry") or ""
            # Check if we already have an active position on the same option
            from algo_trader import load_state
            st = load_state()
            existing = [p for p in st.get("active_positions", [])
                        if p.get("option_type") == option_type
                        and p.get("strike") == strike
                        and p.get("signal_type", "") == "ema_bounce"]
            if not existing:
                pos = track_paper_entry("ema_bounce", direction, strike, 1, premium, option_type, expiry)
                signal["paper_entry"] = pos
                # 🤖 Feed the algo engine — paper order now, real order when live
                _algo_trade("ema_bounce", direction, strike, expiry, 1, premium, option_type,
                            reason="200 EMA bounce signal")
        elif sig_name in ("EXIT_LONGS", "EXIT_SHORTS"):
            current_premium = signal.get("entry_premium") or signal.get("btst_premium") or 0
            results = track_paper_exit_all(current_premium, "long" if sig_name == "EXIT_LONGS" else "short")
            if results:
                total_pnl = sum(r["pnl"] for r in results)
                signal["paper_exit"] = {"count": len(results), "total_pnl": total_pnl}
                # 🔔 Telegram push — every exit trigger
                try:
                    if telegram_alert.is_configured():
                        side = "CE (long)" if sig_name == "EXIT_LONGS" else "PE (short)"
                        sign = "🟢" if total_pnl >= 0 else "🔴"
                        _push_tg(
                            f"{sign} <b>EXIT {side}</b> — {len(results)} position(s) closed\n"
                            f"P&L: ₹{total_pnl:+,.2f} ({signal.get('signal')})")
                except Exception:
                    pass
    except Exception:
        pass  # Non-critical
    
    return jsonify({
        **signal,
        "emoji": emoji.get(sig_name, "⚪"),
        "updated": datetime.now().strftime("%H:%M:%S"),
    })

@app.route("/api/fiidii")
def api_fiidii():
    """Smart Money FII/DII flows (cached 30 min)."""
    return jsonify(fiidii_summary())

@app.route("/api/outlook")
def api_outlook():
    """Tomorrow outlook: GIFT Nifty gap + US cues (cached 5 min)."""
    return jsonify(get_outlook())

@app.route("/api/oi")
def api_oi():
    """OI Buildup / Smart Money Flow (cached 2 min)."""
    return jsonify(get_oi_buildup())

@app.route("/api/bnf/chain")
def api_bnf_chain():
    return jsonify(get_chain(asset="banknifty"))

@app.route("/api/bnf/expiry")
def api_bnf_expiry():
    return jsonify(get_expiry(asset="banknifty"))

@app.route("/api/bnf/ivrank")
def api_bnf_ivrank():
    return jsonify(get_iv_rank(asset="banknifty"))

@app.route("/api/bnf/oi")
def api_bnf_oi():
    return jsonify(get_oi_buildup(asset="banknifty"))

@app.route("/api/bnf/backtest")
def api_bnf_backtest():
    return jsonify(get_backtest(asset="banknifty"))

@app.route("/api/gapgo")
def api_gapgo():
    """Gap & Go / Gap Fade (cached 60s)."""
    return jsonify(compute_gap_signal())

@app.route("/api/btc")
def api_btc():
    """Bitcoin 200 EMA bounce signal (cached 60s). Supports ?interval=15m|1h|4h."""
    import time as _t
    interval = request.args.get("interval", "1h")
    key = f"{interval}:{_btc_cache['ts']}"
    if _btc_cache["data"] is None or (_t.time() - _btc_cache["ts"]) > 60 or _btc_cache.get("interval") != interval:
        _btc_cache["data"] = get_btc_signal(interval)
        _btc_cache["ts"] = _t.time()
        _btc_cache["interval"] = interval
    data = dict(_btc_cache["data"])
    _track_asset_alert("btc", data.get("signal"), data.get("reason"))
    data["alerts"] = _asset_alert_list("btc")
    return jsonify(data)

@app.route("/api/banknifty")
def api_banknifty():
    """Bank Nifty 200 EMA bounce signal (cached 60s)."""
    import time as _t
    if _bnf_cache["data"] is None or (_t.time() - _bnf_cache["ts"]) > 60:
        _bnf_cache["data"] = get_banknifty_signal()
        _bnf_cache["ts"] = _t.time()
    data = dict(_bnf_cache["data"])
    _track_asset_alert("banknifty", data.get("signal"), data.get("reason"))
    data["alerts"] = _asset_alert_list("banknifty")
    return jsonify(data)


@app.route("/api/sensex")
def api_sensex():
    """Sensex 200 EMA bounce signal (cached 60s)."""
    import time as _t
    if _sensex_cache["data"] is None or (_t.time() - _sensex_cache["ts"]) > 60:
        _sensex_cache["data"] = get_sensex_signal("1h")
        _sensex_cache["ts"] = _t.time()
    data = dict(_sensex_cache["data"])
    _track_asset_alert("sensex", data.get("signal"), data.get("reason"))
    data["alerts"] = _asset_alert_list("sensex")
    return jsonify(data)

@app.route("/api/expiry")
def api_expiry():
    """Expiry countdown + gamma risk (cached 10 min)."""
    return jsonify(get_expiry())

@app.route("/api/weeklyreview")
def api_weeklyreview():
    """Latest weekly review report."""
    return jsonify(get_weekly_report())

@app.route("/api/ivrank")
def api_ivrank():
    """IV Rank / Percentile for Nifty (cached 30 min)."""
    return jsonify(get_iv_rank())

@app.route("/api/backtest")
def api_backtest():
    """Strategy backtest report (cached 1 hour)."""
    return jsonify(get_backtest())

@app.route("/api/chain")
def api_chain():
    """Option chain table with walls (cached 60s)."""
    return jsonify(get_chain())

@app.route("/api/telegram/status")
def api_tg_status():
    return jsonify({"configured": is_configured()})

@app.route("/api/telegram/set")
def api_tg_set():
    """Set bot token (and optionally chat id). Query: ?token=...&chat_id=..."""
    token = request.args.get("token", "")
    chat_id = request.args.get("chat_id", "")
    if not token and not chat_id:
        return jsonify({"error": "Provide ?token= and/or ?chat_id="}), 400
    cfg = save_config(token or None, chat_id or None)
    return jsonify({"ok": True, "configured": is_configured()})

@app.route("/api/telegram/chatid")
def api_tg_chatid():
    """Auto-discover chat id from bot updates (user must message the bot first)."""
    cid, err = get_chat_id_from_updates()
    if cid:
        save_config(chat_id=cid)
        return jsonify({"ok": True, "chat_id": cid})
    return jsonify({"error": err}), 400

@app.route("/api/telegram/test")
def api_tg_test():
    ok, err = send_telegram("✅ Nifty Signal connected! You'll receive alerts here.")
    return jsonify({"ok": ok, "error": err})

@app.route("/api/chart")
def api_chart():
    """Price + 200 EMA series. ?asset=nifty|btc|banknifty&interval=1d|1h|15m|4h (cached 10 min)."""
    asset = request.args.get("asset", "nifty")
    interval = request.args.get("interval") or None
    return jsonify(get_chart_data(asset, interval))

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
    import time as _t
    if _intraday_cache["data"] is None or (_t.time() - _intraday_cache["ts"]) > 60:
        _intraday_cache["data"] = run_script("intraday_signals.py")
        _intraday_cache["ts"] = _t.time()
    return jsonify(_clean_nan(_intraday_cache["data"]))


_scalper_cache = {"ts": 0, "data": None}
_scalper_caches = {a: {"ts": 0, "data": None} for a in ("nifty", "bnf", "sensex", "btc")}
_scalp_watch = {"signal": None, "option": None, "entry": None, "ts": None, "highest": None,
               "breakeven": False, "trail": False}
_scalp_watches = {a: {"signal": None, "option": None, "entry": None, "ts": None, "highest": None,
                       "breakeven": False, "trail": False} for a in ("nifty", "bnf", "sensex", "btc")}
_scalp_calls = []  # today's scalp call log (ACTIVE until target/stop/expiry)
_SCALP_CALLS_PATH = os.path.join(WORKSPACE, ".openclaw", "tmp", "scalp_calls.json")

try:
    with open(_SCALP_CALLS_PATH) as _f:
        _scalp_calls = json.load(_f)
except Exception:
    _scalp_calls = []


def _scalp_save_calls():
    try:
        os.makedirs(os.path.dirname(_SCALP_CALLS_PATH), exist_ok=True)
        with open(_SCALP_CALLS_PATH, "w") as _f:
            json.dump(_scalp_calls[-20:], _f, default=str)
    except Exception:
        pass


def _chain_premium(asset, strike, option_type):
    """Current premium/price for a call's tracked instrument.
    Options assets: LTP from the (cached) Upstox chain for strike+type.
    Spot assets (sensex/btc): current spot from the scalper output."""
    if asset in ("sensex", "btc"):
        try:
            sc = _scalper_caches.get(asset, {}).get("data") or {}
            return sc.get("spot")
        except Exception:
            return None
    try:
        from chain_table import get_chain
        ch = get_chain(asset="banknifty" if asset == "bnf" else "nifty")
        for r in ch.get("rows") or []:
            if abs((r.get("strike") or 0) - strike) < 0.01:
                return r.get("ce_ltp") if option_type == "CE" else r.get("pe_ltp")
    except Exception:
        pass
    return None


def _scalp_append_call(asset, sc, call):
    """Log a newly fired scalp call."""
    _scalp_calls.append({
        "id": len(_scalp_calls) + 1,
        "asset": asset,
        "time": datetime.now().strftime("%H:%M:%S"),
        "signal": sc.get("signal"),
        "option": call.get("option"),
        "strike": call.get("strike"),
        "option_type": "CE" if sc.get("signal") == "SCALP_LONG" else "PE",
        "entry": call.get("entry"), "target": call.get("target"), "stop": call.get("stop"),
        "expires_at": call.get("expires_at"), "status": "ACTIVE",
    })
    if len(_scalp_calls) > 60:
        del _scalp_calls[:-60]
    _scalp_save_calls()


def _scalp_refresh_statuses():
    """Check ACTIVE calls: TARGET_HIT / STOP_HIT / EXPIRED. Returns events to push."""
    events = []
    now_hm = datetime.now().strftime("%H:%M")
    for c in _scalp_calls:
        if c.get("status") != "ACTIVE":
            continue
        if c.get("expires_at") and now_hm > c.get("expires_at") and c.get("expires_at") != "INTRAday":
            c["status"] = "EXPIRED"
            c["hit_time"] = now_hm
            events.append((c, "expired"))
            continue
        prem = _chain_premium(c.get("asset") or "nifty", c.get("strike"), c.get("option_type"))
        if prem is None:
            continue
        if c.get("target") and prem >= c["target"]:
            c["status"] = "TARGET_HIT"; c["hit_time"] = now_hm; c["hit_premium"] = prem
            events.append((c, "target"))
        elif c.get("stop") and prem <= c["stop"]:
            c["status"] = "STOP_HIT"; c["hit_time"] = now_hm; c["hit_premium"] = prem
            events.append((c, "stop"))
    if events:
        _scalp_save_calls()
    return events

SCALP_ASSETS = ("nifty", "bnf", "sensex", "btc")
SCALP_EMOJI = {"nifty": "📈", "bnf": "🏦", "sensex": "🇮🇳", "btc": "₿"}
_FIVE_MIN_MARKS = ("00", "05", "10", "15", "20", "25", "30", "35", "40", "45", "50", "55")


def _is_five_min_tick(minute):
    """True when HH:MM lands on a 5-minute boundary."""
    return minute[-2:] in _FIVE_MIN_MARKS


def _scalp_tick(asset):
    """Run one scalper sweep for an asset: fire new calls, trail the active one,
    resolve call log statuses (target/stop/expiry), push alerts."""
    import scalper as _sc
    sc = _sc.main(asset)
    sc_sig = sc.get("signal")
    call = sc.get("call") or {}
    watch = _scalp_watches[asset]
    emoji = SCALP_EMOJI.get(asset, "📈")
    tag = "{} {}".format(emoji, asset.upper())
    # New call fired → entry push + start watch
    if sc_sig in ("SCALP_LONG", "SCALP_SHORT") and not call.get("blocked") and call.get("entry"):
        new_call = watch["signal"] != sc_sig or watch["option"] != call.get("option")
        if new_call:
            watch.update({
                "signal": sc_sig, "option": call.get("option"), "entry": call.get("entry"),
                "ts": datetime.now(), "highest": call.get("entry"),
                "breakeven": False, "trail": False})
            _scalp_append_call(asset, sc, call)
            d_emoji = "🟢" if sc_sig == "SCALP_LONG" else "🔴"
            _add_alert("critical", "{} {} SCALP: {}".format(d_emoji, tag, call.get("option")),
                "Entry ₹{} | Target ₹{} (+10%) | Stop ₹{} (-10%) | Expiry {} | Lot ₹{:,} | Spread {}% | ⏳ expires {}\n{}".format(
                    call.get("entry"), call.get("target"), call.get("stop"),
                    call.get("expiry"), call.get("lot_cost") or 0,
                    call.get("spread_pct"), call.get("expires_at"), sc.get("reason", "")))
        else:
            # Same call still active → trailing watch
            prem = call.get("premium")
            entry = watch["entry"]
            if prem and entry:
                watch["highest"] = max(watch["highest"] or entry, prem)
                pct = (prem - entry) / entry * 100
                if pct >= 5 and not watch["breakeven"]:
                    watch["breakeven"] = True
                    _add_alert("warning", "🛡️ {} SCALP +5% — move stop to breakeven".format(tag),
                        "{} now ₹{} (entry ₹{}). Free trade — stop at entry.".format(call.get("option"), prem, entry))
                if pct >= 7 and not watch["trail"]:
                    watch["trail"] = True
                    _add_alert("warning", "🪢 {} SCALP +7% — trail stop at 50% profit".format(tag),
                        "{} now ₹{} (entry ₹{}). Trail from here.".format(call.get("option"), prem, entry))
                if pct <= -10:
                    _add_alert("critical", "🛑 {} SCALP STOP HIT (−10%)".format(tag),
                        "{} at ₹{} (entry ₹{}). EXIT NOW — scalp over.".format(call.get("option"), prem, entry))
                    watch.update({"signal": None, "option": None})
        # Expiry check: call older than its 10-min freshness
        if watch["ts"] and call.get("expires_at"):
            now_hm = datetime.now().strftime("%H:%M")
            if now_hm > call.get("expires_at") and watch["signal"]:
                _add_alert("info", "⏳ {} Scalp call expired — no entry taken".format(tag),
                    "{} expired at {} (10-min freshness). Next call when setup re-fires.".format(
                        watch["option"], call.get("expires_at")))
                watch.update({"signal": None, "option": None})
    elif sc_sig == "WAIT" and watch["signal"] in ("SCALP_LONG", "SCALP_SHORT"):
        _add_alert("info", "⏳ {} Scalp closed — back to WAIT".format(tag), sc.get("reason", ""))
        watch.update({"signal": None, "option": None})
    # 🎯 Resolve call log statuses — TARGET_HIT / STOP_HIT / EXPIRED (kept alive till expiry)
    for c, ev in _scalp_refresh_statuses():
        if c.get("asset") != asset:
            continue
        if ev == "target":
            _add_alert("critical", "🎯 {} SCALP TARGET HIT (+10%)".format(tag),
                "{} hit ₹{} (target ₹{}). Book profit — call done.".format(
                    c.get("option"), c.get("hit_premium"), c.get("target")))
        elif ev == "stop":
            _add_alert("critical", "🛑 {} SCALP STOP HIT (−10%)".format(tag),
                "{} fell to ₹{} (stop ₹{}). EXIT — call done.".format(
                    c.get("option"), c.get("hit_premium"), c.get("stop")))
        elif ev == "expired":
            _add_alert("info", "⏳ {} SCALP CALL EXPIRED".format(tag),
                "{} expired at {} — no entry taken.".format(c.get("option"), c.get("expires_at")))



@app.route("/api/scalper")
def api_scalper():
    """Scalper for any asset — 5m momentum bias + actionable call. 30s cache.
    ?asset=nifty|bnf|sensex|btc (default nifty)."""
    import time as _t
    asset = request.args.get("asset", "nifty").lower()
    if asset not in _scalper_caches:
        return jsonify({"error": "unknown asset", "asset": asset}), 400
    c = _scalper_caches[asset]
    if c["data"] is None or (_t.time() - c["ts"]) > 30:
        try:
            import scalper as _sc
            c["data"] = _sc.main(asset)
        except Exception as e:
            c["data"] = {"error": str(e), "asset": asset}
        c["ts"] = _t.time()
    out = dict(c["data"] or {})
    out["calls"] = list(reversed([x for x in _scalp_calls if x.get("asset") == asset]))
    return jsonify(_clean_nan(out))


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
    # Push to Telegram — EVERY alert (info/warning/critical), batched, never dropped
    emoji = {"critical": "🔴", "warning": "⚠️", "info": "ℹ️"}.get(level, "🔔")
    _push_tg(f"{emoji} <b>{title}</b>\n{body}")

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
    last_eod_summary = None
    last_orb_check = None
    last_intraday_check = None
    last_scalp_check = None
    last_scalp_signal = None
    last_oi_signal = None
    last_gap_check = None
    last_market_open_push = None
    
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

            # ── Market-open status push at 9:15 (always pings, even on WAIT) ──
            if in_market and current_minute == "09:15" and last_market_open_push != today:
                last_market_open_push = today
                try:
                    sig = get_signal()
                    _add_alert("info", "🕘 MARKET OPEN — Morning Status",
                        f"Nifty {sig.get('spot', 'N/A')} | VIX {sig.get('vix', 'N/A')} | "
                        f"PCR {sig.get('oi_pcr', 'N/A')} | Signal: {sig.get('signal', 'N/A')} | "
                        f"200 EMA {sig.get('ema_200', 'N/A')} | IV Rank {sig.get('iv_rank', 'N/A')}%")
                except Exception as e:
                    _add_alert("warning", "Market Open Push Failed", str(e)[:150])
            
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
                    spot = sig.get("spot", 0)
                    stop_level = sig.get("stop_level", 0)
                    
                    if signal in ("BUY_CALLS", "BUY_PUTS"):
                        # Include risk disclosure
                        premium = sig.get("entry_premium") or 0
                        risk_per_lot = round(abs(spot - stop_level) * (sig.get("entry_delta") or 0.5) * 65, 2)
                        _add_alert("critical", f"🔴 {signal} — 200 EMA",
                            f"Spot: {spot} | ADX: {sig.get('adx')} | "
                            f"PCR: {sig.get('weekly_pcr')} | IV: {sig.get('atm_iv')}% | "
                            f"Stop: {stop_level} | Max loss: ₹{risk_per_lot}/lot | "
                            f"Trade: {sig.get('recommended_trade', '')[:100]}")
                    elif signal in ("EXIT_LONGS", "EXIT_SHORTS"):
                        _add_alert("critical", f"⚠️ {signal}", sig.get("exit_reason", ""))
                    
                    # ── Stop approach warning ──
                    if stop_level and spot and signal in ("BUY_CALLS", "BUY_PUTS", "WAIT"):
                        dist_to_stop = abs(spot - stop_level)
                        stop_pct = round(dist_to_stop / spot * 100, 2)
                        if stop_pct < 0.3:  # Within 0.3% of stop
                            _add_alert("critical", f"🛑 STOP APPROACHING — {stop_pct}% away!",
                                f"Spot: {spot} | Stop: {stop_level} | Distance: {dist_to_stop:.0f} pts | "
                                f"EXIT NOW if stop breaks! Max loss if held: ₹{(sig.get('entry_premium') or 0) * 65:.0f}/lot")
                        elif stop_pct < 0.6:  # Within 0.6%
                            _add_alert("warning", f"⚠️ Near stop — {stop_pct}% from {stop_level}",
                                f"Distance: {dist_to_stop:.0f} pts. Prepare to exit.")
                    # Contrarian PCR check
                    cs = sig.get("contrarian_signal", "")
                    if cs in ("SELL_CALLS", "SELL_PUTS"):
                        _add_alert("critical", f"🔄 Contrarian: {cs}",
                            sig.get("contrarian_reason", ""))
                        # 🤖 Algo feed — buyer-only mapping: SELL_CALLS (bearish) → buy PE, SELL_PUTS → buy CE
                        _algo_trade("contrarian", "BUY",
                                    sig.get("atm_strike") or sig.get("entry_strike"),
                                    sig.get("selected_expiry", ""), 1, None,
                                    "PE" if cs == "SELL_CALLS" else "CE",
                                    reason=(sig.get("contrarian_reason") or "")[:80])
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
                        o_dir = "BUY" if orb.get("signal") == "ORB_BUY" else "SELL"
                        o_type = "CE" if orb.get("signal") == "ORB_BUY" else "PE"
                        o_strike = orb.get("entry_strike")
                        o_exp = orb.get("expiry") or ""
                        if not o_exp:
                            try:
                                o_exp = get_signal().get("selected_expiry", "")
                            except Exception:
                                pass
                        _algo_trade("orb", o_dir, o_strike, o_exp, 1, None, o_type,
                                    reason=(orb.get("reason") or "")[:80])
                except Exception as e:
                    pass
            
            # ── Intraday (VWAP + EMA) every 5 min ──
            if in_market and current_minute[-2:] in _FIVE_MIN_MARKS and last_intraday_check != current_minute:
                last_intraday_check = current_minute
                try:
                    intra = run_script("intraday_signals.py")
                    # VWAP
                    vwap = intra.get("vwap", {})
                    if vwap and vwap.get("signal") in ("VWAP_BUY", "VWAP_SELL"):
                        _add_alert("critical", f"📊 VWAP: {vwap['signal']}",
                            f"{vwap.get('reason', '')} | Spot: {vwap.get('spot')} | VWAP: {vwap.get('vwap')}")
                        try:
                            s_ref = get_signal()
                            _algo_trade("vwap", "BUY" if vwap["signal"] == "VWAP_BUY" else "SELL",
                                        s_ref.get("atm_strike") or s_ref.get("entry_strike"),
                                        s_ref.get("selected_expiry", ""), 1, None,
                                        "CE" if vwap["signal"] == "VWAP_BUY" else "PE",
                                        reason=(vwap.get("reason") or "")[:80])
                        except Exception:
                            pass
                    # EMA crossover
                    ema = intra.get("ema", {})
                    if ema and ema.get("signal") in ("EMA_BUY", "EMA_SELL"):
                        _add_alert("critical", f"📈 EMA: {ema['signal']}",
                            f"{ema.get('reason', '')} | Spot: {ema.get('spot')} | "
                            f"EMA9: {ema.get('ema9')} | EMA21: {ema.get('ema21')}")
                except Exception as e:
                    pass

            # ── Scalper (5m momentum + live option call) every 5 min ──
            if in_market and current_minute[-2:] in _FIVE_MIN_MARKS and last_scalp_check != current_minute:
                last_scalp_check = current_minute
                # ⚡ Scalper sweep — all assets (nifty/bnf/sensex spot/btc spot)
                for _a in SCALP_ASSETS:
                    try:
                        _scalp_tick(_a)
                    except Exception:
                        pass

            # ── OI Buildup (smart money) — snapshot every 5 min + alert on bias flip ──
            if in_market and current_minute.endswith(("00", "05", "10", "15", "20", "25",
                                                      "30", "35", "40", "45", "50", "55")):
                try:
                    take_snapshot(force=True)
                    oi = get_oi_buildup(force=True)
                    oi_sig = oi.get("signal")
                    if oi_sig in ("BUY_CALLS", "BUY_PUTS") and oi_sig != last_oi_signal:
                        last_oi_signal = oi_sig
                        emoji = "🟢" if oi_sig == "BUY_CALLS" else "🔴"
                        top_ce = ", ".join(f"{r['strike']}(+{r['oi_gain']:,})" for r in oi.get("ce_buildup", [])[:3])
                        top_pe = ", ".join(f"{r['strike']}(+{r['oi_gain']:,})" for r in oi.get("pe_buildup", [])[:3])
                        _add_alert("critical", f"{emoji} OI BUILDUP: {oi_sig}",
                            f"{oi.get('reason', '')}\nCE loading: {top_ce or 'none'}\nPE loading: {top_pe or 'none'}")
                        # 🤖 Algo feed — top OI-buildup strike
                        try:
                            s_ref = get_signal()
                            b_list = oi.get("ce_buildup") if oi_sig == "BUY_CALLS" else oi.get("pe_buildup")
                            b_strike = b_list[0]["strike"] if b_list else (s_ref.get("atm_strike") or 0)
                            _algo_trade("oi_buildup", "BUY", b_strike, s_ref.get("selected_expiry", ""), 1, None,
                                        "CE" if oi_sig == "BUY_CALLS" else "PE",
                                        reason=("OI buildup " + oi_sig))
                        except Exception:
                            pass
                    # Bank Nifty OI snapshots too
                    take_snapshot(force=True, asset="banknifty")
                    oib = get_oi_buildup(force=True, asset="banknifty")
                    if oib.get("signal") in ("BUY_CALLS", "BUY_PUTS"):
                        _add_alert("critical", f"🏦 BNF OI BUILDUP: {oib['signal']}",
                            f"{oib.get('reason', '')}")
                except Exception:
                    pass

            # ── Gap & Go / Gap Fade (9:15-9:45, every 5 min) ──
            if in_market and current_minute.endswith(("00", "05", "10", "15", "20", "25",
                                                      "30", "35", "40", "45", "50", "55")) \
                    and last_gap_check != current_minute:
                last_gap_check = current_minute
                try:
                    gap = compute_gap_signal(force=True)
                    if gap.get("signal") in ("GAP_GO_BUY", "GAP_FADE_BUY", "GAP_FILL_WATCH"):
                        emoji = {"GAP_GO_BUY": "🟢", "GAP_FADE_BUY": "🔴", "GAP_FILL_WATCH": "⏳"}[gap["signal"]]
                        _add_alert("critical", f"{emoji} {gap['signal']}",
                            f"{gap.get('reason', '')} | Price: {gap.get('price')} | VWAP: {gap.get('vwap')}")
                        # 🤖 Algo feed (GAP_GO_BUY = momentum long; GAP_FADE_BUY = fade = short bias)
                        if gap.get("signal") in ("GAP_GO_BUY", "GAP_FADE_BUY"):
                            try:
                                s_ref = get_signal()
                                is_long = gap["signal"] == "GAP_GO_BUY"
                                _algo_trade("gap_go", "BUY" if is_long else "SELL",
                                            s_ref.get("atm_strike") or s_ref.get("entry_strike"),
                                            s_ref.get("selected_expiry", ""), 1, None,
                                            "CE" if is_long else "PE",
                                            reason=(gap.get("reason") or "")[:80])
                            except Exception:
                                pass
                except Exception:
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
            
            # ── Daily P&L Summary at 3:30 PM ──
            if current_minute == "15:30" and last_eod_summary != today:
                last_eod_summary = today
                try:
                    from algo_trader import load_state
                    st = load_state()
                    pnl = st.get("pnl_today", 0)
                    trades = st.get("trades_today", 0) + len(st.get("closed_trades", []))
                    pos_count = len(st.get("active_positions", []))
                    emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
                    _add_alert("info", f"{emoji} Market Closed — P&L: ₹{pnl:,.0f}",
                        f"Trades today: {trades} | Open positions: {pos_count} | "
                        f"{'Profit' if pnl > 0 else 'Loss' if pnl < 0 else 'Flat'} day. "
                        f"Review your journal and prep for tomorrow.")
                except:
                    pass

            # ── Friday Weekly Review at 3:35 PM ──
            if current_minute == "15:35" and now.weekday() == 4 and last_eod_summary != today:
                try:
                    rep = build_weekly_report()
                    _add_alert("info", f"📊 Weekly Review (W{now.isocalendar()[1]})",
                        f"Trades: {rep['trades']} | Win rate: {rep['win_rate']}% | P&L: ₹{rep['pnl']:,.0f} | "
                        f"Avg win: ₹{rep['avg_win']:,.0f} | Avg loss: ₹{rep['avg_loss']:,.0f} | {rep['read']}")
                except Exception:
                    pass

            # ── Tuesday Expiry Day Warning at 9:20 AM ──
            if current_minute == "09:20" and now.weekday() == 1:
                try:
                    from expiry_countdown import get_expiry
                    ex = get_expiry(force=True)
                    _add_alert("critical", "⚠️ EXPIRY DAY — Gamma Alert",
                        f"Weekly expiry TODAY. {ex['gamma_note']} Don't buy new weeklies late — theta and gamma will wreck you. Close/roll by 3:15 PM.")
                except Exception:
                    pass
            
            time.sleep(30)
        except Exception as e:
            print(f"[SCHEDULER ERROR] {e}")
            time.sleep(60)


def warmup_caches():
    """Pre-compute heavy endpoints at boot so the first page load is instant."""
    jobs = [
        (get_signal, (), 1),
        (lambda: get_chain(asset="nifty"), (), 3),
        (lambda: get_chain(asset="banknifty"), (), 5),
        (lambda: get_btc_signal("1h"), (), 7),
        (lambda: get_banknifty_signal(), (), 9),
        (lambda: get_sensex_signal("1h"), (), 10),
        (fiidii_summary, (), 11),
        (get_outlook, (), 13),
        (lambda: get_iv_rank(asset="nifty"), (), 15),
        (lambda: get_iv_rank(asset="banknifty"), (), 17),
        (lambda: get_backtest(asset="nifty"), (), 19),
        (lambda: get_backtest(asset="banknifty"), (), 21),
        (lambda: get_expiry(asset="banknifty"), (), 23),
        (lambda: _intraday_cache.update(data=run_script("intraday_signals.py"), ts=time.time()), (), 25),
    ]
    for fn, args, delay in jobs:
        try:
            time.sleep(delay)
            fn(*args)
        except Exception:
            pass
    print("   Warmup:  All caches pre-computed")


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
    try:
        with open(os.path.join(app.static_folder, "index.html"), "r") as f:
            html = f.read()
        # Force browsers to NEVER cache — inject version into HTML
        html = html.replace('</head>', '<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate, max-age=0"><meta http-equiv="Pragma" content="no-cache"><meta http-equiv="Expires" content="0"></head>')
        return html, 200, {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    except:
        return "Error loading dashboard", 500

@app.route("/v2")
def dashboard_v2():
    """Force-fresh dashboard — guaranteed no cache"""
    try:
        with open(os.path.join(app.static_folder, "index.html"), "r") as f:
            html = f.read()
        # Inject cache-busting comment
        ts = str(int(time.time()))
        html = html.replace('</head>', '<meta http-equiv="Cache-Control" content="no-store"><meta http-equiv="Pragma" content="no-cache"></head>')
        response = Response(html, 200)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['ETag'] = ts
        return response
    except Exception as e:
        return f"Error: {e}", 500

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(app.static_folder, path)


if __name__ == "__main__":
    # Global socket timeout: no request may hang forever on a dead network call
    import socket as _socket
    _socket.setdefaulttimeout(20)

    # ── Single-instance guard: exit if port already taken (prevents double schedulers) ──
    _probe = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        _probe.bind(("0.0.0.0", PORT))
        _probe.close()
    except OSError:
        print(f"⚠️  Port {PORT} already in use — another instance is running. Exiting.")
        sys.exit(0)

    print(f"🚀 Nifty Signal Server starting on port {PORT}")
    print(f"   Local:   http://localhost:{PORT}")
    if not IS_CLOUD:
        print(f"   Mobile:  http://<mac-ip>:{PORT}")
    print(f"   API:     http://localhost:{PORT}/api/signal")
    
    if IS_CLOUD:
        print("   Mode:    ☁️  Cloud (scheduler enabled by default; set NO_SCHEDULER=true to disable)")
        if os.environ.get("NO_SCHEDULER", "") == "true":
            print("   Alerts:  DISABLED via NO_SCHEDULER env var")
        else:
            scheduler = threading.Thread(target=alert_scheduler, daemon=True)
            scheduler.start()
            print("   Alerts:  Background scheduler started")
            tgs = threading.Thread(target=tg_sender, daemon=True)
            tgs.start()
            print("   Telegram: Batched sender started")
            wu = threading.Thread(target=warmup_caches, daemon=True)
            wu.start()
            print("   Warmup:  Background cache pre-compute started")
    else:
        tunnel = detect_tunnel_url()
        if tunnel:
            print(f"   Tunnel:  {tunnel}")
        if os.environ.get("NO_SCHEDULER", "") == "true":
            print("   Alerts:  DISABLED via NO_SCHEDULER (dashboard-only mode)")
        else:
            scheduler = threading.Thread(target=alert_scheduler, daemon=True)
            scheduler.start()
            print("   Alerts:  Background scheduler started")
            tgs = threading.Thread(target=tg_sender, daemon=True)
            tgs.start()
            print("   Telegram: Batched sender started")
        wu = threading.Thread(target=warmup_caches, daemon=True)
        wu.start()
        print("   Warmup:  Background cache pre-compute started")
    
    # Always start paper tracking heartbeat
    pth = threading.Thread(target=paper_tracking_heartbeat, daemon=True)
    pth.start()
    print("   Paper:   Auto-tracking enabled")
    
    print()
    
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
