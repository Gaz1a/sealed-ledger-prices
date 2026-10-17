import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _ld(n, d):
    p = os.path.join(ROOT, n)
    return json.load(open(p)) if os.path.exists(p) else d
def ids(): return _ld("jumbo_ids.json", {})
def prices(): return _ld("jumbo_prices.json", {}).get("items", {})
def sealed_pids(): return {v["sealedId"] for v in ids().values() if v.get("sealedId")}
def card_pids(): return {v["cardId"] for v in ids().values() if v.get("cardId")}
