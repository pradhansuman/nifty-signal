#!/usr/bin/env python3
"""
Telegram alert pusher — sends dashboard alerts to your phone.
Config (git-ignored): .openclaw/tmp/telegram_config.py
    TELEGRAM_BOT_TOKEN = "123456:ABC..."
    TELEGRAM_CHAT_ID = "123456789"
No config = no-op (safe). Uses Bot API sendMessage.
"""
import os, json, requests
from datetime import datetime

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".openclaw", "tmp", "telegram_config.py")
API = "https://api.telegram.org/bot{token}/sendMessage"

_config = None


def _load_config():
    global _config
    if _config is not None:
        return _config
    _config = {"token": os.environ.get("TELEGRAM_BOT_TOKEN", ""), "chat_id": os.environ.get("TELEGRAM_CHAT_ID", "")}
    if os.path.exists(CONFIG_PATH):
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("telegram_config", CONFIG_PATH)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            _config["token"] = getattr(m, "TELEGRAM_BOT_TOKEN", _config["token"])
            _config["chat_id"] = str(getattr(m, "TELEGRAM_CHAT_ID", _config["chat_id"]))
        except Exception:
            pass
    return _config


def is_configured():
    c = _load_config()
    return bool(c["token"] and c["chat_id"])


def send_telegram(text, parse_mode="HTML"):
    """Send a message. Returns (ok, error). No-op if not configured.
    Keeps intentional <b> formatting, but if raw '<'/'>' in the payload (e.g.
    gate reasons like 'adx 13 < 25') breaks Telegram's entity parser, retries
    once with the text HTML-escaped."""
    c = _load_config()
    if not c["token"] or not c["chat_id"]:
        return False, "Telegram not configured (need bot token + chat id)"
    try:
        import html as _html
        payload = {"chat_id": c["chat_id"], "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
        r = requests.post(API.format(token=c["token"]), json=payload, timeout=10)
        if r.status_code == 200 and r.json().get("ok"):
            return True, None
        if "can't parse entities" in r.text:
            # raw < / > broke HTML mode → resend escaped (tags become literal text)
            payload = dict(payload, text=_html.escape(text))
            r = requests.post(API.format(token=c["token"]), json=payload, timeout=10)
            if r.status_code == 200 and r.json().get("ok"):
                return True, None
        return False, r.text[:200]
    except Exception as e:
        return False, str(e)[:200]


def get_chat_id_from_updates():
    """Auto-discover chat id: user messages the bot once, we read it."""
    c = _load_config()
    if not c["token"]:
        return None, "No bot token configured"
    try:
        r = requests.get(f"https://api.telegram.org/bot{c['token']}/getUpdates", timeout=10)
        if r.status_code != 200:
            return None, r.text[:200]
        updates = r.json().get("result", [])
        for u in reversed(updates):
            msg = u.get("message") or u.get("edited_message") or {}
            cid = msg.get("chat", {}).get("id")
            if cid:
                return cid, None
        return None, "No messages found — message your bot once (e.g. /start) then retry"
    except Exception as e:
        return None, str(e)[:200]


def save_config(token=None, chat_id=None):
    """Persist config to disk."""
    c = _load_config()
    if token: c["token"] = token
    if chat_id: c["chat_id"] = str(chat_id)
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        f.write(f'TELEGRAM_BOT_TOKEN = "{c["token"]}"\n')
        f.write(f'TELEGRAM_CHAT_ID = "{c["chat_id"]}"\n')
    global _config
    _config = c
    return c


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "chatid":
        cid, err = get_chat_id_from_updates()
        print(f"Chat ID: {cid}" if cid else f"Error: {err}")
    else:
        ok, err = send_telegram("✅ Telegram alerts connected! You'll get Nifty signals here.")
        print("Sent OK" if ok else f"Failed: {err}")
