import json, os, re, sys, time, datetime, urllib.request, urllib.error
KEY = os.environ["PPT_KEY"]
TODAY = datetime.date.today().isoformat()
WANT = {"psa8","psa9","psa10","cgc9","cgc10","bgs9","bgs95","bgs10","ungraded","raw"}

def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def seed_from_probe():
    p = load("graded_probe.json", {})
    items = p.get("cards") if isinstance(p, dict) and "cards" in p else p
    if isinstance(items, dict): items = [dict(v, id=k) for k, v in items.items()]
    out = []
    for c in items or []:
        pid = c.get("productId") or c.get("pid")
        if pid: out.append({"id": str(c.get("id") or pid), "name": c.get("name") or c.get("title") or str(c.get("id") or pid), "productId": pid})
    return out

watch = load("graded_watch.json", None) or seed_from_probe()
# auto-extend watch with ledger cards worth ≥ $10 (singles, kanto holos, gyarados/magikarp)
tracked, prices = load("tracked.json", {}), load("prices.json", {}).get("prices", {})
have = {str(c["productId"]) for c in watch}
for lid, t in tracked.items():
    if not lid.startswith(("k-", "gy-", "mk-", "s-")): continue
    pid = t.get("productId")
    if not pid or str(pid) in have: continue
    if (prices.get(lid) or {}).get("market", 0) < 10: continue
    watch.append({"id": lid, "name": t.get("title") or lid, "productId": pid}); have.add(str(pid))
json.dump(watch, open("graded_watch.json", "w"), indent=1)

def num(x):
    try: return float(x)
    except Exception: return None

def pick(d, *names):
    for n in names:
        if isinstance(d, dict) and d.get(n) is not None: return d[n]

def slim(g):
    if not isinstance(g, dict): return None
    sm = g.get("smartMarketPrice")
    return {
        "n": pick(g, "count", "salesCount", "sales", "totalSales", "saleCount"),
        "median": num(pick(g, "medianPrice", "median")),
        "avg": num(pick(g, "averagePrice", "average", "avg")),
        "min": num(pick(g, "minPrice", "min")),
        "max": num(pick(g, "maxPrice", "max")),
        "p7": num(pick(g, "marketPrice7Day", "market7Day", "marketPrice")),
        "smart": num(sm.get("price")) if isinstance(sm, dict) else num(sm),
        "conf": sm.get("confidence") if isinstance(sm, dict) else None,
        "trend": pick(g, "trend", "marketTrend"),
    }

def fetch(pid):
    url = f"https://www.pokemonpricetracker.com/api/v2/cards?tcgPlayerId={pid}&includeEbay=true&limit=1"
    for a in range(3):
        try:
            r = urllib.request.Request(url, headers={"Authorization": f"Bearer {KEY}"})
            return json.load(urllib.request.urlopen(r, timeout=40))
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(20 * (a + 1)); continue
            return {"error": e.code}
        except Exception as e:
            time.sleep(3)
    return {"error": "fail"}

prev = load("graded.json", {"cards": {}})
res = {"generated": TODAY, "cards": {}}
for c in watch:
    j = fetch(c["productId"])
    d = j.get("data", j)
    if isinstance(d, list): d = d[0] if d else {}
    sbg = ((d.get("ebay") or {}).get("salesByGrade")) or {}
    grades = {}
    for k, v in sbg.items():
        nk = re.sub(r"[^a-z0-9]", "", k.lower())
        if nk in WANT: grades[nk] = slim(v)
    old = prev.get("cards", {}).get(c["id"], {})
    hist = old.get("history", {})
    for g, s in grades.items():
        if s and s.get("median") is not None:
            h = hist.setdefault(g, [])
            if not h or h[-1][0] != TODAY: h.append([TODAY, s["median"], s.get("n")])
    res["cards"][c["id"]] = {"name": c["name"], "productId": c["productId"], "grades": grades,
                             "history": hist, "ok": bool(grades)}
    time.sleep(1.2)
json.dump(res, open("graded.json", "w"), indent=1)
print(sum(1 for v in res["cards"].values() if v["ok"]), "of", len(res["cards"]), "cards with graded data")
