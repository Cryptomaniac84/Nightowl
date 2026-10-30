def build_plan(res, quote, product, cfg, now):
    """Turn a strategy result + live quote into a trade plan with explicit block reasons."""
    reasons = []
    if not res["confirmed"]:
        failed = [k for k, v in res["conditions"].items() if not v]
        return {"status": "WATCH" if res["met"] >= 2 else "WAIT", "met": f'{res["met"]}/{res["total"]}',
                "reasons": ["Not confirmed. Unmet: " + ", ".join(failed)]}
    bid, ask = quote["bid"], quote["ask"]
    age = now - quote["time"]
    if age > cfg["quote_max_age_sec"]:
        reasons.append(f"Quote is stale ({age:.0f}s old, limit {cfg['quote_max_age_sec']}s)")
    if bid <= 0 or ask <= 0 or ask < bid:
        reasons.append("Invalid bid/ask"); return _blocked(reasons)
    spread = (ask - bid) / ((ask + bid) / 2) * 100
    if spread > cfg["max_spread_pct"]:
        reasons.append(f"Spread {spread:.2f}% exceeds {cfg['max_spread_pct']}%")
    entry = ask
    chase = (entry / res["close"] - 1) * 100
    if chase > cfg["max_chase_pct"]:
        reasons.append(f"Price already {chase:.2f}% above signal close (max {cfg['max_chase_pct']}%)")
    risk_pct = (entry - res["swing_low"]) / entry * 100
    risk_pct = max(risk_pct, cfg["stop_min_pct"])  # widen too-tight stops to the minimum
    if risk_pct > cfg["stop_max_pct"]:
        reasons.append(f"Stop distance {risk_pct:.2f}% exceeds {cfg['stop_max_pct']}%")
    cost = cfg["round_trip_cost_pct"]
    reward_pct = risk_pct * cfg["target_r_multiple"]
    net_rr = (reward_pct - cost) / (risk_pct + cost)
    if net_rr < cfg["min_net_rr"]:
        reasons.append(f"Net reward/risk {net_rr:.2f} below {cfg['min_net_rr']} after {cost}% costs")
    size = cfg["position_size"]
    if size < float(product.get("quote_min_size") or 0) or size / entry < float(product.get("base_min_size") or 0):
        reasons.append("Position is below Coinbase minimum order size")
    stop = entry * (1 - risk_pct / 100); target = entry * (1 + reward_pct / 100)
    plan = {"entry": entry, "max_entry": res["close"] * (1 + cfg["max_chase_pct"] / 100),
            "stop": stop, "target": target, "spread_pct": spread, "risk_pct": risk_pct,
            "gross_rr": cfg["target_r_multiple"], "net_rr": net_rr, "position": size,
            "loss_if_stop_net": -(size * (risk_pct + cost) / 100),
            "profit_if_target_net": size * (reward_pct - cost) / 100,
            "bid": bid, "ask": ask, "quote_time": quote["time"], "reasons": reasons}
    plan["status"] = "BLOCKED" if reasons else "CONFIRMED"
    return plan

def _blocked(reasons):
    return {"status": "BLOCKED", "reasons": reasons}
