#!/usr/bin/env python3
"""Fetch TCGplayer market prices from tcgcsv.com for every product in tracked.json.
Writes prices.json. Stdlib only. Caches productId->groupId in group-map.json so
normal runs touch only the groups that hold tracked products."""
import json, time, urllib.request, urllib.error, datetime, os, sys
from concurrent.futures import ThreadPoolExecutor

BASE = "https://tcgcsv.com/tcgplayer"
CATS = [3, 85, 68, 71, 86, 89]   # Pokemon, Pokemon Japan, One Piece, Lorcana, Gundam, Riftbound
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sealed-ledger-prices/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if i == tries - 1:
                print("FAIL", url, e, file=sys.stderr); return None
            time.sleep(1.5 * (i + 1))

def load(name, default):
    p = os.path.join(ROOT, name)
    return json.load(open(p)) if os.path.exists(p) else default

tracked = load("tracked.json", {})
gmap = load("group-map.json", {})            # str(productId) -> [cat, group]
want = {str(v["productId"]) for v in tracked.values()}

def prices_for(cat_group):
    cat, grp = cat_group
    d = get(f"{BASE}/{cat}/{grp}/prices")
    time.sleep(0.15)
    return cat_group, (d or {}).get("results", []) if d else None

def scan(groups):
    out = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for cg, rows in ex.map(prices_for, groups):
            if rows is None: continue
            for r in rows:
                pid = str(r["productId"])
                if pid in want:
                    out.setdefault(pid, []).append(r)
                    gmap[pid] = list(cg)
    return out

found = {}
known = {tuple(gmap[p]) for p in want if p in gmap}
if known:
    found.update(scan(sorted(known)))
missing = [p for p in want if p not in found]
if missing:
    print(f"{len(missing)} products not in cache; scanning all groups", file=sys.stderr)
    groups = []
    for c in CATS:
        d = get(f"{BASE}/{c}/groups")
        groups += [(c, g["groupId"]) for g in (d or {}).get("results", []) if (c, g["groupId"]) not in known]
    for pid, rows in scan(groups).items():
        found.setdefault(pid, []).extend(rows)

def pick(rows, variant):
    rows = [r for r in rows if r.get("marketPrice") is not None]
    if not rows: return None
    if variant:
        m = [r for r in rows if r["subTypeName"] == variant]
        if m: return m[0]
    if len(rows) == 1: return rows[0]
    for pref in ("Normal", "Unlimited Holofoil", "Holofoil"):
        m = [r for r in rows if r["subTypeName"] == pref]
        if m: return m[0]
    return rows[0]

out, unresolved = {}, []
for lid, t in tracked.items():
    r = pick(found.get(str(t["productId"]), []), t.get("variant"))
    if r is None:
        unresolved.append(lid); continue
    out[lid] = {"market": r["marketPrice"], "low": r.get("lowPrice"), "mid": r.get("midPrice"),
                "subType": r["subTypeName"], "productId": t["productId"]}

json.dump(gmap, open(os.path.join(ROOT, "group-map.json"), "w"), indent=0, sort_keys=True)
json.dump({"generated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": "tcgcsv.com (TCGplayer market price, per subtype)",
           "count": len(out), "unresolved": unresolved, "prices": out},
          open(os.path.join(ROOT, "prices.json"), "w"), indent=1, sort_keys=True)
print(f"prices for {len(out)} of {len(tracked)} tracked; unresolved: {len(unresolved)}")
if len(out) < len(tracked) * 0.5:
    sys.exit("too few prices resolved; failing so the old file is kept")
