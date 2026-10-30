import json, os, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
SYD = ZoneInfo("Australia/Sydney")
def fp(p):
    """Fixed-decimal price (never scientific notation), ~4 significant digits for small coins."""
    import math
    if p >= 100: return f"{p:,.2f}"
    if p >= 1: return f"{p:.4f}"
    return f"{p:.{max(4, 3 - math.floor(math.log10(p)))}f}"

def syd(ts): return datetime.fromtimestamp(ts, timezone.utc).astimezone(SYD).strftime("%a %d %b %H:%M:%S %Z")

def format_alert(pair, res, plan, quote_ccy):
    return (f"🟢 <b>CONFIRMED 4/4 — {pair}</b>\n{res['strategy']}\n\n"
        f"Time: {syd(res['now'])}\nCandle closed: {syd(res['candle_t'] + res['gran'])}\nQuote time: {syd(plan['quote_time'])}\n\n"
        f"Bid {fp(plan['bid'])} / Ask {fp(plan['ask'])} (spread {plan['spread_pct']:.2f}%)\n"
        f"Entry ≈ {fp(plan['entry'])} {quote_ccy}\nDo NOT chase above {fp(plan['max_entry'])}\n"
        f"Stop {fp(plan['stop'])} (-{plan['risk_pct']:.2f}%)\nTarget {fp(plan['target'])}\n"
        f"R/R gross {plan['gross_rr']:.1f} · est. net {plan['net_rr']:.2f}\n"
        f"RSI {res['rsi']:.1f} · Rel. volume {res['rel_volume']:.2f}x\n\n"
        f"Illustrative size {plan['position']:.0f} {quote_ccy}: est. net +{plan['profit_if_target_net']:.2f} at target, "
        f"{plan['loss_if_stop_net']:.2f} at stop (assumed costs only, not your verified fees).\n\n"
        f"⚠️ Manual trade. Nothing has been ordered. Confirm your stop/bracket on Coinbase yourself; gaps and slippage can exceed the plan.\n"
        f"https://www.coinbase.com/advanced-trade/spot/{pair}")

def send(text, token=None, chat=None, opener=urllib.request.urlopen):
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN"); chat = chat or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat: return False, "Telegram secrets not set"
    body = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}).encode()
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", body, {"Content-Type": "application/json"})
        with opener(req, timeout=15) as r: return r.status == 200, f"HTTP {r.status}"
    except Exception as e:
        return False, type(e).__name__   # never log the URL: it contains the token
