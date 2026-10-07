#!/usr/bin/env python3
"""One-off audit: sealed products (Pokemon EN + JP) not in tracked.json -> untracked_sealed.json.
Stdlib only. Uses scan_market's sealed filter and the snapshots/ history."""
import json, os, re, sys, glob, datetime
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_market as sm

CATS = {3: "Pokemon EN", 85: "Pokemon JP"}
TODAY = sm.TODAY
ROOT = sm.ROOT
MIN_UNTRACKED = 40.0
CASE_RE = re.compile(r"\bcase\b|\bdisplay\b", re.I)
SEALEDISH = re.compile(sm.SEALED_WORDS.pattern + r"|\bcase\b|\bdisplay\b|sealed", re.I)
MAIN_EXCL = re.compile(r"promo|trainer gallery|galarian gallery|shiny vault|prize|mcdonald|deck|stamped|"
                       r"pokemon go|world championship|blister|code card|miscellaneous|jumbo|sleeve", re.I)

def norm(s):
    s = re.sub(r"^[A-Za-z0-9\-\.]+:\s*", "", s or "")
    s = re.sub(r"[^a-z0-9 ]", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()

def classify(name):
    n = name.lower()
    if CASE_RE.search(n): return "case_display"
    if "elite trainer" in n:
        if "pokemon center" in n or "pokémon center" in n: return "pc_etb"
        return "etb"
    if "booster bundle" in n: return "booster_bundle"
    if "booster box" in n: return "booster_box"
    return "collection"

def fetch_group(args):
    cat, g = args
    gid = g["groupId"]
    prods = sm.get(f"{sm.BASE}/{cat}/{gid}/products")
    prices = sm.get(f"{sm.BASE}/{cat}/{gid}/prices")
    if not prods or not prices: return []
    price = {}
    for r in prices.get("results", []):
        if r.get("marketPrice") is not None and r["productId"] not in price: price[r["productId"]] = r
    out = []
    for p in prods.get("results", []):
        ext = p.get("extendedData") or []
        single = any(x.get("name") in {"Number","Rarity","Card Type","HP","Stage","Attack 1","Weakness","Resistance","Retreat Cost"} for x in ext)
        if single: continue
        n = p["name"]
        sealed = sm.is_sealed(p)
        casey = bool(CASE_RE.search(n)) and bool(SEALEDISH.search(n)) and not re.search(r"\bcode card\b|sleeve|playmat|binder", n, re.I)
        if not (sealed or casey): continue
        r = price.get(p["productId"])
        if not r: continue
        out.append({"pid": p["productId"], "name": n, "cat": cat, "gid": gid, "set": g["name"],
                    "pub": (g.get("publishedOn") or "")[:10], "market": r["marketPrice"], "low": r.get("lowPrice")})
    return out

def main():
    tracked = json.load(open(os.path.join(ROOT, "tracked.json")))
    tpids = {v["productId"] for v in tracked.values()}
    gmap = sm.load("group-map.json", {})
    item_sets = sm.load("item_sets.json", {})
    jobs = []
    for cat in CATS:
        d = sm.get(f"{sm.BASE}/{cat}/groups")
        jobs += [(cat, g) for g in (d or {}).get("results", [])]
    rows, seen = [], set()
    with ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(fetch_group, jobs):
            for r in res:
                if r["pid"] not in seen: seen.add(r["pid"]); rows.append(r)
    if len(rows) < 500: sys.exit(f"only {len(rows)} rows; aborting")
    print(f"{len(rows)} sealed/case rows from {len(jobs)} groups", file=sys.stderr)

    # sets in ledger
    ledger_gids = {tuple(gmap[str(p)]) for p in tpids if str(p) in gmap}
    for r in rows:
        if r["pid"] in tpids: ledger_gids.add((r["cat"], r["gid"]))
    ledger_names = {norm(v) for v in item_sets.values()}
    def set_in_ledger(r):
        if (r["cat"], r["gid"]) in ledger_gids: return True
        s = norm(r["set"])
        return any(s == x or (len(x) > 5 and (x in s or s in x)) for x in ledger_names)

    # history
    hist = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "snapshots/*.json"))):
        d = datetime.date.fromisoformat(os.path.basename(f)[:-5])
        hist[d] = json.load(open(f))
    def near(days, tol):
        best = None
        for d in hist:
            a = (TODAY - d).days
            if abs(a - days) <= tol and (best is None or abs(a - days) < best[0]): best = (abs(a - days), d)
        return hist[best[1]] if best else None
    s4, s12 = near(28, 7), near(84, 10)

    def feat(r):
        pid, m = str(r["pid"]), r["market"]
        age = round((TODAY - datetime.date.fromisoformat(r["pub"])).days / 7, 1) if r["pub"] else None
        def chg(s):
            return round(m / s[pid][0] - 1, 3) if s and pid in s and s[pid][0] else None
        vals = [h[pid][0] for h in hist.values() if pid in h and h[pid][0]] + [m]
        return {"productId": r["pid"], "name": r["name"], "set": r["set"], "category": CATS[r["cat"]],
                "market": m, "low": r["low"], "ageWeeks": age, "tracked": r["pid"] in tpids,
                "chg4w": chg(s4), "chg12w": chg(s12), "athMarket": max(vals), "atlMarket": min(vals),
                "setInLedger": set_in_ledger(r), "url": f"https://www.tcgplayer.com/product/{r['pid']}"}

    untracked, cases = [], []
    for r in rows:
        if r["pid"] in tpids: continue
        f = feat(r)
        if classify(r["name"]) == "case_display": cases.append(f)
        elif r["market"] >= MIN_UNTRACKED: untracked.append(f)
    untracked.sort(key=lambda x: -x["market"]); cases.sort(key=lambda x: -x["market"])

    # coverage: main sets from 2023 onward
    bygid = {}
    for r in rows: bygid.setdefault((r["cat"], r["gid"]), []).append(r)
    coverage = []
    for (cat, gid), rs in bygid.items():
        s = rs[0]
        if not s["pub"] or s["pub"] < "2023-01-01" or MAIN_EXCL.search(s["set"]): continue
        kinds = {r["pid"]: classify(r["name"]) for r in rs}
        if not any(k in ("etb", "booster_box", "booster_bundle") for k in kinds.values()): continue
        entry = {"set": s["set"], "category": CATS[cat], "released": s["pub"], "groupId": gid}
        def cell(kind):
            ps = [r for r in rs if kinds[r["pid"]] == kind]
            return [{"productId": r["pid"], "name": r["name"], "status": "tracked" if r["pid"] in tpids else "missing",
                     "market": r["market"]} for r in sorted(ps, key=lambda r: -r["market"])] or "not-in-tcgplayer"
        for k, label in (("etb", "etb"), ("pc_etb", "pokemonCenterEtb"), ("booster_box", "boosterBox"),
                         ("booster_bundle", "boosterBundle"), ("case_display", "casesDisplays"), ("collection", "collections")):
            entry[label] = cell(k)
        coverage.append(entry)
    coverage.sort(key=lambda e: (e["category"], e["released"]), reverse=True)

    out = {"generated": TODAY.isoformat(), "scanned": len(rows), "snapshotsAvailable": len(hist),
           "historyNote": "chg4w/chg12w/ath/atl come from snapshots/ (earliest %s); null when no snapshot in range" % (min(hist).isoformat() if hist else "n/a"),
           "minUntrackedMarket": MIN_UNTRACKED, "untracked": untracked, "cases_displays": cases, "coverage": coverage}
    json.dump(out, open(os.path.join(ROOT, "untracked_sealed.json"), "w"), indent=1, ensure_ascii=False)
    print(f"untracked>= ${MIN_UNTRACKED:.0f}: {len(untracked)}; cases/displays untracked: {len(cases)}; coverage sets: {len(coverage)}")

if __name__ == "__main__":
    main()
