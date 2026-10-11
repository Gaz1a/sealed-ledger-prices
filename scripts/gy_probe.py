import json, os, urllib.request, urllib.parse, urllib.error, datetime
out = {}
def get(url, hdr=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr or {"User-Agent": "sealed-ledger/1.0"}), timeout=40) as r: return json.load(r)
    except Exception as e: return {"error": str(e)[:100]}
gm = json.load(open("group-map.json")).get("85999")
rows = get(f"https://tcgcsv.com/tcgplayer/{gm[0]}/{gm[1]}/prices")
out["tcgcsv_rows_85999"] = [r for r in rows.get("results", []) if r.get("productId") == 85999]
prods = get(f"https://tcgcsv.com/tcgplayer/{gm[0]}/{gm[1]}/products")
out["tcgcsv_products_gyarados7"] = [{"productId": p["productId"], "name": p["name"], "url": p.get("url")} for p in prods.get("results", []) if "Gyarados" in p["name"]]
k = os.environ.get("PPT_KEY")
if k:
    d = get("https://www.pokemonpricetracker.com/api/v2/cards?tcgPlayerId=85999&limit=1&includeHistory=true", {"Authorization": "Bearer " + k})
    d = d.get("data", d); d = d[0] if isinstance(d, list) and d else d
    pr = (d or {}).get("prices") or {}
    out["ppt"] = {"market": pr.get("market"), "low": pr.get("low"), "listings": pr.get("listings"), "sellers": pr.get("sellers"), "recentSales": pr.get("recentSales"),
                  "variants": {v: {c: x.get("price") for c, x in cs.items()} for v, cs in (pr.get("variants") or {}).items()}}
t = os.environ.get("PRICECHARTING_TOKEN")
if t:
    j = get("https://www.pricecharting.com/api/products?" + urllib.parse.urlencode({"t": t, "q": "pokemon call of legends gyarados 7"}))
    out["pricecharting"] = [{"id": p.get("id"), "name": p.get("product-name"), "console": p.get("console-name"), "tcg-id": p.get("tcg-id"),
                             "ungraded": (p.get("loose-price") or 0) / 100, "psa9": (p.get("graded-price") or 0) / 100, "psa10": (p.get("manual-only-price") or 0) / 100} for p in (j.get("products") or [])]
out["generated"] = datetime.datetime.utcnow().isoformat()
json.dump(out, open("gy_probe.json", "w"), indent=1)
