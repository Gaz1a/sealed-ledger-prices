#!/usr/bin/env python3
"""READ-ONLY audit: compare each single's tracked.json variant pin with the printing its title implies, using today's tcgcsv rows. Also dumps rows for the frozen items."""
import json, os, re, sys, urllib.request, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_market as sm
tr = json.load(open("tracked.json")); gm = json.load(open("group-map.json")); pr = json.load(open("prices.json"))["prices"]
sealed_re = re.compile(sm.SEALED_WORDS.pattern, re.I)
def expected(title, subs):
    t = title.lower()
    if "reverse" in t: want = ["Reverse Holofoil"]
    elif re.search(r"\bholo\b|\(holo|holo rare|holo\)", t):
        want = ["1st Edition Holofoil"] if "1st edition" in t else ["Unlimited Holofoil", "Holofoil"]
    else: want = ["Normal", "Unlimited"] if "1st edition" not in t else ["1st Edition"]
    return next((w for w in want if w in subs), None), want
cache, out, frozen = {}, {}, {}
FROZEN = ["gy-ancient-origins-20-98", "k-149", "gy-ex-firered-leafgreen-ex-109-112", "h-lumiose"]
for lid, t in tr.items():
    if sealed_re.search(t["title"]) and not re.search(r"\d+/\d+", t["title"]) and lid not in FROZEN: continue
    g = gm.get(str(t["productId"]))
    if not g: continue
    if tuple(g) not in cache: cache[tuple(g)] = (sm.get(f"{sm.BASE}/{g[0]}/{g[1]}/prices") or {}).get("results", [])
    rows = {r["subTypeName"]: r for r in cache[tuple(g)] if r["productId"] == t["productId"]}
    subs = {s: {"market": r.get("marketPrice"), "low": r.get("lowPrice"), "mid": r.get("midPrice")} for s, r in rows.items()}
    exp, want = expected(t["title"], subs)
    out[lid] = {"title": t["title"], "pin": t.get("variant"), "feedPrice": (pr.get(lid) or {}).get("market"), "subtypes": subs, "expectedPin": exp, "expectedFrom": want,
                "match": (t.get("variant") == exp) if exp else None, "priceUnderExpected": (subs.get(exp) or {}).get("market") if exp else None}
    if lid in FROZEN: frozen[lid] = {"productId": t["productId"], "tcgcsvToday": subs}
k = os.environ.get("PPT_KEY"); tok = os.environ.get("PRICECHARTING_TOKEN")
def get(url, h=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h or {"User-Agent": "sealed-ledger/1.0"}), timeout=40) as r: return json.load(r)
    except Exception as e: return {"error": str(e)[:80]}
for lid in frozen:
    pid = frozen[lid]["productId"]
    if k:
        d = get(f"https://www.pokemonpricetracker.com/api/v2/cards?tcgPlayerId={pid}&limit=1&includeHistory=true", {"Authorization": "Bearer " + k})
        d = d.get("data", d); d = d[0] if isinstance(d, list) and d else d
        p = (d or {}).get("prices") or {}
        frozen[lid]["ppt"] = {"name": (d or {}).get("name"), "set": (d or {}).get("setName"), "num": (d or {}).get("cardNumber"), "market": p.get("market"), "low": p.get("low"), "listings": p.get("listings"), "recentSales": p.get("recentSales"),
                              "lastUpdated": p.get("lastUpdated"), "variants": {v: {c: x.get("price") for c, x in cs.items() if c.startswith("Near") or c.startswith("Light")} for v, cs in (p.get("variants") or {}).items()}}
    if tok:
        pcid = json.load(open("pricecharting_ids.json")).get(lid, {}).get("pcId")
        if pcid:
            j = get("https://www.pricecharting.com/api/product?" + __import__("urllib.parse").parse.urlencode({"t": tok, "id": pcid}))
            frozen[lid]["pricecharting"] = {"name": j.get("product-name"), "console": j.get("console-name"), "ungraded": (j.get("loose-price") or 0) / 100}
json.dump({"generated": datetime.date.today().isoformat(), "pins": out, "frozen": frozen}, open("pin_audit.json", "w"), indent=1)
print(len(out), "audited;", sum(1 for v in out.values() if v["match"] is False), "mismatches")
