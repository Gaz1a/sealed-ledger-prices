#!/usr/bin/env python3
"""Fanatics Collect weekly/premier auction scan (free: the site's public search index), same rules as goldin_scan.py.
Writes fanatics.json {generated, wants, sealed} and fanatics_sold.json (recent sealed results vs TCGplayer value)."""
import json, os, re, sys, time, datetime, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import goldin_scan as g

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
      "Origin": "https://www.fanaticscollect.com", "Referer": "https://www.fanaticscollect.com/"}
INDEX = "prod_item_state_v1"
SEALED_TERMS = ["booster box", "elite trainer box", "booster bundle", "case", "ultra premium collection", "collection", "tin", "sealed"]
BP_DEFAULT = 20.0

def http(u, data=None, h=None):
    hd = dict(UA); hd.update(h or {})
    with urllib.request.urlopen(urllib.request.Request(u, data=data, headers=hd), timeout=60) as r:
        return r.read().decode("utf-8", "replace")

def keys():
    """The site's public (browser) search key, read from its own page scripts each run."""
    html = http("https://www.fanaticscollect.com/weekly-auction?q=pokemon")
    env = {}
    for s in sorted(set(re.findall(r'(/_next/static/chunks/[^"\' ]+\.js)', html))):
        try: js = http("https://www.fanaticscollect.com" + s)
        except Exception: continue
        for k in ("NEXT_PUBLIC_ALGOLIA_APP_ID", "NEXT_PUBLIC_ALGOLIA_API_KEY"):
            m = re.search(k + r':"([^"]+)"', js)
            if m: env[k] = m.group(1)
        if len(env) == 2: return env["NEXT_PUBLIC_ALGOLIA_APP_ID"], env["NEXT_PUBLIC_ALGOLIA_API_KEY"]
    raise SystemExit("Fanatics search key not found")

class Search:
    index = INDEX
    def __init__(self):
        self.app, self.key = keys()
        self.url = f"https://{self.app}-dsn.algolia.net/1/indexes/*/queries"
    def multi(self, reqs):
        out = []
        for i in range(0, len(reqs), 40):
            body = json.dumps({"requests": [{"indexName": self.index, "params": urllib.parse.urlencode(r)} for r in reqs[i:i + 40]]}).encode()
            for t in range(3):
                try:
                    out += json.loads(http(self.url, body, {"x-algolia-application-id": self.app, "x-algolia-api-key": self.key,
                                                            "Content-Type": "application/json"}))["results"]; break
                except Exception as e:
                    if t == 2: print("fanatics search FAIL", e, file=sys.stderr); out += [{"hits": []}] * len(reqs[i:i + 40])
                    time.sleep(3 * (t + 1))
            time.sleep(0.5)
        return out

def best_img(h):
    """Largest picture Fanatics gives for a lot (the first 'image' field is often a small thumbnail)."""
    im = h.get("images")
    if isinstance(im, dict):
        for slot in ["primary", "front", "main"] + [k for k in im if k not in ("primary", "front", "main")]:
            v = im.get(slot)
            if isinstance(v, dict):
                for size in ("original", "xlarge", "large", "medium"):
                    if isinstance(v.get(size), str) and v[size].startswith("http"): return v[size]
            elif isinstance(v, str) and v.startswith("http"): return v
    for k in ("largeImage", "fullImage", "imageLarge", "originalImage", "images", "image", "imageUrl", "thumbnail"):
        if h.get(k):
            u = g.find_img(h[k])
            if u: return u
    return g.find_img({k: v for k, v in h.items() if re.search(r"image|photo|thumb", k, re.I)})

def lot_url(h):
    """The site's canonical lot page (og:url): /weekly/<uuid>/<slug> (premier lots: /premier/...)."""
    slug = re.sub(r"[^a-z0-9]+", "-", (h.get("title") or "").lower()).strip("-")
    kind = "premier" if h.get("marketplace") == "PREMIER" else "weekly"
    return f"https://www.fanaticscollect.com/{kind}/{h.get('listingUuid')}/{slug}"

def to_lot(h):
    cur = float(h.get("currentBid") or h.get("currentPrice") or 0)
    bp = BP_DEFAULT
    if h.get("purchasePrice") and cur:
        bp = round((float(h["purchasePrice"]) / cur - 1) * 100, 1)
    end = datetime.datetime.fromtimestamp(h.get("auctionEndDatetime") or 0, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"title": h.get("title") or "", "current_price": cur, "min_bid_price": float(h.get("startingBid") or 0),
            "number_of_bids": h.get("bidCount") or 0, "end_timestamp": end, "buyer_premium": bp,
            "url": lot_url(h), "lot_number": h.get("lotNumber"),
            "lot_id": h.get("objectID"), "auction_type": h.get("marketplace"), "status": h.get("status"), "source": "fanatics",
            "fanaticsValue": h.get("value"), "img": best_img(h)}

def fetch(S, status, terms=SEALED_TERMS, per=1000):
    """The public key cannot filter on numbers, so sold lots come from the most-recent-first index and are cut by date in Python."""
    base = f'category:"Pokémon" AND status:"{status}" AND (marketplace:"WEEKLY" OR marketplace:"PREMIER")'
    S.index = INDEX + ("_recent_desc" if status == "Sold" else "")
    res = S.multi([{"query": t, "hitsPerPage": per, "filters": base, "attributesToHighlight": "[]"} for t in terms])
    S.index = INDEX
    seen, out = set(), []
    for r in res:
        for h in r.get("hits", []):
            if h.get("objectID") in seen: continue
            seen.add(h.get("objectID")); out.append(h)
    return out

def main():
    cat_rows = g.catalog()
    if len(cat_rows) < 300: sys.exit("tcgcsv catalog too small")
    ws = g.wants(); ws_all = g.wants(every=True)
    S = Search()
    live = fetch(S, "Live")
    singles = [w for w in ws if w["kind"] in ("singles", "kanto") and w["num"]]
    live += fetch(S, "Live", terms=[f"{w['name']} {w['num']}" for w in singles], per=100)
    seen, lots = set(), []
    for h in live:
        if h.get("objectID") in seen: continue
        seen.add(h.get("objectID")); lots.append(to_lot(h))
    out = {"generated": g.NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "Fanatics Collect public search; values TCGplayer (tcgcsv) and PriceCharting",
           "rules": "Same rules as goldin.json.", "lotsScanned": len(lots), "wants": [], "sealed": [], "tracked": []}
    for l in lots:
        b, p = g.evaluate(l, cat_rows, ws)
        if b:
            if l.get("fanaticsValue"): p["fanaticsGuide"] = l["fanaticsValue"]
            out[b].append(p)
        t = g.identify(l["title"], cat_rows, ws_all)
        if t: out["tracked"].append(dict(t, url=l["url"], title=l["title"], lotId=l.get("lot_id"), ends=l.get("end_timestamp"),
                                         source="fanatics", buyerPremiumPct=float(l.get("buyer_premium") or 20)))
    soon = (g.NOW + datetime.timedelta(days=8)).strftime("%Y-%m-%dT%H:%M")
    pool = [p for p in out["sealed"] if (p.get("ends") or "") <= soon and p.get("value", 0) >= 100]
    pool.sort(key=lambda p: (p.get("flag") != "overlooked", -(p["value"] - p["allInNow"])))
    for p in pool[:12]: p["top"] = True
    for p in out["wants"]: p["top"] = (p.get("ends") or "") <= soon
    for k in ("wants", "sealed"): out[k].sort(key=lambda p: (p.get("ends") or "", p.get("pctOfValueNow") or 9))
    json.dump(out, open(os.path.join(g.ROOT, "fanatics.json"), "w"), indent=1, ensure_ascii=False)
    print(f"fanatics: {len(lots)} lots, wants {len(out['wants'])}, sealed {len(out['sealed'])}", file=sys.stderr)
    # recent results for calibration
    cut = int((g.NOW - datetime.timedelta(days=10)).timestamp())
    rows = []
    for h in [h for h in fetch(S, "Sold") if (h.get("auctionEndDatetime") or 0) > cut]:
        l = to_lot(h); title = l["title"]
        prod, why = g.match_sealed(title, cat_rows); units, case = g.quantity(title)
        r = {"title": title, "url": l["url"], "ended": l["end_timestamp"], "hammer": l["current_price"], "bids": l["number_of_bids"],
             "allIn": round(l["current_price"] * (1 + l["buyer_premium"] / 100), 2)}
        t = g.identify(title, cat_rows, ws_all)
        if t: r.update(key=t["key"], units=t["units"], product=t["product"], kind=t["kind"])
        if prod and units and not g.GRADE.search(title):
            v = prod["value"] * units
            r.update(product=prod["name"], units=units, value=round(v, 2), pctOfValue=round(r["allIn"] / v, 2) if v else None)
        rows.append(r)
    rows.sort(key=lambda r: r.get("pctOfValue") or 9)
    vals = sorted(r["pctOfValue"] for r in rows if r.get("pctOfValue"))
    json.dump({"generated": out["generated"], "days": 10, "recent": len(rows), "valued": len(vals),
               "medianPctOfValue": vals[len(vals) // 2] if vals else None,
               "cheap": [r for r in rows if r.get("pctOfValue") and r["pctOfValue"] <= 0.75], "lots": rows},
              open(os.path.join(g.ROOT, "fanatics_sold.json"), "w"), indent=1, ensure_ascii=False)

if __name__ == "__main__":
    main()
