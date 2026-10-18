#!/usr/bin/env python3
"""Cardmarket trend prices for Jumbo entries -> cardmarket_jumbo.json (by ledger id). Uses the public Cardmarket price guide / product lists (same files as the booklet step).
Ids come from jumbo_ids.json['cardmarket'] ({'sealed': id, 'jumbo': id}). Prices are EUR; converted to USD at the booklet feed rate (booklets.json fx). Trend/low are Cardmarket asking-side stats, unverified."""
import json, os, datetime, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = "https://downloads.s3.cardmarket.com/productCatalog/"
def req(u): return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sealed-ledger"}), timeout=180))
ids = json.load(open(os.path.join(ROOT, "jumbo_ids.json")))
try: fx = json.load(open(os.path.join(ROOT, "booklets.json"))).get("fx")
except Exception: fx = None
if not fx:
    try: fx = req("https://api.frankfurter.app/latest?from=EUR&to=USD")["rates"]["USD"]
    except Exception: fx = None
G, N = {}, {}
try:
    G = {g["idProduct"]: g for g in req(B + "priceGuide/price_guide_6.json")["priceGuides"]}
    for f in ("productList/products_nonsingles_6.json", "productList/products_singles_6.json"):
        try: N.update({p["idProduct"]: p["name"] for p in req(B + f)["products"]})
        except Exception as e: print("names failed", f, type(e).__name__)
except Exception as e: print("price guide download failed", type(e).__name__)
items, stats = {}, {"ids": 0, "withTrend": 0, "noTrend": 0, "notInGuide": 0}
for jid, v in ids.items():
    for kind, pid in (v.get("cardmarket") or {}).items():
        g = G.get(pid); stats["ids"] += 1
        tr = (g or {}).get("trend"); lo = (g or {}).get("low")
        stats["withTrend" if tr else "notInGuide" if g is None else "noTrend"] += 1
        items.setdefault(jid, {})[kind] = {"cardmarketId": pid, "name": N.get(pid), "inPriceGuide": g is not None, "trendEUR": tr, "lowEUR": lo, "avgEUR": (g or {}).get("avg"),
            "trendUSD": round(tr * fx, 2) if tr and fx else None, "lowUSD": round(lo * fx, 2) if lo and fx else None, "fx": fx,
            "label": "Cardmarket trend (EUR converted to USD at the feed rate, shown in fx); unverified, not a sold price"}
json.dump({"generated": datetime.date.today().isoformat(), "fx": fx, "stats": stats, "items": items}, open(os.path.join(ROOT, "cardmarket_jumbo.json"), "w"), indent=1, ensure_ascii=False)
print(stats)
