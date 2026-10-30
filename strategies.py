from indicators import ema, rsi, rel_volume

MODES = {  # Aggressive loosens thresholds slightly; it NEVER relabels partial setups as 4/4.
    "balanced":   {"vol": 1.0, "rsi_pad": 0},
    "aggressive": {"vol": 0.9, "rsi_pad": 2},
}

def completed(candles, gran_sec, now):
    """Drop the still-forming candle. Candles: dicts t,o,h,l,c,v sorted oldest->newest."""
    return [c for c in candles if c["t"] + gran_sec <= now]

def _series(cs):
    return [c["c"] for c in cs], [c["h"] for c in cs], [c["v"] for c in cs]

def _result(name, conds, cs, rs, rv):
    return {"strategy": name, "conditions": conds, "met": sum(conds.values()), "total": len(conds),
            "confirmed": all(conds.values()), "rsi": rs, "rel_volume": rv,
            "candle_t": cs[-1]["t"], "close": cs[-1]["c"],
            "swing_low": min(c["l"] for c in cs[-10:])}

def strategy_a(c15, mode="balanced"):
    m = MODES[mode]; closes, highs, vols = _series(c15)
    if len(c15) < 35: return None
    i = len(c15) - 1; e = ema(closes, 20)[i]; r = rsi(closes)[i]; rv = rel_volume(vols, i)
    if None in (e, r, rv): return None
    conds = {"close_above_ema20": closes[i] > e,
             "rsi_48_76": 48 - m["rsi_pad"] <= r <= 76 + m["rsi_pad"],
             "rel_vol_1.15": rv >= 1.15 * m["vol"],
             "breaks_13_candle_high": closes[i] > max(highs[i - 13:i])}
    return _result("A: 15m Confirmation", conds, c15, r, rv)

def strategy_b(c5, c15, mode="balanced"):
    m = MODES[mode]; closes, highs, vols = _series(c5)
    if len(c5) < 35 or len(c15) < 25: return None
    i = len(c5) - 1; r = rsi(closes)[i]; rv = rel_volume(vols, i)
    c15c = [c["c"] for c in c15]; e15 = ema(c15c, 20)[-1]
    if None in (r, rv, e15): return None
    conds = {"breaks_12_candle_high": closes[i] > max(highs[i - 12:i]),
             "rel_vol_1.25": rv >= 1.25 * m["vol"],
             "rsi_50_78": 50 - m["rsi_pad"] <= r <= 78 + m["rsi_pad"],
             "15m_trend_up": c15c[-1] > e15}
    return _result("B: 5m Momentum Breakout", conds, c5, r, rv)

def strategy_c(c5, c15, mode="balanced"):
    m = MODES[mode]; closes, _, vols = _series(c5)
    if len(c5) < 35 or len(c15) < 25: return None
    i = len(c5) - 1; e9 = ema(closes, 9); e20 = ema(closes, 20)
    r = rsi(closes)[i]; rv = rel_volume(vols, i)
    c15c = [c["c"] for c in c15]; e15 = ema(c15c, 20)[-1]
    if None in (r, rv, e15, e9[i], e9[i - 1], e20[i]): return None
    conds = {"15m_above_ema20": c15c[-1] > e15,
             "5m_ema9_above_ema20": e9[i] > e20[i],
             "reclaims_ema9": closes[i - 1] <= e9[i - 1] and closes[i] > e9[i] and closes[i] > c5[i]["o"],
             "rsi_48_74_vol_1.0": 48 - m["rsi_pad"] <= r <= 74 + m["rsi_pad"] and rv >= 1.0 * m["vol"]}
    return _result("C: 5m Pullback Recovery", conds, c5, r, rv)

def evaluate_all(c5, c15, mode="balanced"):
    out = [strategy_a(c15, mode), strategy_b(c5, c15, mode), strategy_c(c5, c15, mode)]
    return [r for r in out if r]
