"""Gap monitor: WATCH ONLY. Compares Coinbase with Kraken for the same coin and the same quote currency.
Never trades, never uses API keys. Costs are assumptions, shown as such."""
import json, time, urllib.request, urllib.parse
from datetime import datetime
import coinbase as cb, state

KR = "https://api.kraken.com/0/public"
KMAP = {"BTC": "XBT", "DOGE": "XDG"}   # Kraken's names for these coins

def kget(path, params=None, retries=2, opener=urllib.request.urlopen):
    url = KR + path + ("?" + urllib.parse.urlencode(params) if params else "")
    last = None
    for a in range(retries):
        try:
            with opener(urllib.request.Request(url, headers={"User-Agent": "nightowl"}), timeout=15) as r:
                d = json.loads(r.read())
            if d.get("error"): raise ValueError(str(d["error"])[:100])
            return d["result"]
        except Exception as e:
            last = e; time.sleep(1.5 ** a)
    raise RuntimeError(f"kraken {path}: {type(last).__name__}")

def kraken_pairs(opener=urllib.request.urlopen):
    out = {}
    for alt, p in kget("/AssetPairs", opener=opener).items():
        if p.get("status") == "online" and "/" in p.get("wsname", ""):
            b, q = p["wsname"].split("/"); out[(b, q)] = alt
    return out

def kraken_book(alt, opener=urllib.request.urlopen):
    b = next(iter(kget("/Depth", {"pair": alt, "count": 1}, opener=opener).values()))
    a, d = b["asks"][0], b["bids"][0]
    return {"ask": float(a[0]), "ask_size": float(a[1]), "bid": float(d[0]), "bid_size": float(d[1])}

def cb_book(pid):
    pb = cb.get_json("/product_book", {"product_id": pid, "limit": 1})["pricebook"]
    t = pb.get("time")
    ts = datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() if t else 0
    return {"bid": float(pb["bids"][0]["price"]), "bid_size": float(pb["bids"][0]["size"]),
            "ask": float(pb["asks"][0]["price"]), "ask_size": float(pb["asks"][0]["size"]), "time": ts}

def compare(sym, quote, c, k, cfg, now):
    g1 = (k["bid"] / c["ask"] - 1) * 100      # buy on Coinbase, sell on Kraken
    g2 = (c["bid"] / k["ask"] - 1) * 100      # buy on Kraken, sell on Coinbase
    if g1 >= g2:
        d, gross, depth = "Buy Coinbase, sell Kraken", g1, min(c["ask"] * c["ask_size"], k["bid"] * k["bid_size"])
    else:
        d, gross, depth = "Buy Kraken, sell Coinbase", g2, min(k["ask"] * k["ask_size"], c["bid"] * c["bid_size"])
    fees = cfg["gap_fee_cb_pct"] + cfg["gap_fee_kr_pct"]
    return {"symbol": sym, "quote": quote, "direction": d, "gross_pct": round(gross, 4), "fees_pct": fees,
            "net_pct": round(gross - fees, 4), "depth_usdc": round(depth, 2), "thin": depth < cfg["position_size"],
            "stale": (now - c["time"]) > cfg["quote_max_age_sec"],
            "cb": [c["bid"], c["ask"]], "kr": [k["bid"], k["ask"]]}

def run(targets, cfg, now, data_dir, opener=urllib.request.urlopen):
    if not cfg.get("gap_enabled", True): return
    path = f"{data_dir}/gap.json"; prev = state.load(path, {})
    if now - prev.get("time", 0) < cfg.get("gap_every_sec", 280): return
    stats = prev.get("stats") or {"since": now, "checks": 0, "gross_pos": 0, "net_pos": 0, "best": None}
    out = {"time": now, "rows": [], "skipped": [], "stats": stats,
           "assumptions": {"coinbase_fee_pct": cfg["gap_fee_cb_pct"], "kraken_fee_pct": cfg["gap_fee_kr_pct"],
                           "note": "Best case: money already sitting on both exchanges, so no transfer cost or delay is included."}}
    try:
        pairs = kraken_pairs(opener)
    except Exception as e:
        out["error"] = str(e); state.save(path, out); return
    for sym, pid, quote in targets:
        alt = pairs.get((KMAP.get(sym, sym), quote))
        if not alt:
            out["skipped"].append({"symbol": sym, "why": f"Kraken has no {sym}/{quote} market"}); continue
        try:
            c = cb_book(pid); k = kraken_book(alt, opener); time.sleep(0.3)
        except Exception:
            out["skipped"].append({"symbol": sym, "why": "price fetch failed"}); continue
        r = compare(sym, quote, c, k, cfg, now); out["rows"].append(r)
        if not r["stale"]:
            stats["checks"] += 1
            if r["gross_pct"] > 0: stats["gross_pos"] += 1
            if r["net_pct"] > 0 and not r["thin"]:
                stats["net_pos"] += 1
            if not r["thin"] and (stats["best"] is None or r["net_pct"] > stats["best"]["net"]):
                stats["best"] = {"net": r["net_pct"], "symbol": sym, "direction": r["direction"], "time": now}
    out["rows"].sort(key=lambda r: -r["net_pct"]); state.save(path, out)
