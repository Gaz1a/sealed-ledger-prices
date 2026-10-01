#!/usr/bin/env python3
"""Weekly Lorcana radar from tcgcsv.com (TCGplayer data). Mechanical only:
ranks Enchanted / Iconic singles and sealed boxes in recent sets, and lists upcoming sets.
Writes cards/lorcana_radar.json. Judgment (consider / watch / skip) happens in the Claude weekly task.
Stdlib only."""
import json, os, re, sys, time, datetime, urllib.request

BASE = "https://tcgcsv.com/tcgplayer/71"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda n: os.path.join(ROOT, "cards", n)
RECENT_SETS = 6          # most recent released sets scanned
MAX_OUT = 25
# Brand-level characters: demand tied to the franchise, not one film (ledger rule).
BRANDS = re.compile(r"\b(mickey|minnie|donald|goofy|pluto|stitch|lilo|winnie|pooh|piglet|tigger|elsa|anna|olaf|simba|aurora|cinderella|belle|ariel|moana|rapunzel|snow white|tinker bell|peter pan|woody|buzz)\b", re.I)
WEIGHT = {"Iconic": 4, "Enchanted": 3, "Legendary": 1}

def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sealed-ledger-prices/1.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except Exception as e:
            if i == tries - 1:
                print("FAIL", url, e, file=sys.stderr); return None
            time.sleep(1.5 * (i + 1))

def ext(p, name):
    for e in p.get("extendedData") or []:
        if e.get("name") == name: return e.get("value")
    return None

def main():
    today = datetime.date.today()
    groups = (get(f"{BASE}/groups") or {}).get("results", [])
    if not groups: sys.exit("no groups")
    def pub(g):
        try: return datetime.date.fromisoformat(g["publishedOn"][:10])
        except Exception: return None
    dated = [(pub(g), g) for g in groups if pub(g)]
    released = sorted([x for x in dated if x[0] <= today], key=lambda x: x[0], reverse=True)
    upcoming = sorted([x for x in dated if x[0] > today], key=lambda x: x[0])
    tracked = {str(v.get("productId")) for v in json.load(open(P("tracked.json"))).values()}
    prev = json.load(open(P("lorcana_radar_state.json"))) if os.path.exists(P("lorcana_radar_state.json")) else {}
    cands, state = [], {}
    for d, g in released[:RECENT_SETS]:
        prods = (get(f"{BASE}/{g['groupId']}/products") or {}).get("results", [])
        prices = {}
        for r in (get(f"{BASE}/{g['groupId']}/prices") or {}).get("results", []):
            if r.get("marketPrice") is not None:
                prices.setdefault(r["productId"], r)
        time.sleep(0.2)
        rows = []
        for p in prods:
            pr = prices.get(p["productId"])
            if not pr: continue
            rarity, name = ext(p, "Rarity"), p.get("name", "")
            sealed = bool(re.search(r"booster box|display", name, re.I)) and not rarity
            if not sealed and rarity not in WEIGHT: continue
            rows.append((p, pr, rarity, sealed))
        ranked = sorted((r for r in rows if not r[3]), key=lambda r: r[1]["marketPrice"], reverse=True)
        rank = {r[0]["productId"]: i + 1 for i, r in enumerate(ranked)}
        age = max(0, (today - d).days // 7)
        for p, pr, rarity, sealed in rows:
            pid = str(p["productId"])
            if pid in tracked: continue
            m = pr["marketPrice"]
            if m < (20 if sealed else 25): continue
            tags, score = [], 0
            if sealed: tags.append("sealed box")
            else:
                score += WEIGHT[rarity]; tags.append(rarity.lower())
                if rank[p["productId"]] <= 3: score += 2; tags.append(f"top-{rank[p['productId']]} in set")
                if BRANDS.search(p.get("name", "")): score += 2; tags.append("brand-level character")
            old = prev.get(pid)
            chg = round((m - old) / old * 100, 1) if old else None
            if chg is not None and chg <= -15: tags.append("falling"); score += 1
            state[pid] = m
            cands.append({"pid": int(pid), "name": p["name"], "set": g["name"], "setPublished": d.isoformat(),
                          "ageWeeks": age, "cat": "sealed" if sealed else "single", "rarity": rarity,
                          "number": ext(p, "Number"), "property": ext(p, "Property"),
                          "market": m, "low": pr.get("lowPrice"), "chg1w": chg,
                          "tags": tags, "score": score, "url": p.get("url")})
    cands.sort(key=lambda c: (-c["score"], -c["market"]))
    out = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": "tcgcsv.com (TCGplayer market price)",
           "upcomingSets": [{"name": g["name"], "groupId": g["groupId"], "date": d.isoformat()} for d, g in upcoming],
           "candidates": cands[:MAX_OUT]}
    json.dump(out, open(P("lorcana_radar.json"), "w"), indent=1, ensure_ascii=False)
    keep = {str(c["pid"]): c["market"] for c in cands}
    json.dump(keep, open(P("lorcana_radar_state.json"), "w"), indent=0, sort_keys=True)
    print(f"{len(out['candidates'])} candidates, {len(out['upcomingSets'])} upcoming sets")

main()
