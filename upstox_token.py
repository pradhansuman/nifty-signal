#!/usr/bin/env python3
"""
Shared Upstox token manager — kills the daily token chore.

Priority:
1. UPSTOX_ANALYTICS_TOKEN  — 1-year read-only token (Upstox dashboard → API Access).
                              Best for this dashboard (all endpoints read-only).
2. UPSTOX_REFRESH_TOKEN    — OAuth auto-refresh: silently swaps for a fresh access
                              token when the daily one dies (3:30 AM IST expiry),
                              using grant_type=refresh_token. Requires CLIENT_ID/SECRET.
3. UPSTOX_ACCESS_TOKEN     — fallback (manual daily paste, old way).

Config file: .openclaw/tmp/upstox_config.py  (git-ignored)
"""
import importlib.util
import os
import time
import urllib.request
import urllib.parse
import json

WORKSPACE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(WORKSPACE, ".openclaw", "tmp", "upstox_config.py")

_refresh_lock = 0  # avoid thundering herd across threads


def _load_cfg():
    cfg = {}
    if os.path.exists(CFG):
        spec = importlib.util.spec_from_file_location("upstox_config", CFG)
        m = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(m)
        except Exception:
            return cfg
        for k in dir(m):
            if k.isupper():
                cfg[k] = getattr(m, k)
    return cfg


def _save_cfg(cfg):
    lines = []
    for k, v in cfg.items():
        lines.append(f"{k} = {json.dumps(v)}")
    with open(CFG, "w") as f:
        f.write("\n".join(lines) + "\n")


def _expired(access_exp):
    """Upstox access tokens die at 3:30 AM IST daily; refresh a bit early (3:15 AM)."""
    if not access_exp:
        return True
    try:
        exp = float(access_exp)
        return time.time() >= exp - 900
    except (TypeError, ValueError):
        return True


def _next_330_ist():
    """Epoch seconds of next 3:30 AM IST."""
    import datetime
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now = datetime.datetime.now(ist)
    nxt = now.replace(hour=3, minute=30, second=0, microsecond=0)
    if nxt <= now:
        nxt += datetime.timedelta(days=1)
    return nxt.timestamp()


def _refresh_access(cfg):
    """Exchange refresh token for a fresh access token (+ rotating refresh token)."""
    global _refresh_lock
    if time.time() - _refresh_lock < 60:
        return None, cfg  # someone else just refreshed
    _refresh_lock = time.time()
    rt = cfg.get("UPSTOX_REFRESH_TOKEN", "")
    cid = cfg.get("UPSTOX_CLIENT_ID", "")
    sec = cfg.get("UPSTOX_CLIENT_SECRET", "")
    if not (rt and cid and sec):
        return None, cfg
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": rt,
        "client_id": cid,
        "client_secret": sec,
    }).encode()
    req = urllib.request.Request("https://api.upstox.com/v2/oauth/token", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        at = data.get("access_token", "")
        nrt = data.get("refresh_token", "") or rt
        if at:
            cfg["UPSTOX_ACCESS_TOKEN"] = at
            cfg["UPSTOX_REFRESH_TOKEN"] = nrt
            cfg["UPSTOX_ACCESS_EXPIRY"] = _next_330_ist()
            _save_cfg(cfg)
            return at, cfg
    except Exception:
        pass
    return None, cfg


def _real(v):
    """Treat empty/placeholder values as missing."""
    return v and str(v).strip() not in ("", "PASTE_HERE")


def get_token():
    """Return the best available Upstox token (str) or empty string."""
    cfg = _load_cfg()

    # 1) Analytics token — 1 year, read-only, no renewal ever needed
    atok = cfg.get("UPSTOX_ANALYTICS_TOKEN", "")
    if _real(atok):
        return atok

    # 2) Auto-refresh flow
    acc = cfg.get("UPSTOX_ACCESS_TOKEN", "")
    if _real(cfg.get("UPSTOX_REFRESH_TOKEN")) and _expired(cfg.get("UPSTOX_ACCESS_EXPIRY")):
        acc, cfg = _refresh_access(cfg)

    # 3) Fallback
    return acc if _real(acc) else ""


if __name__ == "__main__":
    t = get_token()
    print("token:", (t[:10] + "...") if t else "EMPTY")
