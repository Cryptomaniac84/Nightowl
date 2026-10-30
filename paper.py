"""Paper-trade research: hypothetical outcomes only. Never real trades, never real profit."""

def gran_of(strategy):
    return 900 if strategy.startswith("A") else 300

def record_new(recs, pair, res, plan, now):
    rid = f"{pair}|{res['strategy'][0]}|{res['candle_t']}"
    if any(r["id"] == rid for r in recs[-600:]):
        return False
    ok = plan["status"] == "CONFIRMED"
    recs.append({"id": rid, "pair": pair, "strategy": res["strategy"], "candle_t": res["candle_t"],
                 "created": now, "group": "allowed" if ok else "blocked",
                 "blocked_by": [] if ok else plan.get("reasons", []),
                 "entry": plan["entry"], "stop": plan["stop"], "target": plan["target"], "outcome": "open"})
    return True

def _close(r, outcome, exit_price, now, cost_pct):
    r["outcome"] = outcome; r["exit"] = exit_price; r["resolved"] = now
    r["net_pct"] = round((exit_price / r["entry"] - 1) * 100 - cost_pct, 3)

def resolve(recs, pair, c5, now, cost_pct, max_age=28800):
    """c5: completed 5-minute candles, oldest first. Conservative rules:
    - stop wins if stop and target are touched in the same candle
    - the candle containing the entry can trigger the stop but never the target
    - missing history -> 'unknown', never a made-up win"""
    n = 0
    for r in recs:
        if r["pair"] != pair or r["outcome"] != "open":
            continue
        start = r["candle_t"] + (900 if r["strategy"].startswith("A") else 300)
        if c5 and c5[0]["t"] > start:
            r["outcome"] = "unknown"; r["resolved"] = now; n += 1; continue
        later = [c for c in c5 if c["t"] >= start]
        for c in later:
            if c["l"] <= r["stop"]:
                _close(r, "loss", r["stop"], now, cost_pct); break
            if c["t"] > start and c["h"] >= r["target"]:
                _close(r, "win", r["target"], now, cost_pct); break
        if r["outcome"] == "open" and now - r["created"] > max_age:
            _close(r, "timeout", later[-1]["c"] if later else r["entry"], now, cost_pct)
        if r["outcome"] != "open":
            n += 1
    return n

def trim(recs, keep=2000):
    return recs[-keep:]
