#!/usr/bin/env python3
"""Keep a registry of every Goldin / Fanatics pick (data/auction_picks.json) and record how each one closed
(auction_results.json), so the ledger can log final prices and we can see whether the max bids would have won."""
import json, os, sys, time, datetime, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.datetime.now(datetime.timezone.utc)
REG, RES = os.path.join(ROOT, "data/auction_picks.json"), os.path.join(ROOT, "auction_results.json")

def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

reg, res = load(REG, {}), load(RES, {"results": {}})
for f in ("goldin.json", "fanatics.json"):
    d = load(os.path.join(ROOT, f), {})
    for k in ("wants", "sealed"):
        for p in d.get(k, []):
            if not p.get("top"): continue
            e = reg.setdefault(p["url"], {"source": p.get("source", "goldin"), "lotId": p.get("lotId"), "title": p["title"],
                                          "firstSeen": d.get("generated"), "bucket": k, "wantId": p.get("wantId")})
            e.update(ends=p.get("ends"), maxBid=p.get("maxBid"), value=p.get("value"), buyerPremiumPct=p.get("buyerPremiumPct"),
                     shipEst=p.get("shipEst"), lastSeen=d.get("generated"))

def http(u, data=None, h=None):
    with urllib.request.urlopen(urllib.request.Request(u, data=data, headers=h or {"User-Agent": "Mozilla/5.0"}), timeout=40) as r:
        return json.loads(r.read())

fan = None
done = 0
for url, e in reg.items():
    if url in res["results"] and res["results"][url].get("status") in ("sold", "unsold"): continue
    if not e.get("ends") or e["ends"] > (NOW - datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"): continue
    r = {"source": e["source"], "title": e["title"], "maxBid": e.get("maxBid"), "value": e.get("value"), "wantId": e.get("wantId"), "checked": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        if e["source"] == "goldin":
            lot = http("https://lot-retrieval-bidder.api.prod.goldin.com/api/meta_slug/" + url.rsplit("/", 1)[1],
                       h={"User-Agent": "Mozilla/5.0", "Origin": "https://goldin.co", "Referer": "https://goldin.co/"}).get("lot") or {}
            st = lot.get("status") or ""
            hammer = lot.get("final_price") or (lot.get("current_price") if "Sold" in st else None)
            r.update(status="sold" if "Sold" in st else ("unsold" if st.startswith("Completed") else "unknown"),
                     hammer=hammer, ended=lot.get("end_timestamp"), bids=lot.get("number_of_bids"))
            bp = float(lot.get("buyer_premium") or e.get("buyerPremiumPct") or 22)
        else:
            if fan is None:
                import fanatics_scan as fs; fan = fs.Search()
            h = (fan.multi([{"query": "", "hitsPerPage": 1, "filters": f'objectID:"{e["lotId"]}"'}])[0].get("hits") or [{}])[0]
            st = h.get("status") or ""
            r.update(status="sold" if st == "Sold" else ("unknown" if not st or st == "Live" else "unsold"),
                     hammer=h.get("currentPrice"), bids=h.get("bidCount"),
                     ended=datetime.datetime.fromtimestamp(h.get("auctionEndDatetime") or 0, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            bp = float(e.get("buyerPremiumPct") or 20)
        if r.get("hammer"):
            r["allIn"] = round(float(r["hammer"]) * (1 + bp / 100) + float(e.get("shipEst") or 0), 2)
            r["pctOfValue"] = round(r["allIn"] / e["value"], 2) if e.get("value") else None
            r["maxBidWouldWin"] = bool(e.get("maxBid") and float(r["hammer"]) <= float(e["maxBid"]))
    except Exception as x:
        r.update(status="unknown", error=type(x).__name__)
    res["results"][url] = r; done += 1; time.sleep(0.5)

cut = (NOW - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
reg = {u: e for u, e in reg.items() if (e.get("ends") or "9") >= cut}
res["results"] = {u: r for u, r in res["results"].items() if u in reg}
res["generated"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
won = [r for r in res["results"].values() if r.get("maxBidWouldWin")]
res["summary"] = {"closed": sum(1 for r in res["results"].values() if r.get("status") in ("sold", "unsold")), "maxBidWouldHaveWon": len(won)}
os.makedirs(os.path.dirname(REG), exist_ok=True)
json.dump(reg, open(REG, "w"), indent=1, ensure_ascii=False)
json.dump(res, open(RES, "w"), indent=1, ensure_ascii=False)
print(f"registry {len(reg)}, newly checked {done}, summary {res['summary']}")
