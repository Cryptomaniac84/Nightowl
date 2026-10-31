import sys, time, traceback
import coinbase as cb, strategies as st, risk, state, telegram as tg, paper
VERSION = "0.2.0"

DEFAULTS = {"watchlist": ["BTC", "ETH", "SOL", "XRP", "DOGE", "SUI", "HBAR", "ZEC", "BNB", "HYPE", "LTC", "PEPE"], "quote_preference": ["USDC", "USD"], "mode": "balanced", "bankroll": 150, "position_size": 50, "round_trip_cost_pct": 0.8, "max_spread_pct": 0.65, "max_chase_pct": 0.75, "stop_min_pct": 1.0, "stop_max_pct": 5.0, "target_r_multiple": 2.5, "min_net_rr": 1.25, "quote_max_age_sec": 120, "cooldown_minutes": 90, "request_delay_sec": 0.25}

def choose(confirmed):
    """Best confirmed setup for a pair: highest estimated net reward/risk."""
    return max(confirmed, key=lambda x: x[1]["net_rr"])

def main(cfg_path="config.json", data_dir="data"):
    import json as _j
    cfg_err = None
    try:
        with open(cfg_path) as f: user = _j.load(f)
    except Exception as e:
        user, cfg_err = {}, f"config.json could not be read ({type(e).__name__}); using built-in defaults. Check it for a typo."
    cfg = {**DEFAULTS, **user}; now = time.time()
    sent = state.load(f"{data_dir}/sent.json", {}); hist = state.load(f"{data_dir}/history.json", [])
    health = {"version": VERSION, "scan_started": now, "errors": [cfg_err] if cfg_err else [], "telegram": None}
    coins, signals = [], []
    paper_recs = state.load(f"{data_dir}/paper.json", [])
    try:
        products = cb.tradable_products(); health["last_api_ok"] = time.time()
    except cb.ApiError as e:
        health["errors"].append(str(e)); state.save(f"{data_dir}/health.json", health); return 1
    for sym in cfg["watchlist"]:
        prod = next((products[(sym, q)] for q in cfg["quote_preference"] if (sym, q) in products), None)
        if not prod:
            coins.append({"symbol": sym, "status": "UNAVAILABLE", "note": "No tradable USDC/USD spot market on Coinbase"}); continue
        pid = prod["product_id"]
        try:
            c5 = st.completed(cb.candles(pid, "FIVE_MINUTE", now), 300, now)
            time.sleep(cfg["request_delay_sec"])
            c15 = st.completed(cb.candles(pid, "FIFTEEN_MINUTE", now), 900, now)
            time.sleep(cfg["request_delay_sec"])
            q = cb.quote(pid)
        except cb.ApiError as e:
            health["errors"].append(str(e)); coins.append({"symbol": sym, "pair": pid, "status": "DATA_ERROR"}); continue
        row = {"symbol": sym, "pair": pid, "bid": q["bid"], "ask": q["ask"], "setups": []}
        confirmed = []
        for res in st.evaluate_all(c5, c15, cfg["mode"]):
            plan = risk.build_plan(res, q, prod, cfg, now)
            gran = 900 if res["strategy"].startswith("A") else 300
            row["setups"].append({**res, "plan": plan})
            if res["confirmed"] and plan.get("entry"):
                paper.record_new(paper_recs, pid, res, plan, now)
            if plan["status"] == "CONFIRMED":
                confirmed.append((res, plan, gran))
        if confirmed:
            # One alert per pair: several strategies firing together is one opportunity.
            res, plan, gran = choose(confirmed)
            others = [r["strategy"] for r, _, _ in confirmed if r is not res]
            fresh = now - (res["candle_t"] + gran) <= 600   # never alert on an old candle
            if fresh and state.should_alert(sent, pid, "ALL", res["candle_t"], now, cfg["cooldown_minutes"]):
                try:   # re-read the live quote right before sending
                    plan = risk.build_plan(res, cb.quote(pid), prod, cfg, time.time())
                except cb.ApiError:
                    plan = {"status": "HELD", "reasons": ["Could not re-check the live quote"]}
                if plan["status"] != "CONFIRMED":
                    row["held"] = plan.get("reasons", [])
                else:
                    ok, info = tg.send(tg.format_alert(pid, {**res, "now": now, "gran": gran}, plan, prod["quote_currency_id"], others))
                    health["telegram"] = {"ok": ok, "info": info, "time": now}
                    if ok: sent = state.record(sent, pid, "ALL", res["candle_t"], now)
                    if not any(h["pair"] == pid and h["candle_t"] == res["candle_t"] for h in hist[-50:]):
                        hist.append({"time": now, "pair": pid, "strategy": res["strategy"], "also": others,
                                     "candle_t": res["candle_t"], "plan": plan, "alerted": ok,
                                     "conditions": res["conditions"], "rsi": res["rsi"], "rel_volume": res["rel_volume"]})
        paper.resolve(paper_recs, pid, c5, now, cfg["round_trip_cost_pct"])
        coins.append(row)
    health["scan_finished"] = time.time(); health["last_success"] = health["scan_finished"] if not health["errors"] else None
    state.save(f"{data_dir}/latest.json", {"time": now, "coins": coins})
    state.save(f"{data_dir}/paper.json", paper.trim(paper_recs))
    state.save(f"{data_dir}/sent.json", sent); state.save(f"{data_dir}/history.json", hist[-500:])
    state.save(f"{data_dir}/health.json", health); return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        try:
            state.save("data/health.json", {"version": VERSION, "scan_started": time.time(), "last_success": None, "errors": ["Scanner crashed: " + type(e).__name__ + ": " + str(e)[:200]], "telegram": None})
        except Exception: pass
        sys.exit(1)
