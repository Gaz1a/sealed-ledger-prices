#!/usr/bin/env python3
"""Build auction_sheet.json for the ledger's Buy tab from goldin.json + fanatics.json.
Budget (data/auction_budget.json): a pick is kept only if its max bid lands at or under perLotAllIn all-in
(hammer + buyer's premium + est. shipping). The page applies the monthly budget against what Gaz has spent."""
import json, os, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load(f, d=None):
    try: return json.load(open(os.path.join(ROOT, f)))
    except Exception: return d if d is not None else {}
bud = load("data/auction_budget.json", {"perLotAllIn": 500, "monthly": 500})
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
picks, dropped = [], 0
for house, f, sf in (("Goldin", "goldin.json", "goldin_sold.json"), ("Fanatics", "fanatics.json", "fanatics_sold.json")):
    d = load(f)
    for k in ("wants", "sealed"):
        for p in d.get(k, []):
            if p.get("maxBid") is None: continue
            if k == "wants" and not p.get("top"): continue
            if (p.get("ends") or "") < now: continue
            at_max = round(p["maxBid"] * (1 + p["buyerPremiumPct"] / 100) + p["shipEst"], 2)
            if at_max > bud["perLotAllIn"]: dropped += 1; continue
            picks.append({"house": house, "bucket": k, "title": p["title"], "url": p["url"], "tcgUrl": p.get("tcgUrl"),
                          "wantId": p.get("wantId"), "what": p.get("product") or p.get("grade"), "units": p.get("units"),
                          "value": p["value"], "currentBid": p["currentBid"], "bids": p["bids"], "allInNow": p["allInNow"],
                          "maxBid": p["maxBid"], "allInAtMax": at_max, "premiumPct": p["buyerPremiumPct"], "shipEst": p["shipEst"],
                          "ends": p["ends"], "flag": p.get("flag")})
# one lot per want (the cheapest right now), and the 12 best sealed lots within the cap
best = {}
for p in [p for p in picks if p["bucket"] == "wants"]:
    k = p["wantId"] or p["url"]
    if k not in best or p["allInNow"] < best[k]["allInNow"]: best[k] = p
sealed = sorted([p for p in picks if p["bucket"] == "sealed"], key=lambda p: (p.get("flag") != "overlooked", -(p["value"] - p["allInAtMax"])))[:12]
picks = sorted(best.values(), key=lambda p: -(p["value"] - p["allInAtMax"])) + sealed
med = {h: (load(sf).get("medianPctOfValue")) for h, sf in (("Goldin", "goldin_sold.json"), ("Fanatics", "fanatics_sold.json"))}
out = {"generated": now, "budget": bud, "picks": picks, "droppedOverCap": dropped,
       "scans": {"Goldin": load("goldin.json").get("generated"), "Fanatics": load("fanatics.json").get("generated")},
       "medianPctOfValue": med,
       "rule": "Max bid = highest hammer bid keeping hammer + premium + est. shipping at or under 85% of value; only lots whose max bid stays within the per-lot budget all-in."}
json.dump(out, open(os.path.join(ROOT, "auction_sheet.json"), "w"), indent=1, ensure_ascii=False)
print(f"{len(picks)} picks kept, {dropped} over the ${bud['perLotAllIn']} per-lot cap")
