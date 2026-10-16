"""Read-only: find Chaos Rising (and ETB promo) products + prices on tcgcsv."""
import json, urllib.request, datetime
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sealed-ledger/1.0"}), timeout=60) as r: return json.load(r)
    except Exception as e: return {"error": str(e)[:80]}
out = {"groups": [], "products": []}
gs = get("https://tcgcsv.com/tcgplayer/3/groups").get("results", [])
sel = [g for g in gs if "chaos rising" in g["name"].lower() or "mega evolution" in g["name"].lower() and "promo" in g["name"].lower() or g["name"].lower().startswith("me:") ]
out["groups"] = [{"groupId": g["groupId"], "name": g["name"], "published": g.get("publishedOn")} for g in sel]
for g in sel:
    ps = get(f"https://tcgcsv.com/tcgplayer/3/{g['groupId']}/products").get("results", [])
    pr = {}
    for r in get(f"https://tcgcsv.com/tcgplayer/3/{g['groupId']}/prices").get("results", []):
        pr.setdefault(r["productId"], []).append({"sub": r.get("subTypeName"), "market": r.get("marketPrice"), "low": r.get("lowPrice"), "mid": r.get("midPrice")})
    for p in ps:
        n = next((e.get("value") for e in p.get("extendedData", []) if e.get("name") == "Number"), None)
        nm = p["name"].lower()
        if any(w in nm for w in ("sliggoo", "jumbo ice", "cobalion", "ho-oh", "crobat", "bubbly", "nitro fire", "fennekin")) or (n or "").split("/")[0] in ("095","109","064","010","051","084","086","080"):
            out["products"].append({"group": g["name"], "groupId": g["groupId"], "productId": p["productId"], "name": p["name"], "number": n, "url": p.get("url"), "prices": pr.get(p["productId"], [])})
out["generated"] = datetime.datetime.utcnow().isoformat()
json.dump(out, open("cri_lookup.json", "w"), indent=1)
