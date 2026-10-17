"""Read-only lookup for coverage gaps: names/prices for given productIds, name searches for unresolved ledger rows, PPT history-window probe on jumbo cards."""
import json, os, re, urllib.request, datetime
def get(u, h=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=h or {"User-Agent": "sealed-ledger/1.0"}), timeout=60) as r: return json.load(r)
    except Exception as e: return {"error": str(e)[:80]}
PIDS = {603428, 571832, 637384, 565236, 282401, 587728, 575042, 565248, 672733}
SEARCH = {"moonlit": r"moonlit", "clefable": r"clefable", "pc_etb": r"pok.mon center", "upc": r"ultra.premium", "destined": r"destined rivals", "perfect": r"perfect order"}
out = {"pids": {}, "search": {k: [] for k in SEARCH}, "groups": {}}
for c in (3, 85):
    for g in get(f"https://tcgcsv.com/tcgplayer/{c}/groups").get("results", []):
        nm = g["name"].lower()
        interesting = ("30th" in nm and "celebration" in nm) or "destined" in nm or "perfect" in nm or "por" in nm
        ps = get(f"https://tcgcsv.com/tcgplayer/{c}/{g['groupId']}/products").get("results", [])
        hit = [p for p in ps if p["productId"] in PIDS or any(re.search(rx, p["name"], re.I) for k, rx in SEARCH.items() if k in ("moonlit", "clefable")) or (interesting and any(re.search(rx, p["name"], re.I) for rx in (SEARCH["pc_etb"], SEARCH["upc"], r"booster box|elite trainer|display|box|collection")))]
        if not hit: continue
        pr = {}
        for r in get(f"https://tcgcsv.com/tcgplayer/{c}/{g['groupId']}/prices").get("results", []):
            pr.setdefault(r["productId"], []).append({"sub": r.get("subTypeName"), "market": r.get("marketPrice"), "low": r.get("lowPrice")})
        for p in hit:
            n = next((e.get("value") for e in p.get("extendedData", []) if e.get("name") == "Number"), None)
            rec = {"cat": c, "group": g["name"], "groupId": g["groupId"], "productId": p["productId"], "name": p["name"], "number": n, "prices": pr.get(p["productId"], [])}
            if p["productId"] in PIDS: out["pids"][str(p["productId"])] = rec
            else: out["search"].setdefault("hits", []).append(rec)
# PPT history window probe (jumbo cards we hold)
k = os.environ.get("PPT_KEY"); probe = {}
if k:
    for pid in (704880, 692115):
        for q in ("&includeHistory=true", "&includeHistory=true&days=180", "&includeHistory=true&historyDays=180", "&includeHistory=true&maxDataPoints=400"):
            d = get(f"https://www.pokemonpricetracker.com/api/v2/cards?tcgPlayerId={pid}&limit=1{q}", {"Authorization": "Bearer " + k})
            meta = {x: v for x, v in d.items() if x != "data"} if isinstance(d, dict) else d
            x = d.get("data") if isinstance(d, dict) else None; x = x[0] if isinstance(x, list) and x else x
            ph = (x or {}).get("priceHistory") or {}
            nm = (ph.get("conditions") or {}).get("Near Mint") or {}
            probe[f"{pid}{q}"] = {"meta": meta, "found": bool(x), "nmPoints": len(nm.get("history", [])) if nm else None, "first": (nm.get("history") or [{}])[0].get("date") if nm else None, "totalDataPoints": ph.get("totalDataPoints")}
out["pptProbe"] = probe
json.dump(out, open("gap_lookup.json", "w"), indent=1)
