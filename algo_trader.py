#!/usr/bin/env python3
"""
Algo Trading Module — Upstox API v2
DRY-RUN by default. Set LIVE_MODE via config to place real orders.
"""

import json, os, time, threading, requests
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

UPSTOX_BASE = "https://api.upstox.com/v2"
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(WORKSPACE, ".openclaw", "tmp", "algo_config.json")
ALGO_LOG_PATH = os.path.join(WORKSPACE, ".openclaw", "tmp", "algo_orders.json")

# ── Config ──
DEFAULT_CONFIG = {
    "live_mode": False,          # NEVER change this manually — use API toggle
    "max_lots_per_trade": 2,
    "max_lots_per_day": 10,
    "daily_loss_limit": 10000,   # ₹ — stops trading if hit
    "enabled_strategies": {
        "ema_bounce": False,     # 200 EMA signals
        "contrarian": False,     # PCR reversal
        "orb": False,            # Opening range breakout
        "vwap": False,           # VWAP reversion
        "btst_exit": False,      # Auto-exit BTST
    },
    "lot_size": 65,
}

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
            # Merge defaults for any missing keys
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    save_config(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ── State Tracking ──
_algo_state = {
    "today": "",
    "trades_today": 0,
    "lots_today": 0,
    "pnl_today": 0.0,
    "total_pnl": 0.0,  # Running paper P&L
    "active_positions": [],
    "closed_trades": [],
    "daily_limit_hit": False,
    "last_order_time": None,
}

def load_state():
    global _algo_state
    today = datetime.now(IST).strftime("%Y-%m-%d")
    if _algo_state["today"] != today:
        _algo_state = {
            "today": today,
            "trades_today": 0,
            "lots_today": 0,
            "pnl_today": 0.0,
            "active_positions": [],
            "daily_limit_hit": False,
            "last_order_time": None,
        }
    return _algo_state

def save_order_log(order):
    logs = []
    if os.path.exists(ALGO_LOG_PATH):
        with open(ALGO_LOG_PATH) as f:
            logs = json.load(f)
    order["id"] = len(logs) + 1
    order["timestamp"] = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    logs.append(order)
    os.makedirs(os.path.dirname(ALGO_LOG_PATH), exist_ok=True)
    with open(ALGO_LOG_PATH, "w") as f:
        json.dump(logs, f, indent=2, default=str)
    return order


# ── Order Building ──

def build_order(signal_type, direction, strike, expiry, lots, premium=None):
    """
    Build an order object. In dry-run mode, returns the planned order without executing.
    signal_type: 'ema_bounce' | 'contrarian' | 'orb' | 'vwap' | 'btst_exit'
    direction: 'BUY' | 'SELL'
    """
    lot_size = 65
    qty = lots * lot_size
    
    # Map to Upstox transaction type
    txn_type = "BUY" if direction == "BUY" else "SELL"
    
    order = {
        "signal_type": signal_type,
        "transaction_type": txn_type,
        "instrument": f"NIFTY {strike} {'CE' if 'CE' in str(strike) or txn_type == 'BUY' else 'PE'}",
        "strike": strike,
        "expiry": expiry,
        "lots": lots,
        "quantity": qty,
        "premium_est": premium,
        "order_type": "MARKET",
        "product": "NRML",  # NRML = carry forward
    }
    return order


# ── Trade Execution ──

def execute_trade(signal_type, direction, strike, expiry, lots, premium=None):
    """Execute a trade or log it in dry-run mode."""
    state = load_state()
    cfg = load_config()
    
    # Check strategy enabled
    if not cfg["enabled_strategies"].get(signal_type, False):
        return {"status": "blocked", "reason": f"Strategy '{signal_type}' not enabled"}
    
    # Check daily limits
    if state["daily_limit_hit"]:
        return {"status": "blocked", "reason": f"Daily loss limit ₹{cfg['daily_loss_limit']} hit — paused"}
    
    if state["lots_today"] + lots > cfg["max_lots_per_day"]:
        return {"status": "blocked", "reason": f"Max daily lots ({cfg['max_lots_per_day']}) exceeded"}
    
    if lots > cfg["max_lots_per_trade"]:
        return {"status": "blocked", "reason": f"Max lots per trade ({cfg['max_lots_per_trade']}) exceeded"}
    
    order = build_order(signal_type, direction, strike, expiry, lots, premium)
    
    if not cfg["live_mode"]:
        # DRY-RUN: just log it
        order["status"] = "DRY_RUN"
        order["note"] = "Would execute in live mode"
        save_order_log(order)
        return {"status": "dry_run", "order": order, "message": f"DRY RUN: {direction} {lots} lot(s) {order['instrument']}"}
    
    # LIVE MODE — place real order via Upstox
    try:
        token = _get_upstox_token()
        if not token:
            return {"status": "error", "reason": "No Upstox token"}
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}
        
        payload = {
            "quantity": order["quantity"],
            "product": order["product"],
            "validity": "DAY",
            "price": 0,
            "trigger_price": 0,
            "instrument_token": _instrument_key(strike, direction, expiry),
            "order_type": "MARKET",
            "transaction_type": order["transaction_type"],
            "disclosed_quantity": 0,
            "is_amo": False,
        }
        
        resp = requests.post(f"{UPSTOX_BASE}/order/place", headers=headers, json=payload, timeout=15)
        
        if resp.status_code == 200:
            data = resp.json()
            order["status"] = "LIVE"
            order["order_id"] = data.get("data", {}).get("order_id", "")
            order["response"] = data
            save_order_log(order)
            
            state["trades_today"] += 1
            state["lots_today"] += lots
            state["last_order_time"] = datetime.now(IST).strftime("%H:%M:%S")
            state["active_positions"].append({
                "order_id": order["order_id"],
                "strike": strike,
                "direction": direction,
                "lots": lots,
                "entry_time": state["last_order_time"],
            })
            
            return {"status": "live", "order": order, "message": f"✅ LIVE: {direction} {lots} lot(s) placed"}
        else:
            order["status"] = "FAILED"
            order["error"] = resp.text[:300]
            save_order_log(order)
            return {"status": "error", "reason": f"Upstox API error: {resp.status_code}", "detail": resp.text[:300]}
    
    except Exception as e:
        order["status"] = "FAILED"
        order["error"] = str(e)
        save_order_log(order)
        return {"status": "error", "reason": str(e)}


def _get_upstox_token():
    """Get Upstox token from env or config file."""
    token = os.environ.get("UPSTOX_TOKEN", "")
    if token:
        return token
    try:
        from upstox_token import get_token
        return get_token()
    except:
        pass
    return ""
    return ""


def _instrument_key(strike, direction, expiry):
    """Build Upstox instrument key. NSE_FO format."""
    return f"NSE_FO|{strike}"  # Simplified — real key needs lookup


def get_algo_status():
    """Return full algo status for dashboard."""
    state = load_state()
    cfg = load_config()
    
    # Get recent orders
    orders = []
    if os.path.exists(ALGO_LOG_PATH):
        with open(ALGO_LOG_PATH) as f:
            all_orders = json.load(f)
            orders = all_orders[-20:]  # Last 20
    
    return {
        "live_mode": cfg["live_mode"],
        "dry_run": not cfg["live_mode"],
        "daily_limit": cfg["daily_loss_limit"],
        "max_lots_trade": cfg["max_lots_per_trade"],
        "max_lots_day": cfg["max_lots_per_day"],
        "enabled_strategies": cfg["enabled_strategies"],
        "state": state,
        "recent_orders": orders,
        "active_positions": state.get("active_positions", []),
        "closed_trades": state.get("closed_trades", [])[-10:],
    }


def toggle_live_mode(enable, confirm_code=None):
    """Enable/disable live trading. Requires confirmation."""
    cfg = load_config()
    
    if enable:
        if confirm_code != "CONFIRM_LIVE":
            return {"status": "blocked", "reason": "Must pass confirm_code='CONFIRM_LIVE' to enable live trading"}
        cfg["live_mode"] = True
        save_config(cfg)
        return {"status": "live", "message": "⚠️ LIVE TRADING ENABLED — real orders will be placed"}
    else:
        cfg["live_mode"] = False
        save_config(cfg)
        return {"status": "dry_run", "message": "Dry-run mode — no real orders"}


def toggle_strategy(strategy_name, enable):
    """Enable/disable a specific strategy."""
    cfg = load_config()
    if strategy_name not in cfg["enabled_strategies"]:
        return {"status": "error", "reason": f"Unknown strategy: {strategy_name}"}
    cfg["enabled_strategies"][strategy_name] = enable
    save_config(cfg)
    return {"status": "ok", "strategy": strategy_name, "enabled": enable}


# ── Paper P&L Tracking ──

def track_paper_entry(signal_type, direction, strike, lots, premium):
    """Record a simulated entry position."""
    state = load_state()
    pos = {
        "id": len(state["active_positions"]) + len(state.get("closed_trades", [])) + 1,
        "signal_type": signal_type,
        "direction": direction,
        "strike": strike,
        "lots": lots,
        "entry_premium": premium,
        "entry_time": datetime.now(IST).strftime("%H:%M:%S"),
        "status": "open",
    }
    state["active_positions"].append(pos)
    return pos

def track_paper_exit(position_id, exit_premium):
    """Close a simulated position and calculate P&L."""
    state = load_state()
    lot_size = 65
    
    for i, pos in enumerate(state["active_positions"]):
        if pos["id"] == position_id:
            entry = pos["entry_premium"]
            lots = pos["lots"]
            
            if pos["direction"] == "SELL":
                pnl = round((entry - exit_premium) * lots * lot_size, 2)
            else:
                pnl = round((exit_premium - entry) * lots * lot_size, 2)
            
            pnl_pct = round(pnl / (entry * lots * lot_size) * 100, 2) if entry and lots else 0
            
            pos["exit_premium"] = exit_premium
            pos["pnl"] = pnl
            pos["pnl_pct"] = pnl_pct
            pos["exit_time"] = datetime.now(IST).strftime("%H:%M:%S")
            pos["status"] = "closed"
            
            state["pnl_today"] = round(state["pnl_today"] + pnl, 2)
            state["total_pnl"] = round(state.get("total_pnl", 0) + pnl, 2)
            
            # Move to closed
            state.setdefault("closed_trades", []).append(pos)
            state["active_positions"].pop(i)
            
            return {"pnl": pnl, "pnl_pct": pnl_pct, "position": pos}
    
    return None

def track_paper_exit_all(exit_premium, trade_direction="long"):
    """Close ALL open positions matching the direction."""
    results = []
    state = load_state()
    for pos in list(state["active_positions"]):
        if pos["direction"] == ("SELL" if trade_direction == "short" else "BUY"):
            r = track_paper_exit(pos["id"], exit_premium)
            if r:
                results.append(r)
    return results
