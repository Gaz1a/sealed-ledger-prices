import json
ids = json.load(open("jumbo_ids.json")); cat = {x["id"]: x for x in json.load(open("jumbo_catalogue.json"))}; pr = json.load(open("jumbo_prices.json"))["items"]
def order(j):
    en = j["lang"] == "English"
    return (0 if en and (j["year"] or 0) >= 2019 else 1 if en else 2, j["lang"], j["year"] or 0)
BASIS = {"tcgplayer": "TCGplayer market, dated snapshot = historical (not sold-verified)", "pricecharting": "estimate", "cardmarket": "asking price (EUR converted to USD at the feed rate, rate stated)"}
out = []
for k, j in sorted(cat.items(), key=lambda kv: order(kv[1])):
    v, p = ids[k], pr.get(k, {})
    r = {"id": k, "title": j["title"], "lang": j["lang"], "year": j["year"], "sheetCards": j["cards"], "sheetCheck": j["check"] or None}
    for kind in ("sealed", "card"):
        e = p.get(kind) or {}
        r[kind] = {"productId": v[kind + "Id"], "basis": v.get(kind + "Basis"), "market": e.get("market"), "date": e.get("date"), "source": e.get("source"), "history": e.get("history", [])}
        why = None
        if not v[kind + "Id"]:
            c = v.get(kind + "Candidates") or []
            why = ("ambiguous: %d candidates" % len(c)) if len(c) > 1 else (v.get("cardNote") if kind == "card" and v.get("cardNote") else "no TCGplayer listing found by exact name")
            r[kind]["candidates"] = c
            ms = [x["market"] for x in c if x.get("market") is not None]
            r[kind]["candidateRange"] = [min(ms), max(ms)] if ms else None
        elif e.get("market") is None: why = "listing found but no priced row"
        if kind == "card" and v.get("cardClosed"): why = v.get("cardNote")
        r[kind]["problem"] = why
    for kind, ik in (("card", "cardIds"), ("sealed", "sealedIds")):
        cs = (p.get(kind + "Set") or {})
        if v.get(ik):
            r[kind].update({"productIds": v[ik], "mode": v.get(kind + "Mode") or "separate", "items": cs.get("items", []), "byId": cs.get("byId", {}), "low": cs.get("low"), "high": cs.get("high"), "sum": cs.get("sum"), "date": cs.get("date"), "source": cs.get("source"), "basis": v.get(kind + "Basis")})
            miss = [x["productId"] for x in cs.get("items", []) if x["market"] is None]
            r[kind]["problem"] = ("no priced row for %s" % miss) if miss or not cs else None
    r["refs"] = v.get("refs"); r["cardmarketIds"] = v.get("cardmarket")
    r["priceBasisLabels"] = BASIS
    out.append(r)
json.dump(out, open("jumbo_report.json", "w"), indent=1)
json.dump([r for r in out if r["sealed"]["problem"] or r["card"]["problem"]], open("jumbo_unresolved.json", "w"), indent=1)
