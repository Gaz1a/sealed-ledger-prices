#!/usr/bin/env python3
"""Weekly sealed-product scan (Pokemon EN, Pokemon Japan, Lorcana) from tcgcsv.com.
Saves a price snapshot, compares with earlier snapshots, and writes radar.json / radar.md
with the products that look most interesting under the ledger's rules. Stdlib only."""
import json, os, re, sys, time, glob, datetime, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://tcgcsv.com/tcgplayer"
CATS = {3: "Pokemon", 85: "Pokemon Japan", 71: "Lorcana"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_MARKET, MAX_MARKET = 15.0, 1500.0
KEEP_SNAPSHOTS = 12
TODAY = datetime.date.today()

def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sealed-ledger-radar/1.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except Exception as e:
            if i == tries - 1:
                print("FAIL", url, e, file=sys.stderr); return None
            time.sleep(1.5 * (i + 1))

def load(name, default):
    p = os.path.join(ROOT, name)
    return json.load(open(p)) if os.path.exists(p) else default

def is_sealed(prod):
    ext = prod.get("extendedData") or []
    if any(x.get("name") == "Number" for x in ext):
        return False
    n = prod["name"].lower()
    if re.search(r"code card|online|sleeve|deck box|playmat|binder$", n):
        return False
    if n.endswith(" case") or " case " in n:
        return False
    return True

def msrp_est(name, cat, pub):
    n = name.lower()
    year = int((pub or "2000")[:4])
    if "pokemon center" in n and "elite trainer" in n: return 59.99
    if "elite trainer box" in n: return 49.99 if year < 2026 else 59.99
    if "booster bundle" in n: return 26.94
    if "booster box" in n and "case" not in n:
        if cat == 71: return 143.76
        return 143.64 if year < 2026 else 161.64
    return None

def fetch_group(args):
    cat, g = args
    gid = g["groupId"]
    prods = get(f"{BASE}/{cat}/{gid}/products")
    prices = get(f"{BASE}/{cat}/{gid}/prices")
    time.sleep(0.1)
    if not prods or not prices:
        return []
    price = {}
    for r in prices.get("results", []):
        if r.get("marketPrice") is not None and r["productId"] not in price:
            price[r["productId"]] = r
    out = []
    for p in prods.get("results", []):
        if not is_sealed(p): continue
        r = price.get(p["productId"])
        if not r: continue
        out.append({"pid": p["productId"], "name": p["name"], "cat": cat, "gid": gid,
                    "set": g["name"], "pub": (g.get("publishedOn") or "")[:10],
                    "market": r["marketPrice"], "low": r.get("lowPrice")})
    return out

def main():
    tracked = {v["productId"] for v in load("tracked.json", {}).values()}
    jobs = []
    for cat in CATS:
        d = get(f"{BASE}/{cat}/groups")
        jobs += [(cat, g) for g in (d or {}).get("results", [])]
    print(f"{len(jobs)} groups to scan", file=sys.stderr)
    rows = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(fetch_group, jobs):
            rows += res
    if len(rows) < 200:
        sys.exit(f"only {len(rows)} sealed products found; keeping previous files")

    os.makedirs(os.path.join(ROOT, "snapshots"), exist_ok=True)
    snap = {str(r["pid"]): [r["market"], r["low"]] for r in rows}
    json.dump(snap, open(os.path.join(ROOT, f"snapshots/{TODAY}.json"), "w"), separators=(",", ":"))
    files = sorted(glob.glob(os.path.join(ROOT, "snapshots/*.json")))
    for f in files[:-KEEP_SNAPSHOTS]: os.remove(f)

    def snap_near(days_back, tol):
        best = None
        for f in glob.glob(os.path.join(ROOT, "snapshots/*.json")):
            d = datetime.date.fromisoformat(os.path.basename(f)[:-5])
            age = (TODAY - d).days
            if abs(age - days_back) <= tol and (best is None or abs(age - days_back) < best[0]):
                best = (abs(age - days_back), f)
        return json.load(open(best[1])) if best else None
    s1w, s4w = snap_near(7, 3), snap_near(28, 6)

    cands = []
    for r in rows:
        m, low = r["market"], r["low"]
        if not (MIN_MARKET <= m <= MAX_MARKET) or r["pid"] in tracked: continue
        pid = str(r["pid"])
        age = None
        if r["pub"]:
            age = (TODAY - datetime.date.fromisoformat(r["pub"])).days / 7
        chg1 = (m / s1w[pid][0] - 1) if s1w and pid in s1w and s1w[pid][0] else None
        chg4 = (m / s4w[pid][0] - 1) if s4w and pid in s4w and s4w[pid][0] else None
        est = msrp_est(r["name"], r["cat"], r["pub"])
        tags, score = [], 0
        recent = age is not None and 3 <= age <= 20
        drop = chg4 if chg4 is not None else chg1
        thr = -0.15 if chg4 is not None else -0.10
        if recent and drop is not None and drop <= thr:
            tags.append(f"post-launch slide {drop*100:.0f}%"); score += 2 + (1 if drop <= -0.30 else 0)
        if est and age is not None and age >= 6 and m <= est * 1.15:
            tags.append(f"near MSRP ({m/est:.2f}x est.)"); score += 2
        if low and m >= 25 and low <= m * 0.80:
            disc = 1 - low / m
            tags.append(f"cheapest listing {disc*100:.0f}% under market"); score += 1 + (1 if disc >= 0.30 else 0)
        if tags:
            cands.append({"pid": r["pid"], "name": r["name"], "set": r["set"], "cat": CATS[r["cat"]],
                          "market": m, "low": low, "msrpEst": est,
                          "ageWeeks": round(age, 1) if age is not None else None,
                          "chg1w": round(chg1, 3) if chg1 is not None else None,
                          "chg4w": round(chg4, 3) if chg4 is not None else None,
                          "tags": tags, "score": score,
                          "url": f"https://www.tcgplayer.com/product/{r['pid']}"})
    cands.sort(key=lambda c: (-c["score"], -c["market"]))
    top = cands[:25]
    note = "" if s1w else "First run: no earlier snapshot yet, so slide signals start next week."
    json.dump({"generated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
               "source": "tcgcsv.com (TCGplayer market and lowest listing)",
               "scanned": len(rows), "note": note, "candidates": top},
              open(os.path.join(ROOT, "radar.json"), "w"), indent=1, ensure_ascii=False)
    lines = [f"# Market radar {TODAY}", f"Scanned {len(rows)} sealed products. {note}", "",
             "| Product | Set | Market | Low | Signals |", "|---|---|---|---|---|"]
    for c in top:
        lines.append(f"| [{c['name']}]({c['url']}) | {c['set']} | ${c['market']:.2f} | "
                     f"{'$%.2f' % c['low'] if c['low'] else '-'} | {'; '.join(c['tags'])} |")
    open(os.path.join(ROOT, "radar.md"), "w").write("\n".join(lines) + "\n")
    print(f"scanned {len(rows)} sealed products, {len(cands)} flagged, top {len(top)} written")

if __name__ == "__main__":
    main()
