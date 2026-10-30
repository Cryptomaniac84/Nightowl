import json, os
def load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except (OSError, ValueError): return default
def save(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(obj, f, indent=1)
    os.replace(tmp, path)

def should_alert(sent, pair, strategy, candle_t, now, cooldown_min):
    """sent: {key: ts}. Blocks the same candle and anything inside the cooldown window."""
    if f"{pair}|{strategy}|{candle_t}" in sent: return False
    prior = [v for k, v in sent.items() if k.startswith(f"{pair}|{strategy}|")]
    return not prior or now - max(prior) >= cooldown_min * 60

def record(sent, pair, strategy, candle_t, now):
    sent[f"{pair}|{strategy}|{candle_t}"] = now
    cutoff = now - 7 * 86400
    return {k: v for k, v in sent.items() if v >= cutoff}
