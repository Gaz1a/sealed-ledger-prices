#!/usr/bin/env python3
"""Every price source we have for every ledger row, side by side -> price_sources.json (Gaz, Nov 8: "use all sources").
Free: reads only files the other workflows already write. The ledger's own market stays TCGplayer; this adds the others
and a consensus (median of the comparable sources) so disagreements show up.

Per row: {tcg, tcgLow, pc, cnTcg, cnCm, auction, auctionN, ebayGraded (slabs only), consensus, n, spread, src}
  tcg      TCGplayer market (prices.json, daily)
  pc       PriceCharting ungraded / sealed price (paid API, daily)
  cnTcg    CardNexus TCGplayer market value; cnCm Cardmarket market value (USD)
  auction  median Goldin/Fanatics finish per unit, all-in (needs 3+ finishes in the last year)
"""
import json, os, statistics, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load(p, d=None):
    try: return json.load(open(os.path.join(ROOT, p)))
    except Exception: return d if d is not None else {}

prices = load("prices.json").get("prices", {})
pc = load("pricecharting.json")
pcc, pcs = pc.get("cards", {}), pc.get("sealed", {})
cn = load("cardnexus.json").get("items", {})
au = load("auction_sheet.json").get("market", {})
gr = load("graded.json").get("cards", {})
po = load("pc_offers.json").get("items", {})   # PriceCharting marketplace   # eBay sold by grade (PokemonPriceTracker API)
tracked = load("tracked.json")
ids = set(prices) | set(pcc) | set(pcs) | set(k for k in tracked if isinstance(tracked.get(k), dict))
out, disagree = {}, []
for i in sorted(ids):
    r = {}
    p = prices.get(i) or {}
    if p.get("market"): r["tcg"] = round(p["market"], 2)
    if p.get("low"): r["tcgLow"] = round(p["low"], 2)
    c = pcs.get(i) or {}
    if c.get("matched") and (c.get("pcSealed") or c.get("ungraded")): r["pc"] = round(c.get("pcSealed") or c["ungraded"], 2)
    c = pcc.get(i) or {}
    # PriceCharting 'ungraded' is any condition and has no reverse-holo split: shown, but never part of the NM consensus
    if c.get("matched") and c.get("ungraded") and not i.endswith("-rev"): r["pcRaw"] = round(c["ungraded"], 2)
    for g in ("psa8", "psa9", "psa10"):
        if c.get("matched") and c.get(g) and not i.endswith("-rev"): r["pc" + g[3:]] = round(c[g], 2)
    for g, v in ((gr.get(i) or {}).get("grades") or {}).items():
        if g in ("psa8", "psa9", "psa10", "cgc9", "cgc10", "bgs9", "bgs95") and v.get("n", 0) >= 3 and v.get("median"):
            r["eb_" + g] = [round(v["median"], 2), v["n"]]   # eBay sold median and count for that grader + grade
    for c in (pcs.get(i) or {}, pcc.get(i) or {}):
        try:
            if c.get("matched") and int(float(c.get("salesVolumeYearly") or 0)): r["salesYr"] = int(float(c["salesVolumeYearly"])); break
        except ValueError: pass
    o = po.get(i) or {}
    if o.get("live"): r["pcmLive"] = [o["live"][0]["price"], o["live"][0].get("cond"), o["live"][0].get("url")]
    if o.get("sold"): r["pcmSold"] = [o["sold"][0]["price"], o["sold"][0].get("cond"), o["sold"][0].get("date")]
    n = cn.get(i) or {}
    if (n.get("tcg") or {}).get("marketValue"): r["cnTcg"] = round(n["tcg"]["marketValue"], 2)
    if (n.get("cm") or {}).get("marketValue"): r["cnCm"] = round(n["cm"]["marketValue"], 2)
    na = (n.get("cnx") or {}).get("na") or {}
    if na.get("low") and na.get("cur") == "USD": r["cnxLow"] = [round(na["low"], 2), na.get("n")]   # CardNexus lowest US listing (asking)
    pid = p.get("productId") or (tracked.get(i) or {}).get("productId") if isinstance(tracked.get(i), dict) else p.get("productId")
    m = au.get(f"p{pid}") if pid else None
    if m and m.get("n", 0) >= 3: r["auction"], r["auctionN"] = m["med"], m["n"]
    vals = [r[k] for k in ("tcg", "pc", "cnTcg", "auction") if r.get(k)]
    if not vals and not r: continue
    if not vals: out[i] = r; continue
    r["consensus"] = round(statistics.median(vals), 2); r["n"] = len(vals)
    if len(vals) >= 2:
        r["spread"] = round(max(vals) / min(vals) - 1, 3)
        if r["spread"] > 0.3 and r["consensus"] >= 10: disagree.append([i, r["spread"]])
    out[i] = r
disagree.sort(key=lambda x: -x[1])
doc = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
       "note": "tcg=TCGplayer market, pc=PriceCharting sealed, pcRaw=PriceCharting ungraded any condition (not in consensus), pc8/pc9/pc10=PriceCharting graded, cnCm=Cardmarket price guide trend in USD, cnxLow=lowest CardNexus US listing (asking, not in consensus), auction=Goldin/Fanatics median finish per unit incl. premium; consensus=median of tcg, pc, cnTcg, auction; salesYr=PriceCharting units sold per year",
       "coverage": {k: sum(1 for r in out.values() if k in r) for k in ("salesYr", "tcg", "pc", "pcRaw", "pc9", "cnCm", "cnxLow", "auction")},
       "disagree": disagree[:40], "rows": out}
json.dump(doc, open(os.path.join(ROOT, "price_sources.json"), "w"), separators=(",", ":"), ensure_ascii=False)
print(len(out), "rows", doc["coverage"], "disagree", len(disagree), f"{len(json.dumps(doc))//1024} KB")
