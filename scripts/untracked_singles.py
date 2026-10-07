#!/usr/bin/env python3
"""One-off audit: top chase singles per English set (2023+ and held sets) -> untracked_singles.json.
tcgcsv (category 3) NM prices, CardNexus cross-check by exact tcgplayerId. Stdlib only. Never prints secrets."""
import json, os, re, sys, time, datetime, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_market as sm

ROOT, TODAY = sm.ROOT, sm.TODAY
MIN_MARKET, PER_SET = 25.0, 15
CN_BASE = "https://public-api.cardnexus.com/v1"
TOKEN = os.environ.get("CARDNEXUS_TOKEN", "")
PRICE_CALL_CAP = 450          # pricing-snapshot limit is 600/hr; stay well under
SLEEP = 1.3
EXCL = re.compile(r"code card|miscellaneous|jumbo|energy|world championship|deck|pokemon go tcg|mcdonald", re.I)

class Limited(Exception): pass

def norm(s):
    s = re.sub(r"^[A-Za-z0-9\-\.]+:\s*", "", s or "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", s.lower())).strip()

def fetch_group(g):
    gid = g["groupId"]
    prods = sm.get(f"{sm.BASE}/3/{gid}/products"); prices = sm.get(f"{sm.BASE}/3/{gid}/prices")
    if not prods or not prices: return gid, [], set()
    info, allp = {}, set()
    for p in prods.get("results", []):
        allp.add(p["productId"])
        ext = {x.get("name"): x.get("value") for x in (p.get("extendedData") or [])}
        if "Number" in ext: info[p["productId"]] = (p["name"], ext.get("Number"), ext.get("Rarity"))
    rows = []
    for r in prices.get("results", []):
        pid = r["productId"]
        if pid in info and r.get("marketPrice") is not None:
            n, num, rar = info[pid]
            rows.append({"name": n, "number": num, "rarity": rar, "productId": pid, "subtype": r.get("subTypeName"),
                         "market": r["marketPrice"], "low": r.get("lowPrice")})
    return gid, rows, allp

def cn(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(CN_BASE + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN); req.add_header("Accept", "application/json")
    if data: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 429: raise Limited()
        return e.code, None
    except Exception: return 0, None

def fin_norm(s):
    s = re.sub(r"[^a-z]", "", (s or "").lower())
    return "normal" if s in ("standard", "normal", "nonfoil") else s

def main():
    tracked = json.load(open(os.path.join(ROOT, "tracked.json")))
    tpids = {v["productId"] for v in tracked.values()}
    item_sets = {norm(v) for v in sm.load("item_sets.json", {}).values()}
    groups = (sm.get(f"{sm.BASE}/3/groups") or {}).get("results", [])
    gmeta = {g["groupId"]: g for g in groups}
    bygid = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for gid, rows, allp in ex.map(fetch_group, groups):
            bygid[gid] = (rows, bool(allp & tpids))
    if sum(len(r) for r, _ in bygid.values()) < 5000: sys.exit("too few singles; aborting")
    cards, sets_used = [], {}
    for gid, (rows, held_pid) in bygid.items():
        g = gmeta[gid]; pub = (g.get("publishedOn") or "")[:10]
        main_set = pub >= "2023-01-01" and not EXCL.search(g["name"])
        s = norm(g["name"])
        held = held_pid or any(s == x or (len(x) > 5 and (x in s or s in x)) for x in item_sets)
        if not (main_set or held): continue
        top = sorted([r for r in rows if r["market"] >= MIN_MARKET], key=lambda r: -r["market"])[:PER_SET]
        sets_used[g["name"]] = {"groupId": gid, "released": pub, "held": held, "mainSet2023plus": main_set}
        for r in top:
            lo, m = r["low"], r["market"]
            flag = bool(lo and (lo < 0.5 * m or m > 3 * lo))
            cards.append(dict(r, set=g["name"], groupId=gid, released=pub, tracked=r["productId"] in tpids,
                              setHeld=held, price_sanity=("suspect" if flag else "ok"),
                              cardnexus=None))
    cards.sort(key=lambda c: -c["market"])
    print(f"{len(cards)} cards from {len(sets_used)} sets", file=sys.stderr)

    note = "CardNexus skipped (no token)"
    if TOKEN:
        note = "ok"; matched = {}
        try:
            pids = sorted({c["productId"] for c in cards})
            for i in range(0, len(pids), 100):          # catalogue search, exact tcgplayerId batches
                chunk = pids[i:i + 100]; off = 0
                while True:
                    st, j = cn("POST", "/products/search", {"tcgplayerId": chunk, "limit": 200, "offset": off}); time.sleep(SLEEP)
                    if st != 200 or not isinstance(j, dict): break
                    for p in j.get("data", []):
                        for e in (p.get("externalIds") or {}).get("tcgplayer", []) or []:
                            if e.get("id") in chunk: matched.setdefault(e["id"], []).append((p["id"], e.get("finish")))
                    pg = j.get("pagination") or {}
                    if not pg.get("hasMore"): break
                    off += 200
            calls = 0; cache = {}
            for c in cards:
                cands = matched.get(c["productId"], [])
                if not cands: continue
                want = fin_norm(c["subtype"])
                hit = [x for x in cands if fin_norm(x[1]) == want]
                if len(hit) != 1: continue                 # no confident match: leave null
                cnid, fin = hit[0]
                if cnid not in cache:
                    if calls >= PRICE_CALL_CAP: continue
                    st, j = cn("GET", f"/products/{cnid}/prices"); calls += 1; time.sleep(SLEEP)
                    cache[cnid] = j if st == 200 and isinstance(j, dict) else None
                j = cache[cnid]
                if not j: continue
                blk = (j.get("pricesByFinish") or {}).get(fin) or {}
                cm, tcg = blk.get("cardmarket") or {}, blk.get("tcgplayer") or {}
                c["cardnexus"] = {"cnId": cnid, "finish": fin, "cardmarketEUR": cm.get("marketValue"), "cardmarketLowEUR": cm.get("low"),
                                  "tcgplayerUSD": tcg.get("marketValue")}
            note = f"ok; {sum(1 for c in cards if c['cardnexus'])} matched, {calls} pricing calls"
        except Limited:
            note = "rate limited (429); remaining cards left null"
    per_set = {}
    for c in cards:
        if not c["tracked"] and c["set"] not in per_set: per_set[c["set"]] = c
    out = {"generated": TODAY.isoformat(), "minMarket": MIN_MARKET, "perSetCap": PER_SET,
           "priceBasis": "TCGplayer market, Near Mint, per subtype (tcgcsv category 3)",
           "cardnexusNote": note, "sets": sets_used, "cards": cards, "per_set": per_set}
    json.dump(out, open(os.path.join(ROOT, "untracked_singles.json"), "w"), indent=1, ensure_ascii=False)
    print(f"cards {len(cards)}, untracked {sum(not c['tracked'] for c in cards)}, suspect {sum(c['price_sanity']=='suspect' for c in cards)}, cardnexus: {note}")

if __name__ == "__main__":
    main()
