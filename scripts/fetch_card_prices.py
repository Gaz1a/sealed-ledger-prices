#!/usr/bin/env python3
"""Fetch TCGplayer market prices (via tcgcsv.com) for the card ledgers.
Reads cards/tracked.json, writes cards/prices.json. Stdlib only.
Currently Lorcana only (category 71): Football and Wrestling cards are not on
TCGplayer and are covered by scan_ebay_cards.py instead."""
import json, time, urllib.request, datetime, os, sys
from concurrent.futures import ThreadPoolExecutor

BASE = "https://tcgcsv.com/tcgplayer"
CATS = [71]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda n: os.path.join(ROOT, "cards", n)

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

tracked = json.load(open(P("tracked.json")))
gmap = json.load(open(P("group-map.json"))) if os.path.exists(P("group-map.json")) else {}
want = {str(v["productId"]) for v in tracked.values() if v.get("productId")}

def prices_for(cg):
    d = get(f"{BASE}/{cg[0]}/{cg[1]}/prices"); time.sleep(0.15)
    return cg, (d or {}).get("results") if d else None

def scan(groups):
    out = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for cg, rows in ex.map(prices_for, groups):
            for r in rows or []:
                pid = str(r["productId"])
                if pid in want:
                    out.setdefault(pid, []).append(r); gmap[pid] = list(cg)
    return out

found = {}
known = {tuple(gmap[p]) for p in want if p in gmap}
if known: found.update(scan(sorted(known)))
if [p for p in want if p not in found]:
    groups = []
    for c in CATS:
        d = get(f"{BASE}/{c}/groups")
        groups += [(c, g["groupId"]) for g in (d or {}).get("results", []) if (c, g["groupId"]) not in known]
    for pid, rows in scan(groups).items(): found.setdefault(pid, []).extend(rows)

def pick(rows, variant):
    rows = [r for r in rows if r.get("marketPrice") is not None]
    if not rows: return None
    if variant:
        m = [r for r in rows if r["subTypeName"] == variant]
        if m: return m[0]
    for pref in ("Normal", "Holofoil", "Unlimited Holofoil"):
        m = [r for r in rows if r["subTypeName"] == pref]
        if m: return m[0]
    return rows[0]

out, unresolved = {}, []
for lid, t in tracked.items():
    r = pick(found.get(str(t.get("productId")), []), t.get("variant")) if t.get("productId") else None
    if r is None: unresolved.append(lid); continue
    out[lid] = {"market": r["marketPrice"], "low": r.get("lowPrice"), "mid": r.get("midPrice"),
                "subType": r["subTypeName"], "productId": t["productId"]}

json.dump(gmap, open(P("group-map.json"), "w"), indent=0, sort_keys=True)
json.dump({"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": "tcgcsv.com (TCGplayer market price, per subtype)",
           "count": len(out), "unresolved": unresolved, "prices": out},
          open(P("prices.json"), "w"), indent=1, sort_keys=True)
print(f"prices for {len(out)} of {len(tracked)} tracked; unresolved: {unresolved}")
if len(out) < len(tracked) * 0.5:
    sys.exit("too few prices resolved; failing so the old file is kept")
