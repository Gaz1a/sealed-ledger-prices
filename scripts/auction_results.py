#!/usr/bin/env python3
"""Keep a registry of every Goldin / Fanatics pick (data/auction_picks.json) and record how each one closed
(auction_results.json), so the ledger can log final prices and we can see whether the max bids would have won."""
import json, os, sys, time, datetime, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.datetime.now(datetime.timezone.utc)
REG, RES = os.path.join(ROOT, "data/auction_picks.json"), os.path.join(ROOT, "auction_results.json")
COMPS = os.path.join(ROOT, "data/auction_comps.json")   # every finished lot we ever found, by product: Gaz's own market data point
import re

from auction_keys import comp_key

def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

reg, res = load(REG, {}), load(RES, {"results": {}})
for f in ("goldin.json", "fanatics.json"):
    d = load(os.path.join(ROOT, f), {})
    picks = {p["url"]: (k, p) for k in ("wants", "sealed") for p in d.get(k, [])}
    # every lot we could identify (deal or not), so its final price becomes market data
    for t in d.get("tracked", []) + [dict(p, key=comp_key(p)) for k, p in picks.values()]:
        if not t.get("key"): continue
        e = reg.setdefault(t["url"], {"source": t.get("source", "goldin"), "lotId": t.get("lotId"), "title": t["title"], "firstSeen": d.get("generated")})
        e.update(ends=t.get("ends"), key=t["key"], units=t.get("units") or 1, lastSeen=d.get("generated"),
                 buyerPremiumPct=t.get("buyerPremiumPct") or e.get("buyerPremiumPct"))
        if t["url"] in picks:
            k, p = picks[t["url"]]
            e.update(bucket=k, wantId=p.get("wantId"), pick=bool(p.get("top")), maxBid=p.get("maxBid"), value=p.get("value"), shipEst=p.get("shipEst"))

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
    r.update(key=e.get("key"), units=e.get("units") or 1, url=url)
    res["results"][url] = r; done += 1; time.sleep(0.3)

comps = load(COMPS, {})
def add_comp(key, url, d, house, allin, hammer, units, bids, title):
    lst = comps.setdefault(key, [])
    if any(c.get("url") == url for c in lst): return
    lst.append({"d": (d or "")[:10], "h": house, "a": round(float(allin), 2), "hm": hammer, "u": units or 1, "b": bids, "t": (title or "")[:90], "url": url})
    lst.sort(key=lambda c: c["d"], reverse=True); del lst[12:]
# lots that sold in the last 10 days, including ones listed and closed between our scans (no shipping included: hammer + premium)
for f, house in (("goldin_sold.json", "G"), ("fanatics_sold.json", "F")):
    sd = load(os.path.join(ROOT, f), {})
    for r in sd.get("lots", []) + sd.get("history", []):
        if r.get("key") and r.get("allIn") and r.get("hammer"):
            add_comp(r["key"], r["url"], r.get("ended"), house, r["allIn"], r["hammer"], r.get("units"), r.get("bids"), r["title"])
for url, r in res["results"].items():
    if r.get("status") != "sold" or not r.get("hammer") or not r.get("key"): continue
    bp = float(reg.get(url, {}).get("buyerPremiumPct") or (22 if r["source"] == "goldin" else 20))
    add_comp(r["key"], url, r.get("ended") or r.get("checked"), "G" if r["source"] == "goldin" else "F",
             float(r["hammer"]) * (1 + bp / 100), r["hammer"], r.get("units"), r.get("bids"), r["title"])
json.dump(comps, open(COMPS, "w"), indent=1, ensure_ascii=False)
cut = (NOW - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
reg = {u: e for u, e in reg.items() if (e.get("ends") or "9") >= cut}
res["results"] = {u: r for u, r in res["results"].items() if u in reg}
res["generated"] = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
won = [r for r in res["results"].values() if r.get("maxBidWouldWin")]
res["summary"] = {"products": len(comps), "closed": sum(1 for r in res["results"].values() if r.get("status") in ("sold", "unsold")), "maxBidWouldHaveWon": len(won)}
os.makedirs(os.path.dirname(REG), exist_ok=True)
json.dump(reg, open(REG, "w"), indent=1, ensure_ascii=False)
json.dump(res, open(RES, "w"), indent=1, ensure_ascii=False)
print(f"registry {len(reg)}, newly checked {done}, summary {res['summary']}")
