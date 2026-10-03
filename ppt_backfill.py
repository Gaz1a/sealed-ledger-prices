#!/usr/bin/env python3
"""PPT backfill (paid plan): ~30 days of daily history for every item in tracked.json.
Sealed items use /sealed-products, cards (Kanto k-###, singles) use /cards.
Resumable via ppt_backfill.json. Roughly 2 credits per sealed item, 3 per card."""
import json, os, sys, time, urllib.request, urllib.error

KEY = os.environ.get("PPT_KEY", "")
if not KEY: sys.exit("PPT_KEY secret missing")
MAX_ITEMS = int(os.environ.get("MAX_ITEMS") or "700")
DAYS = int(os.environ.get("DAYS") or "180")
STATE = "ppt_backfill_180.json"
API = "https://www.pokemonpricetracker.com/api/v2/"

tracked = json.load(open("tracked.json"))
state = json.load(open(STATE)) if os.path.exists(STATE) else {}
for k, v in (("history", {}), ("not_found", []), ("card_ids", []), ("card_samples", []), ("cands", {}), ("jp_tried", [])):
    state.setdefault(k, v)
done = set(state["history"]) | set(state["not_found"])
order = sorted(tracked, key=lambda k: (k.startswith("k-"), k))
todo = [k for k in order if k not in done]
print(f"{len(done)} done, {len(todo)} to go, doing up to {MAX_ITEMS}")

def get(path, pid, lang=None):
    url = f"{API}{path}?tcgPlayerId={pid}&includeHistory=true&days={DAYS}&limit=1" + ("&maxDataPoints=200" if path == "cards" else "") + (f"&language={lang}" if lang else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KEY}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            if e.code == 429 and attempt < 2:
                time.sleep(int(e.headers.get("Retry-After") or 20)); continue
            return e.code, body
    return 429, "rate limited"

PRICE_KEYS = ("unopenedPrice", "market", "marketPrice", "price")

def series(h, variant):
    """Best-effort: turn a priceHistory blob (list, or dict keyed by variant/condition) into [[date, price]]."""
    if isinstance(h, list):
        pts = {}
        for row in h:
            if not isinstance(row, dict): continue
            d = str(row.get("date") or row.get("timestamp") or "")[:10]
            p = next((row[k] for k in PRICE_KEYS if isinstance(row.get(k), (int, float))), None)
            if d and p is not None: pts[d] = round(float(p), 2)
        return sorted(pts.items()) and [[d, p] for d, p in sorted(pts.items())]
    if isinstance(h, dict):
        keys = list(h)
        pref = [k for k in keys if variant and k == variant] + \
               [k for k in keys if k in ("Near Mint", "NM", "Normal", "Holofoil", "market")] + keys
        for k in pref:
            s = series(h[k], variant)
            if s: return s
    return []

def cands_of(h, label=""):
    """Flatten a priceHistory blob into {label: [[date, price], ...]} (every variant/condition series)."""
    out = {}
    if isinstance(h, list):
        pts = series(h, None)
        if pts: out[label or "_"] = pts
    elif isinstance(h, dict):
        for k, v in h.items():
            out.update(cands_of(v, f"{label}/{k}" if label else str(k)))
    return out

# redo cards that have no saved candidates, and retry not_found items in Japanese
cardset = set(state["card_ids"])
redo = [k for k in order if k in cardset and k not in state["cands"]]
retry_jp = [k for k in state["not_found"] if k not in state["jp_tried"]]
todo = [k for k in order if k not in done] + redo + retry_jp
n = 0
for lid in todo:
    if n >= MAX_ITEMS: break
    t = tracked[lid]; pid = t.get("productId")
    if not pid:
        state["not_found"].append(lid); continue
    is_card = lid.startswith("k-") or lid in cardset
    jp = lid in retry_jp
    if jp:
        state["jp_tried"].append(lid)
        if lid in state["not_found"]: state["not_found"].remove(lid)
    pts, sample = [], None
    combos = [("cards", None)] if is_card else [("sealed-products", None), ("cards", None), ("sealed-products", "japanese")]
    for path, lang in combos:
        code, body = get(path, pid, lang)
        if code != 200:
            print(f"STOP at {lid}: HTTP {code} {body}")
            json.dump(state, open(STATE, "w"), separators=(",", ":")); sys.exit(0)
        n += 1; time.sleep(1.0)
        data = body.get("data") or []
        if isinstance(data, dict): data = [data]   # cards endpoint returns one object
        if not data or not isinstance(data[0], dict): continue
        if path == "cards":
            sample = json.dumps(data[0])[:2500]
            pts = series(data[0].get("priceHistory"), t.get("variant"))
            c = cands_of(data[0].get("priceHistory"))
            if c: state["cands"][lid] = c
            if pts and lid not in cardset: state["card_ids"].append(lid)
        else:
            pts = series(data[0].get("priceHistory"), None)
        if pts: break
    if pts:
        state["history"][lid] = pts
    else:
        state["not_found"].append(lid)
    if sample and len(state["card_samples"]) < 3 and not redo:
        state["card_samples"].append({"id": lid, "extracted_points": len(pts), "raw": sample})
        print(f"CARD SAMPLE {lid}: extracted {len(pts)} points; raw: {sample[:900]}")

json.dump(state, open(STATE, "w"), separators=(",", ":"))
left = [k for k in order if k not in set(state["history"]) | set(state["not_found"])]
print(f"this run: {n} calls. history={len(state['history'])} not_found={len(state['not_found'])} remaining={len(left)}")
print("not_found:", state["not_found"][:40])
