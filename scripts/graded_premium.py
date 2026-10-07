#!/usr/bin/env python3
"""Post-process graded.json: add rawMarket, PSA 9/10 reference, premium = PSA10 / raw, and flags. No figures are invented:
missing data stays null."""
import json, os, datetime
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
g = load("graded.json", {"cards": {}})
watch = {str(w["productId"]): w for w in load("graded_watch.json", [])}
prices = load("prices.json", {}).get("prices", {})
sg = {}
for c in load("untracked_singles.json", {}).get("cards", []): sg.setdefault(c["productId"], c)
pc = load("pricecharting.json", {}).get("cards", {})
n10 = 0
for cid, c in g.get("cards", {}).items():
    w = watch.get(str(c.get("productId")), {})
    raw = (prices.get(cid) or {}).get("market") or w.get("rawMarket") or (sg.get(c.get("productId")) or {}).get("market")
    gr = c.get("grades") or {}
    p10, p9 = gr.get("psa10") or {}, gr.get("psa9") or {}
    c["rawMarket"] = raw
    c["psa10"] = {"median": p10.get("median"), "p7": p10.get("p7"), "n": p10.get("n")} if p10 else None
    c["psa9"] = {"median": p9.get("median"), "p7": p9.get("p7"), "n": p9.get("n")} if p9 else None
    prem = round(p10["median"] / raw, 2) if p10.get("median") and raw else None
    c["premium"] = prem
    c["premiumFlag"] = None if prem is None else ("below_2x" if prem < 2 else "above_6x" if prem > 6 else "ok")
    pcc = pc.get(cid) or {}
    c["editionMatched"] = pcc.get("editionMatched") if pcc.get("matched") else None
    c["premiumSource"] = "ppt_ebay"
    if pcc.get("matched") and pcc.get("editionMatched") and pcc.get("psa10") and pcc.get("ungraded"):
        c["pricecharting"] = {"ungraded": pcc["ungraded"], "psa9": pcc.get("psa9"), "psa10": pcc["psa10"], "asOf": pcc.get("asOf")}
        prem = round(pcc["psa10"] / pcc["ungraded"], 2)
        c["premium"] = prem
        c["premiumFlag"] = "below_2x" if prem < 2 else "above_6x" if prem > 6 else "ok"
        c["premiumSource"] = "pricecharting (edition matched)"
    elif pcc.get("matched") and pcc.get("editionMatched") is False:
        c["premiumFlag"] = "edition_mismatch" if c.get("premiumFlag") == "above_6x" else c.get("premiumFlag")
    c["thinSales"] = bool(p10 and (p10.get("n") or 0) < 5)
    n10 += prem is not None
g["generated"] = datetime.date.today().isoformat()
g["source"] = {"graded": "PokemonPriceTracker v2 includeEbay salesByGrade (eBay sold listings; existing repo route)",
               "raw": "TCGplayer market via prices.json / untracked_singles.json",
               "premium": "PSA 10 median sale / raw market",
               "pricechartingTokenPresent": bool(os.environ.get("PRICECHARTING_TOKEN")),
               "note": "PriceCharting not used; eBay sold data via PPT is what the repo already uses"}
json.dump(g, open("graded.json", "w"), indent=1)
print(len(g["cards"]), "cards;", n10, "with premium")
