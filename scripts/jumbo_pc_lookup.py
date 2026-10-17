"""Read-only: (a) Charizard ex SVP 196 in tcgcsv (Jumbo Cards group vs regular promos); (b) PriceCharting candidate search for h-* rows. Never prints the token."""
import json, os, re, time, urllib.request, urllib.parse
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sealed-ledger/1.0"}), timeout=60) as r: return json.load(r)
    except Exception as e: return {"error": type(e).__name__, "results": []}
out = {"tcg": [], "pc": {}}
for c in (3, 85):
    for g in get(f"https://tcgcsv.com/tcgplayer/{c}/groups")["results"]:
        n = g["name"]
        if not re.search(r"jumbo|black star promos|svp|scarlet.*violet.*promo", n, re.I): continue
        pr = {}
        for r in get(f"https://tcgcsv.com/tcgplayer/{c}/{g['groupId']}/prices")["results"]:
            pr.setdefault(r["productId"], []).append([r.get("subTypeName"), r.get("marketPrice"), r.get("lowPrice")])
        for p in get(f"https://tcgcsv.com/tcgplayer/{c}/{g['groupId']}/products")["results"]:
            if re.search(r"charizard", p["name"], re.I):
                ext = {e["name"]: e.get("value") for e in p.get("extendedData", [])}
                out["tcg"].append({"cat": c, "group": n, "gid": g["groupId"], "pid": p["productId"], "name": p["name"], "number": ext.get("Number"), "rarity": ext.get("Rarity"), "prices": pr.get(p["productId"], []), "url": p.get("url")})
T = os.environ.get("PRICECHARTING_TOKEN", "")
Q = {"h-sv151": ["pokemon 151 booster box", "pokemon japanese 151 booster box", "pokemon 151 ultra premium collection", "pokemon 151 elite trainer box"],
     "h-jp-venusaur": ["pokemon japanese venusaur", "pokemon japanese venusaur promo"],
     "h-bday-pikachu": ["pokemon birthday pikachu", "pokemon happy birthday pikachu"],
     "h-gengar-deck": ["pokemon gengar deck", "pokemon gengar starter deck", "pokemon illustrated booklet gengar"],
     "portuguese-booklet": ["pokemon portuguese booklet"]}
for k, qs in Q.items():
    for q in qs:
        time.sleep(1.1)
        d = get("https://www.pricecharting.com/api/products?" + urllib.parse.urlencode({"t": T, "q": q})) if T else {"error": "no token"}
        out["pc"].setdefault(k, {})[q] = [{"id": x.get("id"), "name": x.get("product-name"), "console": x.get("console-name"), "loose": x.get("loose-price"), "new": x.get("new-price"), "cib": x.get("cib-price")} for x in (d.get("products") or [])[:8]] if "products" in d else d
json.dump(out, open("jumbo_pc_lookup.json", "w"), indent=1)
print(len(out["tcg"]))
