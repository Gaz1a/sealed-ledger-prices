import json, urllib.request
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sealed-ledger/1.0"}), timeout=60) as r: return json.load(r)
g = 24655
ps = get(f"https://tcgcsv.com/tcgplayer/3/{g}/products")["results"]; pr = {}
for r in get(f"https://tcgcsv.com/tcgplayer/3/{g}/prices")["results"]:
    pr.setdefault(r["productId"], []).append({"sub": r.get("subTypeName"), "market": r.get("marketPrice"), "low": r.get("lowPrice"), "mid": r.get("midPrice")})
out = [{"productId": p["productId"], "name": p["name"], "number": next((e.get("value") for e in p.get("extendedData", []) if e.get("name") == "Number"), None),
        "rarity": next((e.get("value") for e in p.get("extendedData", []) if e.get("name") == "Rarity"), None), "prices": pr.get(p["productId"], [])} for p in ps]
json.dump(out, open("cri_group.json", "w"), indent=1)
