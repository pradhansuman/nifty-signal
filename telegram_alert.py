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

# ── Odia (ଓଡ଼ିଆ) alert translation ──
# Phrase dictionary, longest-first so longer templates match before their
# shorter fragments. Only exact English phrases are replaced; numbers, ₹,
# emoji, tickers and HTML tags pass through untouched. TG_LANG=en disables.
ODIA_PHRASES = [
    ("SCALP TARGET HIT (+10%)", "ସ୍କାଲ୍ପ୍ ଟାର୍ଗେଟ୍ ହିଟ୍ (+10%)"),
    ("SCALP STOP HIT (−10%)", "ସ୍କାଲ୍ପ୍ ଷ୍ଟପ୍ ହିଟ୍ (−10%)"),
    ("SCALP STOP HIT (-10%)", "ସ୍କାଲ୍ପ୍ ଷ୍ଟପ୍ ହିଟ୍ (-10%)"),
    ("SCALP CALL EXPIRED", "ସ୍କାଲ୍ପ୍ କଲ୍ ଏକ୍ସପାୟର୍ ହେଲା"),
    ("🔥 PERFECT SETUP", "🔥 ପରଫେକ୍ଟ ସେଟଅପ୍"),
    ("SCALP +5% — move stop to breakeven", "ସ୍କାଲ୍ପ୍ +5% — ଷ୍ଟପ୍ ବ୍ରେକ୍-ଇଭେନ୍ କୁ ଘୁଞ୍ଚାଅ"),
    ("SCALP +7% — trail stop at 50% profit", "ସ୍କାଲ୍ପ୍ +7% — 50% ଲାଭରେ ଟ୍ରେଲ୍ ଷ୍ଟପ୍"),
    ("Scalp call expired — no entry taken", "ସ୍କାଲ୍ପ୍ କଲ୍ ଏକ୍ସପାୟର୍ — କୌଣସି ଏଣ୍ଟ୍ରି ହୋଇନାହିଁ"),
    ("Scalp closed — back to WAIT", "ସ୍କାଲ୍ପ୍ ବନ୍ଦ — WAIT କୁ ଫେରିଛି"),
    ("MARKET OPEN — Morning Status", "ମାର୍କେଟ୍ ଖୋଲିଛି — ସକାଳ ସ୍ଥିତି"),
    ("Pre-Market Brief", "ପ୍ରି-ମାର୍କେଟ୍ ସାରାଂଶ"),
    ("Market Open Push Failed", "ମାର୍କେଟ୍ ଓପନ୍ ପୁଶ୍ ବିଫଳ"),
    ("Pre-Market Brief Failed", "ପ୍ରି-ମାର୍କେଟ୍ ସାରାଂଶ ବିଫଳ"),
    ("Nifty Signal connected! You'll receive alerts here.",
     "ନିଫ୍ଟି ସିଗନାଲ୍ ସଂଯୋଜିତ! ଆପଣ ଏଠାରେ ଆଲର୍ଟ ପାଇବେ।"),
    ("STOP APPROACHING", "ଷ୍ଟପ୍ ନିକଟରେ"),
    ("Near stop", "ଷ୍ଟପ୍ ନିକଟ"),
    ("Contrarian", "କଣ୍ଟ୍ରାରିୟାନ୍"),
    ("TARGET HIT", "ଟାର୍ଗେଟ୍ ହିଟ୍"),
    ("STOP HIT", "ଷ୍ଟପ୍ ହିଟ୍"),
    ("No scalp edge", "କୌଣସି ସ୍କାଲ୍ପ୍ ଧାର ନାହିଁ"),
    ("Entry ₹", "ଏଣ୍ଟ୍ରି ₹"),
    ("Target ₹", "ଟାର୍ଗେଟ୍ ₹"),
    ("Stop ₹", "ଷ୍ଟପ୍ ₹"),
    ("Premium ₹", "ପ୍ରିମିୟମ୍ ₹"),
    ("Expiry", "ଏକ୍ସପାୟରୀ"),
    ("Lot ₹", "ଲଟ୍ ₹"),
    ("Spread", "ସ୍ପ୍ରେଡ୍"),
    ("expires", "ଏକ୍ସପାୟର୍"),
    ("Stop Loss", "ଷ୍ଟପ୍ ଲସ୍"),
    ("no trade", "କୌଣସି ଟ୍ରେଡ୍ ନାହିଁ"),
    ("BANK NIFTY", "ବ୍ୟାଙ୍କ୍ ନିଫ୍ଟି"),
    ("Bank Nifty", "ବ୍ୟାଙ୍କ୍ ନିଫ୍ଟି"),
    ("BITCOIN", "ବିଟକଏନ୍"),
    ("SENSEX", "ସେନସେକ୍ସ"),
    ("NIFTY", "ନିଫ୍ଟି"),
    ("SCALP", "ସ୍କାଲ୍ପ୍"),
    ("EXPIRED", "ଏକ୍ସପାୟର୍"),
    ("BUY", "କିଣ"),
    ("SELL", "ବିକ"),
    ("Buy", "କିଣ"),
    ("Sell", "ବିକ"),
    ("LONG", "ଲଙ୍ଗ୍"),
    ("SHORT", "ସର୍ଟ"),
    ("signal", "ସିଗନାଲ୍"),
    ("reason", "କାରଣ"),
    ("trend", "ଟ୍ରେଣ୍ଡ୍"),
    ("momentum", "ମୋମେଣ୍ଟମ୍"),
    ("score", "ସ୍କୋର୍"),
    ("below", "ତଳେ"),
    ("above", "ଉପରେ"),
    ("blocked", "ଅବରୋଧିତ"),
]


def odia_translate(text):
    """Translate known English alert phrases to Odia (ଓଡ଼ିଆ). Unknown text,
    numbers, tickers, ₹, emoji and HTML tags pass through unchanged."""
    out = text
    for en, or_ in ODIA_PHRASES:
        if en in out:
            out = out.replace(en, or_)
    return out

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
    once with the text HTML-escaped. Alerts go out in Odia by default
    (TG_LANG=en switches back to English)."""
    if os.environ.get("TG_LANG", "or") == "or":
        text = odia_translate(text)
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
