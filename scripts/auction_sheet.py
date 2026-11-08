#!/usr/bin/env python3
"""Build auction_sheet.json for the ledger's Buy tab from goldin.json + fanatics.json.
Budget (data/auction_budget.json): a pick is kept only if its max bid lands at or under perLotAllIn all-in
(hammer + buyer's premium + est. shipping). The page applies the monthly budget against what Gaz has spent."""
import json, os, sys, datetime, re, io, base64, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auction_keys import comp_key
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load(f, d=None):
    try: return json.load(open(os.path.join(ROOT, f)))
    except Exception: return d if d is not None else {}
bud = load("data/auction_budget.json", {"perLotAllIn": 500, "monthly": 500})
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
picks, dropped, allp = [], 0, []
for house, f, sf in (("Goldin", "goldin.json", "goldin_sold.json"), ("Fanatics", "fanatics.json", "fanatics_sold.json")):
    d = load(f)
    for k in ("wants", "sealed"):
        for p in d.get(k, []):
            if p.get("maxBid") is None: continue
            if (p.get("ends") or "") < now: continue
            at_max = round(p["maxBid"] * (1 + p["buyerPremiumPct"] / 100) + p["shipEst"], 2)
            row = {"house": house, "bucket": k, "title": p["title"], "url": p["url"], "tcgUrl": p.get("tcgUrl"),
                          "wantId": p.get("wantId"), "what": p.get("product") or p.get("grade"), "units": p.get("units"),
                          "value": p["value"], "currentBid": p["currentBid"], "bids": p["bids"], "allInNow": p["allInNow"],
                          "maxBid": p["maxBid"], "allInAtMax": at_max, "premiumPct": p["buyerPremiumPct"], "shipEst": p["shipEst"],
                          "ends": p["ends"], "flag": p.get("flag"), "rawMarket": p.get("rawMarket"), "img": p.get("img"),
                          "comp": comp_key(p, k),
                          "thumb": "a-" + re.sub(r"[^A-Za-z0-9_-]", "_", str(p.get("lotId") or p["url"].rstrip("/").rsplit("/", 1)[-1]))[:60], "overCap": at_max > bud["perLotAllIn"],
                          "pctAtMax": round(at_max / p["value"], 2) if p.get("value") else None}
            allp.append(row)
            if row["overCap"]: dropped += 1; continue
            if k == "wants" and not p.get("top"): continue
            picks.append(row)
# one lot per want (the cheapest right now), and the 12 best sealed lots within the cap
best = {}
for p in [p for p in picks if p["bucket"] == "wants"]:
    k = p["wantId"] or p["url"]
    if k not in best or p["allInNow"] < best[k]["allInNow"]: best[k] = p
sealed = sorted([p for p in picks if p["bucket"] == "sealed"], key=lambda p: (p.get("flag") != "overlooked", -(p["value"] - p["allInAtMax"])))[:12]
picks = sorted(best.values(), key=lambda p: -(p["value"] - p["allInAtMax"])) + sealed
med = {h: (load(sf).get("medianPctOfValue")) for h, sf in (("Goldin", "goldin_sold.json"), ("Fanatics", "fanatics_sold.json"))}
allp.sort(key=lambda p: (p["bucket"] != "wants", p["overCap"], p.get("ends") or "", -(p["value"] - p["allInAtMax"])))
out = {"generated": now, "budget": bud, "picks": picks, "all": allp, "droppedOverCap": dropped,
       "scans": {"Goldin": load("goldin.json").get("generated"), "Fanatics": load("fanatics.json").get("generated")},
       "medianPctOfValue": med,
       "rule": "Max bid = highest hammer bid keeping hammer + premium + est. shipping at or under 85% of value; only lots whose max bid stays within the per-lot budget all-in."}
print(f"{len(picks)} picks kept, {dropped} over the ${bud['perLotAllIn']} per-lot cap")

# small pictures of every lot for the ledger (collection thumbsa): files auction_thumbs/a<N>.json, each under ~200 KB
def small_webp(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://goldin.co/" if "goldin" in url or "cloudfront" in url else "https://www.fanaticscollect.com/"})
        raw = urllib.request.urlopen(req, timeout=30).read()
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB"); im.thumbnail((400, 400), Image.LANCZOS)   # sharp on phones and in the tap-to-enlarge view
        for q in (78, 70, 60, 50):
            b = io.BytesIO(); im.save(b, "WEBP", quality=q, method=6)
            if b.tell() <= 26000: break
        return base64.b64encode(b.getvalue()).decode()
    except Exception as e:
        return None
os.makedirs(os.path.join(ROOT, "auction_thumbs"), exist_ok=True)
old = {}
for f in os.listdir(os.path.join(ROOT, "auction_thumbs")):
    try:
        d = json.load(open(os.path.join(ROOT, "auction_thumbs", f)))
        if d.get("v") == 3: old.update(d.get("imgs", {}))
    except Exception: pass
    os.remove(os.path.join(ROOT, "auction_thumbs", f))
imgs, got = {}, 0
for p in out["all"]:
    k = p["thumb"]
    if k in old: imgs[k] = old[k]; continue
    if p.get("img"):
        b = small_webp(p["img"])
        if b: imgs[k] = b; got += 1
docs, cur, size = [], {}, 0
for k, v in imgs.items():
    if size + len(v) > 200000: docs.append(cur); cur, size = {}, 0
    cur[k] = v; size += len(v) + len(k) + 6
if cur: docs.append(cur)
for i, d in enumerate(docs):
    json.dump({"imgs": d, "n": len(d), "generated": now, "v": 3}, open(os.path.join(ROOT, "auction_thumbs", f"a{i}.json"), "w"))
print(f"auction pictures: {len(imgs)} ({got} new) in {len(docs)} docs")

# auction finishes we have tracked, per product: for the lots on the sheet and for every ledger row (sealed by TCGplayer id, graded wants by grade)
comps = load("data/auction_comps.json", {})
tracked = load("tracked.json", {})
want = {p.get("comp") for p in out["all"]} | {f"p{v['productId']}" for v in tracked.values() if isinstance(v, dict) and v.get("productId")}
want |= {k for k in comps if k.split("|")[0] in tracked}
cut = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
out["comps"] = {k: [[c["d"], c["h"], c["a"], c.get("u") or 1, c.get("b"), c["url"]] for c in v if c["d"] >= cut][:5]
                for k, v in comps.items() if k in want}
out["comps"] = {k: v for k, v in out["comps"].items() if v}
out["compsNote"] = "Each: [date, house G=Goldin F=Fanatics, all-in incl. buyer premium (no shipping), boxes in the lot, bids, url]"
for p in out["all"] + out["picks"]: p.pop("img", None)
json.dump(out, open(os.path.join(ROOT, "auction_sheet.json"), "w"), indent=1, ensure_ascii=False)
print(f"comps: {len(out['comps'])} products with auction finishes; sheet {len(json.dumps(out))//1024} KB")
