#!/usr/bin/env python3
"""Pull Cardmarket's public daily price guide for the Pokemon Illustrated Booklet half decks.
Writes booklets.json: {generated, fx, decks:{name:{id, trendEUR, lowEUR, avg30EUR, avg7EUR, trendUSD, lowUSD}}}
Free public files, no API key. Prices are EUR (cheapest listings / trend), not eBay sold."""
import json, urllib.request, datetime, sys
BASE = "https://downloads.s3.cardmarket.com/productCatalog/"
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sealed-ledger"}), timeout=120) as r:
        return json.load(r)
prods = get(BASE + "productList/products_nonsingles_6.json")["products"]
hits = {p["idProduct"]: p["name"] for p in prods if "illustrated booklet" in p["name"].lower()}
print("matched products:", len(hits), file=sys.stderr)
for i, n in hits.items(): print(" ", i, n, file=sys.stderr)
guide = {g["idProduct"]: g for g in get(BASE + "priceGuide/price_guide_6.json")["priceGuides"]}
try:
    fx = get("https://api.frankfurter.app/latest?from=EUR&to=USD")["rates"]["USD"]
except Exception:
    fx = None
out = {"generated": datetime.date.today().isoformat(), "fx": fx, "decks": {}}
for i, n in hits.items():
    g = guide.get(i, {})
    d = {"id": i, "trendEUR": g.get("trend"), "lowEUR": g.get("low"), "avgEUR": g.get("avg"),
         "avg7EUR": g.get("avg7"), "avg30EUR": g.get("avg30")}
    if fx:
        for k in ("trend", "low"):
            if d[k + "EUR"] is not None: d[k + "USD"] = round(d[k + "EUR"] * fx, 2)
    out["decks"][n] = d
json.dump(out, open("booklets.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps(out, indent=1, ensure_ascii=False))
