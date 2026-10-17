"""Daily from 2026-11-07: look in the Delta Reign TCGplayer group for the Mega Rayquaza ex SIR (s-rayq-sir).
Search key 138/103 is PROVISIONAL (no English scan seen). Matches by number and by name; reports ids only - does not touch tracked.json."""
import json, re, datetime, urllib.request
GROUP, START, KEY = 24831, "2026-11-07", "138/103"
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sealed-ledger/1.0"}), timeout=60) as r: return json.load(r)
    except Exception as e: return {"error": str(e)[:80], "results": []}
today = datetime.date.today().isoformat()
out = {"row": "s-rayq-sir", "searchKey": KEY, "keyStatus": "provisional (no English scan seen)", "checked": today, "startsOn": START, "matches": [], "status": ""}
if today < START:
    out["status"] = f"waiting: checks start {START}"
else:
    ps = get(f"https://tcgcsv.com/tcgplayer/3/{GROUP}/products")
    if ps.get("error") or not ps["results"]:
        out["status"] = "group not listed yet / unreachable"
    else:
        pr = {}
        for r in get(f"https://tcgcsv.com/tcgplayer/3/{GROUP}/prices")["results"]: pr.setdefault(r["productId"], []).append({"sub": r["subTypeName"], "market": r.get("marketPrice")})
        for p in ps["results"]:
            num = next((e.get("value") for e in p.get("extendedData", []) if e.get("name") == "Number"), None)
            by_num = bool(num) and num.replace(" ", "") == KEY
            by_name = "rayquaza" in p["name"].lower()
            if by_num or by_name:
                out["matches"].append({"productId": p["productId"], "name": p["name"], "number": num, "matchedBy": [m for m, ok in (("number", by_num), ("name", by_name)) if ok], "prices": pr.get(p["productId"], [])})
        out["status"] = f"{len(out['matches'])} candidate(s) - tell Gaz the id to lock" if out["matches"] else "group listed, no Rayquaza / 138/103 yet"
json.dump(out, open("srayq_watch.json", "w"), indent=1)
print(out["status"])
