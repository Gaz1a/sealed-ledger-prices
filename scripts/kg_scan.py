import json, urllib.request, datetime, time
def get(u):
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent":"sealed-ledger/1.0"}), timeout=60) as r: return json.load(r)
        except Exception: time.sleep(2)
    return {}
tracked = json.load(open("tracked.json"))
have = {v["productId"] for v in tracked.values()}
out = []
for cat in (3, 85):
    for g in get(f"https://tcgcsv.com/tcgplayer/{cat}/groups").get("results", []):
        gid = g["groupId"]
        prods = [p for p in get(f"https://tcgcsv.com/tcgplayer/{cat}/{gid}/products").get("results", [])
                 if any(n in p["name"].lower() for n in ("magikarp", "gyarados")) and p["productId"] not in have]
        if not prods: continue
        rows = {}
        for r in get(f"https://tcgcsv.com/tcgplayer/{cat}/{gid}/prices").get("results", []):
            rows.setdefault(r["productId"], []).append({"sub": r.get("subTypeName"), "market": r.get("marketPrice"), "low": r.get("lowPrice")})
        for p in prods:
            num = next((e.get("value") for e in p.get("extendedData", []) if e.get("name") == "Number"), None)
            out.append({"cat": cat, "group": g["name"], "productId": p["productId"], "name": p["name"], "number": num, "rows": rows.get(p["productId"], [])})
json.dump({"generated": datetime.datetime.utcnow().isoformat(), "uncovered": out}, open("kg_scan.json", "w"), indent=1)
