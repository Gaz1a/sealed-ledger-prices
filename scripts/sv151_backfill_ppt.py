#!/usr/bin/env python3
"""Resumable PPT 180-day backfill for every card in the English SV 151 group (all variants, Near Mint market series). ~2 credits/card.
State: sv151_ppt_state.json {productId: {status, fetchedAt, variants:{subtype:[[date, market]]}}}. Stops cleanly on HTTP 429/402; next run continues."""
import json, os, time, datetime, urllib.request, urllib.error
K = os.environ["PPT_KEY"]; MAXC = int(os.environ.get("MAX_CALLS") or 100)
NOW = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
lines = json.load(open("sv151_lines.json"))
cards = sorted({l["productId"]: l["number"] for l in lines}.items(), key=lambda kv: kv[1])
st = json.load(open("sv151_ppt_state.json")) if os.path.exists("sv151_ppt_state.json") else {}
n = 0; stop = None
for pid, num in cards:
    e = st.get(str(pid))
    if e and e["status"] in ("ok", "no PPT record", "no history rows"): continue
    if n >= MAXC: break
    u = f"https://www.pokemonpricetracker.com/api/v2/cards?tcgPlayerId={pid}&limit=1&includeHistory=true&days=180"
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"Authorization": "Bearer " + K}), timeout=60) as r: d = json.load(r)
    except urllib.error.HTTPError as ex:
        if ex.code in (429, 402): stop = f"http {ex.code}"; break
        st[str(pid)] = {"status": f"error {ex.code}", "fetchedAt": NOW}; n += 1; continue
    except Exception as ex:
        st[str(pid)] = {"status": f"error {type(ex).__name__}", "fetchedAt": NOW}; n += 1; continue
    n += 1; time.sleep(0.6)
    x = d.get("data", d); x = x[0] if isinstance(x, list) and x else x
    if not x: st[str(pid)] = {"status": "no PPT record", "fetchedAt": NOW}; continue
    vs = ((x.get("priceHistory") or {}).get("variants") or {})
    out = {}
    for sub, conds in vs.items():
        rows = ((conds or {}).get("Near Mint") or {}).get("history") or []
        pts = [[h["date"][:10], h["market"]] for h in rows if h.get("date") and isinstance(h.get("market"), (int, float))]
        if pts: out[sub] = pts
    st[str(pid)] = {"status": "ok" if out else "no history rows", "fetchedAt": NOW, "variants": out}
json.dump(st, open("sv151_ppt_state.json", "w"), separators=(",", ":"))
fin = sum(1 for p, _ in cards if st.get(str(p), {}).get("status") in ("ok", "no PPT record", "no history rows"))
print(f"calls {n}; cards finished {fin}/{len(cards)}; stop={stop}")
