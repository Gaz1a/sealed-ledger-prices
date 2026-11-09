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
            at_max = round((p["maxBid"] * (1 + p["buyerPremiumPct"] / 100) + p["shipEst"]) * (1 + (p.get("cardFeePct") or 0) / 100), 2)
            row = {"house": house, "bucket": k, "title": p["title"], "url": p["url"], "tcgUrl": p.get("tcgUrl"),
                          "wantId": p.get("wantId"), "what": p.get("product") or p.get("grade"), "units": p.get("units"),
                          "value": p["value"], "currentBid": p["currentBid"], "bids": p["bids"], "allInNow": p["allInNow"],
                          "maxBid": p["maxBid"], "allInAtMax": at_max, "premiumPct": p["buyerPremiumPct"], "shipEst": p["shipEst"], "cardFeePct": p.get("cardFeePct") or 0,
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
# ---------- what the finishes tell us ----------
def q(v, f):
    v = sorted(v); i = (len(v) - 1) * f; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)
cut180 = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
prices = load("prices.json", {}).get("prices", {})
tcg_by_pid = {}
for lid, v in prices.items():
    if v.get("productId") and v.get("market"): tcg_by_pid.setdefault(str(v["productId"]), v["market"])
for d in (load("goldin.json"), load("fanatics.json")):
    for t in d.get("tracked", []):
        if t["key"].startswith("p") and t.get("unitValue"): tcg_by_pid.setdefault(t["key"][1:], t["unitValue"])
graded_val = {p.get("comp"): p["value"] for p in out["all"] if p.get("comp") and "|" in (p.get("comp") or "")}
ledger_by_key = {}
for lid, v in tracked.items():
    if isinstance(v, dict) and v.get("productId"): ledger_by_key.setdefault(f"p{v['productId']}", []).append(lid)
ledger_mkt = {f"p{v['productId']}": v["market"] for v in prices.values() if v.get("productId") and v.get("market")}
def clean(k, lst):
    """Drop finishes that cannot be the same product at the same count (a misread box count, a store-exclusive variant):
    per box more than 2.5x or under 0.4x the TCGplayer price, or, with no TCGplayer price, the median of the others."""
    rec = [c for c in lst if c.get("a")]
    if not rec: return []
    ref = tcg_by_pid.get(k[1:]) if k.startswith("p") else graded_val.get(k)
    if not ref:
        per = [c["a"] / (c.get("u") or 1) for c in rec]
        ref = q(per, .5) if len(per) >= 3 else None
    if not ref: return rec
    return [c for c in rec if 0.4 <= (c["a"] / (c.get("u") or 1)) / ref <= 2.5]
comps = {k: clean(k, v) for k, v in comps.items()}
market, mismatch, bulk = {}, [], {}
for k, lst in comps.items():
    rec = [c for c in lst if c["d"] >= cut180 and c.get("a")]
    if not rec: continue
    per = [c["a"] / (c.get("u") or 1) for c in rec]
    single = [c["a"] for c in rec if (c.get("u") or 1) == 1]
    multi = [c["a"] / c["u"] for c in rec if (c.get("u") or 1) > 1]
    tcg = (ledger_mkt.get(k) or tcg_by_pid.get(k[1:])) if k.startswith("p") else graded_val.get(k)
    m = {"n": len(per), "med": round(q(per, .5), 2), "lo": round(q(per, .25), 2), "hi": round(q(per, .75), 2), "last": rec[0]["d"]}
    if tcg: m["ref"] = round(tcg, 2); m["ratio"] = round(m["med"] / tcg, 2)
    if len(single) >= 2 and len(multi) >= 2:
        bulk[k] = {"single": round(q(single, .5), 2), "inCase": round(q(multi, .5), 2), "pct": round(q(multi, .5) / q(single, .5) - 1, 3)}
        m["bulkPct"] = bulk[k]["pct"]
    if ledger_by_key.get(k): m["ledger"] = ledger_by_key[k]
    market[k] = m
    if ledger_mkt.get(k) and len(per) >= 3 and abs(m["ratio"] - 1) > 0.25:
        mismatch.append({"key": k, "ledger": ledger_by_key.get(k, []), "tcg": round(tcg, 2), "auction": m["med"], "n": len(per),
                         "diffPct": round((m["ratio"] - 1) * 100), "title": rec[0]["t"]})
mismatch.sort(key=lambda x: -abs(x["diffPct"]))
bp = [b["pct"] for b in bulk.values()]
out["comps"] = {k: [[c["d"], c["h"], c["a"], c.get("u") or 1, c.get("b"), c["url"]] for c in comps.get(k, []) if c["d"] >= cut][:5] for k in out["comps"]}
out["comps"] = {k: v for k, v in out["comps"].items() if v}
out["market"] = market
out["mismatch"] = mismatch[:30]
out["bulk"] = {"products": len(bulk), "medianPct": round(q(bp, .5), 3) if bp else None,
               "note": "Per-box price inside a multi-box lot vs a single box of the same product, auction finishes in the last year."}
# likely finish and the chance the max bid wins, from that product's own finishes (3+ needed)
for p in out["all"]:
    m = market.get(p.get("comp"))
    u = p.get("units") or 1
    if not m or m["n"] < 3: p["likely"] = None; p["winPct"] = None; continue
    per = sorted(c["a"] / (c.get("u") or 1) for c in comps[p["comp"]] if c["d"] >= cut180 and c.get("a"))
    adj = 1 + (m.get("bulkPct") or 0) if u > 1 else 1      # cases finish at the case price per box when we know it
    if u > 1 and m.get("bulkPct") is not None:
        per_u = [c["a"] / c["u"] for c in comps[p["comp"]] if c["d"] >= cut180 and (c.get("u") or 1) > 1] or per
    elif u == 1:
        per_u = [c["a"] for c in comps[p["comp"]] if c["d"] >= cut180 and (c.get("u") or 1) == 1] or per
    else:
        per_u = per
    at_max = (p["maxBid"] * (1 + p["premiumPct"] / 100)) / u      # what the max bid costs per box, same basis as finishes (no shipping)
    p["likely"] = round(q(per_u, .5) * u + (p.get("shipEst") or 0), 2)
    p["winPct"] = round(sum(1 for x in per_u if x <= at_max) / len(per_u), 2)
    p["nComps"] = len(per_u)
# Nov 8 (Gaz: how easy and quick is it to sell?): sales per year = PriceCharting units sold (CSV, by TCGplayer id; for a slab, all
# grades of that card) + our tracked Goldin/Fanatics finishes. The page turns this into weeks to sell and a sell-speed score.
vol = load("data/pc_volume.json", {}).get("v", {})
pcc = load("pricecharting.json", {}).get("cards", {})
for p in out["all"] + out["picks"]:
    k = p.get("comp") or ""
    if k.startswith("p"): base = vol.get(k[1:])
    else:
        c = pcc.get(p.get("wantId") or "") or {}
        try: base = int(float(c.get("salesVolumeYearly") or 0)) or None
        except ValueError: base = None
    au = (market.get(k) or {}).get("n", 0)
    if base or au: p["salesYr"] = (base or 0) + au; p["salesSrc"] = ("PriceCharting" if base else "") + (" + auctions" if au else "")
print(f"market stats {len(market)}, mismatches {len(mismatch)}, bulk {out['bulk']}, lots with a likely finish {sum(1 for p in out['all'] if p.get('likely'))}")
for p in out["all"] + out["picks"]: p.pop("img", None)
json.dump(out, open(os.path.join(ROOT, "auction_sheet.json"), "w"), indent=1, ensure_ascii=False)
print(f"comps: {len(out['comps'])} products with auction finishes; sheet {len(json.dumps(out))//1024} KB")
