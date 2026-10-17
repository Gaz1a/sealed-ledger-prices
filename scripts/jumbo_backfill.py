#!/usr/bin/env python3
"""Backfill jumbo history from PokemonPriceTracker (real NM daily history, 180-day window). Resumable: stops cleanly on HTTP 429 and continues next run.
Raw PPT rows -> jumbo_history_ppt.json ([date, market, marketRaw, volume]); merged into jumbo_prices.json history as [date, market] for dates BEFORE our own first scan point.
Sealed products use PPT /sealed-products (unopenedPrice history); blanks where PPT has no record."""
import json, os, time, datetime, urllib.request, urllib.error
K = os.environ["PPT_KEY"]; NOW = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
def ld(p, d): return json.load(open(p)) if os.path.exists(p) else d
ids, prices, state = ld("jumbo_ids.json", {}), ld("jumbo_prices.json", {"items": {}}), ld("jumbo_history_ppt.json", {})
cat = {x["id"]: x for x in json.load(open("jumbo_catalogue.json"))}
def key(j): en = j["lang"] == "English"; return (0 if en and (j["year"] or 0) >= 2019 else 1 if en else 2, j["year"] or 0)
order = [k for k, _ in sorted(cat.items(), key=lambda kv: key(kv[1]))]
def call(pid, kind="card"):
    path = "sealed-products" if kind == "sealed" else "cards"
    u = f"https://www.pokemonpricetracker.com/api/v2/{path}?tcgPlayerId={pid}&limit=1&includeHistory=true&days=180"
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"Authorization": "Bearer " + K}), timeout=60) as r: return json.load(r), None
    except urllib.error.HTTPError as e: return None, e.code
    except Exception as e: return None, type(e).__name__
stop = None
def fetch(pid, kind):
    global stop
    d, err = call(pid, kind)
    if err == 429 or err == 402: stop = f"http {err}"; return
    if err: state[str(pid)] = {"kind": kind, "status": f"error {err}", "fetchedAt": NOW}; return
    x = d.get("data", d); x = x[0] if isinstance(x, list) and x else x
    if not x: state[str(pid)] = {"kind": kind, "status": "no PPT record", "fetchedAt": NOW}; return
    if kind == "sealed":
        ph = x.get("priceHistory"); ph = ph if isinstance(ph, list) else (ph or {}).get("history", [])
        rows = [[str(h.get("date") or h.get("timestamp"))[:10], next((h[q] for q in ("unopenedPrice", "market", "marketPrice", "price") if isinstance(h.get(q), (int, float))), None), None, h.get("volume")] for h in ph if isinstance(h, dict) and (h.get("date") or h.get("timestamp"))]
        rows = [r for r in rows if r[1] is not None]
    else:
        nm = ((x.get("priceHistory") or {}).get("conditions") or {}).get("Near Mint") or {}
        rows = [[h["date"][:10], h.get("market"), h.get("marketRaw"), h.get("volume")] for h in nm.get("history", []) if h.get("date")]
    meta = (d.get("metadata") or {}).get("historyWindow")
    state[str(pid)] = {"kind": kind, "status": "ok" if rows else "no history rows", "fetchedAt": NOW, "window": meta, "source": ("PokemonPriceTracker /sealed-products priceHistory (unopenedPrice)" if kind == "sealed" else "PokemonPriceTracker priceHistory.conditions['Near Mint'] (market, marketRaw, volume)"), "rows": rows}
    time.sleep(0.5)
sealed = [(ids[k]["sealedId"], k) for k in order if ids[k].get("sealedId")]
for pid, _ in sealed:   # earlier probe wrongly used the /cards endpoint; retry those
    e = state.get(str(pid))
    if e and e["kind"] == "sealed" and e["status"] == "no PPT record" and "source" not in e: del state[str(pid)]
if True:
    for pid, k in sealed:
        if stop: break
        if str(pid) not in state or state[str(pid)]["status"].startswith("error"): fetch(pid, "sealed")
cards = [(ids[k]["cardId"], k) for k in order if ids[k].get("cardId")]
for pid, k in cards:
    if stop: break
    if str(pid) in state and state[str(pid)]["status"] in ("ok", "no PPT record", "no history rows"): continue
    fetch(pid, "card")
# merge into jumbo_prices history
merged = 0
for k, it in prices["items"].items():
    for kind in ("sealed", "card"):
        e = it.get(kind)
        if not e: continue
        st = state.get(str(e["productId"]))
        if not st or st["status"] != "ok": continue
        first_own = e.get("ownFrom") or min((h[0] for h in e.get("history", [])), default="9999")
        e["ownFrom"] = first_own
        ppt_pts = [[r[0], r[1]] for r in st["rows"] if r[1] is not None and r[0] < first_own]
        base = [h for h in e.get("history", []) if h[0] not in {p[0] for p in ppt_pts}]
        e["history"] = sorted(ppt_pts + base, key=lambda h: h[0])
        e["historySources"] = {"ppt": {"points": len(ppt_pts), "from": ppt_pts[0][0] if ppt_pts else None, "to": ppt_pts[-1][0] if ppt_pts else None}, "own": "daily tcgcsv scan from " + first_own}
        merged += 1
json.dump(state, open("jumbo_history_ppt.json", "w"), indent=0)
json.dump({"generated": NOW, "items": prices["items"]}, open("jumbo_prices.json", "w"), indent=1)
done = sum(1 for p, _ in cards if str(p) in state and state[str(p)]["status"] != "pending")
print(f"cards processed {done}/{len(cards)}; merged {merged}; stop={stop}")
