"""Read-only: for each owned row's productId, record exactly what PokemonPriceTracker returns (no estimates). Also finds tcgcsv candidates for rows with no productId."""
import csv, json, os, time, datetime, urllib.request, urllib.error
K = os.environ["PPT_KEY"]
rows = list(csv.DictReader(open("owned_rows.csv")))
tr = json.load(open("tracked.json"))
def get(url, hdr=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr or {"User-Agent": "sealed-ledger/1.0"}), timeout=60) as r: return json.load(r), None
    except urllib.error.HTTPError as e: return None, f"http {e.code}"
    except Exception as e: return None, type(e).__name__
def trim(v, n=5, depth=0):
    if isinstance(v, list): return [trim(x, n, depth+1) for x in v[:n]] + ([f"...{len(v)-n} more"] if len(v) > n else [])
    if isinstance(v, dict): return {k: trim(x, n, depth+1) for k, x in v.items() if k not in ("attacks", "flavorText", "imageCdnUrl", "imageCdnUrl200", "imageCdnUrl400", "imageCdnUrl800", "imageUrl")}
    return v
pids = sorted({r["productId"] or str(tr.get(r["id"], {}).get("productId") or "") for r in rows} - {""}, key=int)
raw, stop = {}, None
for i, pid in enumerate(pids):
    d, err = get(f"https://www.pokemonpricetracker.com/api/v2/cards?tcgPlayerId={pid}&limit=1&includeHistory=true&includeEbay=true", {"Authorization": "Bearer " + K})
    if err:
        raw[pid] = {"error": err}
        if err in ("http 429", "http 402", "http 403"): stop = f"stopped at {i}: {err}"; break
    else:
        x = d.get("data", d); x = x[0] if isinstance(x, list) and x else x
        raw[pid] = {"topKeys": list(x.keys()) if isinstance(x, dict) else None, "card": trim(x) if isinstance(x, dict) else None, "meta": {k: v for k, v in d.items() if k != "data"}} if x else {"empty": True, "meta": {k: v for k, v in d.items() if k != "data"}}
    time.sleep(0.35)
json.dump({"fetchedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "stop": stop, "products": raw}, open("sales_signals_raw.json", "w"), indent=1)
# candidates for rows with no productId anywhere
need = {"h-bday-pikachu": ["birthday", "pikachu"], "h-gengar-deck": ["gengar"], "h-jp-venusaur": ["venusaur"], "h-moonlit": ["moonlit"], "h-sv151": ["151"]}
mk = {r["id"]: float(r["market"]) for r in rows}
cands = {k: [] for k in need}
for cat in (3, 85):
    gs, _ = get(f"https://tcgcsv.com/tcgplayer/{cat}/groups")
    for g in (gs or {}).get("results", []):
        ps, _ = get(f"https://tcgcsv.com/tcgplayer/{cat}/{g['groupId']}/products")
        hit = [(p, k) for p in (ps or {}).get("results", []) for k, ws in need.items() if any(w in p["name"].lower() for w in ws) and not any(e.get("name") == "Number" for e in p.get("extendedData", []))]
        if not hit: continue
        pr, _ = get(f"https://tcgcsv.com/tcgplayer/{cat}/{g['groupId']}/prices")
        m = {}
        for r in (pr or {}).get("results", []): m.setdefault(r["productId"], []).append(r.get("marketPrice"))
        for p, k in hit:
            v = [x for x in m.get(p["productId"], []) if x]
            if v and 0.6 * mk[k] <= max(v) <= 1.6 * mk[k]:
                cands[k].append({"cat": cat, "group": g["name"], "productId": p["productId"], "name": p["name"], "market": v})
json.dump({"rowMarket": {k: mk[k] for k in need}, "candidates": cands}, open("pidless_candidates.json", "w"), indent=1)
