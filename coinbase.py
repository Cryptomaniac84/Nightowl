import json, time, urllib.request, urllib.parse, urllib.error
BASE = "https://api.coinbase.com/api/v3/brokerage/market"
GRAN = {"FIVE_MINUTE": 300, "FIFTEEN_MINUTE": 900}

class ApiError(Exception):
    pass

def get_json(path, params=None, retries=3, backoff=1.5, opener=urllib.request.urlopen):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    last = None
    for attempt in range(retries):
        try:
            with opener(urllib.request.Request(url, headers={"User-Agent": "nightowl"}), timeout=15) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            last = e
        time.sleep(backoff ** attempt)
    raise ApiError(f"{path}: {last}")

def tradable_products():
    """Only currently tradable SPOT products quoted in USDC or USD."""
    out = {}
    for p in get_json("/products", {"product_type": "SPOT"}).get("products", []):
        if p.get("status") != "online" or p.get("trading_disabled") or p.get("is_disabled"):
            continue
        if p.get("cancel_only") or p.get("limit_only") or p.get("post_only"):
            continue
        if p.get("quote_currency_id") in ("USDC", "USD"):
            out[(p["base_currency_id"], p["quote_currency_id"])] = p
    return out

def candles(product_id, granularity, now, count=100):
    sec = GRAN[granularity]
    d = get_json(f"/products/{product_id}/candles",
                 {"start": int(now - sec * count), "end": int(now), "granularity": granularity})
    cs = [{"t": int(c["start"]), "o": float(c["open"]), "h": float(c["high"]),
           "l": float(c["low"]), "c": float(c["close"]), "v": float(c["volume"])}
          for c in d.get("candles", [])]
    return sorted(cs, key=lambda c: c["t"])

def quote(product_id):
    book = get_json("/product_book", {"product_id": product_id, "limit": 1})["pricebook"]
    t = book.get("time")
    from datetime import datetime
    ts = datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() if t else 0
    return {"bid": float(book["bids"][0]["price"]), "ask": float(book["asks"][0]["price"]), "time": ts}
