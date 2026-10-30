def ema(values, n):
    out = [None] * len(values)
    if len(values) < n:
        return out
    e = sum(values[:n]) / n
    out[n - 1] = e
    k = 2 / (n + 1)
    for i in range(n, len(values)):
        e = values[i] * k + e * (1 - k)
        out[i] = e
    return out

def rsi(closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0); losses += max(-d, 0)
    ag, al = gains / n, losses / n
    def val():
        return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    out[n] = val()
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = val()
    return out

def rel_volume(volumes, i, n=20):
    """Volume at index i divided by the average of the n candles before it."""
    if i < n:
        return None
    avg = sum(volumes[i - n:i]) / n
    return None if avg <= 0 else volumes[i] / avg
