#!/usr/bin/env python3
"""Daily + weekly eBay sweep for every Jumbo watch entry -> jumbo_listings.json, jumbo_coverage.json.
Input jumbo_watch_queries.json (list or {id: entry}); entry fields used: id, queries[] (search strings), orig (native-language name, string or list), targetAllIn (USD), lang (optional; else jumbo_ids.json), title (optional).
Searches eBay Browse API on every marketplace in MARKETS (Buy It Now + auctions, ships to US), same credentials/route as bk_booklets.py / scan_ebay_jumbo.py.
Quota guard: each run takes the least-recently-swept entries until MAX_CALLS is used, stops at the first eBay 429 (so a full sweep may take several days when the API quota is tight).
all-in = (item or current bid + shipping) x 1.10. Listings are unverified asks/bids, not sold prices."""
import json, os, re, sys, time, base64, datetime, urllib.request, urllib.parse, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CID, CSEC = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
MAX_CALLS = int(os.environ.get("MAX_CALLS", "1800"))
MARKETS = [m for m in os.environ.get("MARKETS", "EBAY_US,EBAY_GB,EBAY_DE,EBAY_ES,EBAY_IT,EBAY_FR,EBAY_CA,EBAY_AU").split(",") if m]
TAX, NOW = 1.10, datetime.datetime.utcnow()
TODAY = NOW.strftime("%Y-%m-%d")
SHIP_TO = {"X-EBAY-C-ENDUSERCTX": "contextualLocation=country=US,zip=91505"}
NOISE = re.compile(r"\bempty\b|\bopened\b|\bopen box\b|box only|no cards?\b|cards? only|code cards?|\bpacks? only\b|\bempty pack|wrapper|\bproxy\b|\bcustom\b|\breprint\b|replica|fan ?art|\blots?\b|\bbundle\b|\bpsa\b|\bcgc\b|\bbgs\b|\bgraded\b|\bslab\b|\bfake\b|\bplush\b|\bdigital\b|damaged|\bdmg\b", re.I)
LANGS = {"english": r"\benglish\b", "japanese": r"japan|\bjp\b|日本|ポケモン", "korean": r"korea|한국|포켓몬", "french": r"fran[cç]ais|french|\bfr\b", "portuguese": r"portugu|\bpt\b|\bbr\b", "german": r"deutsch|german", "italian": r"italian|italiano", "spanish": r"espa[nñ]ol|spanish|castellano", "chinese": r"chinese|中文|繁體|简体"}
GENERIC = {"box", "collection", "premium", "special", "pokemon", "the", "and", "card", "cards", "set", "jumbo", "display", "booster", "case", "promo", "pack"}
RL = {"hit": False}; DIAG = {"calls": 0, "errors": {}}
def ld(n, d):
    try: return json.load(open(os.path.join(ROOT, n)))
    except Exception: return d
def get(url, H):
    DIAG["calls"] += 1
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        k = "%s %s" % (e.code, H.get("X-EBAY-C-MARKETPLACE-ID", "")); DIAG["errors"][k] = DIAG["errors"].get(k, 0) + 1
        if e.code == 429: RL["hit"] = True
        return {}
    except Exception as e:
        k = type(e).__name__; DIAG["errors"][k] = DIAG["errors"].get(k, 0) + 1; return {}
def token():
    a = base64.b64encode(f"{CID}:{CSEC}".encode()).decode()
    b = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://api.ebay.com/identity/v1/oauth2/token", data=b, headers={"Authorization": f"Basic {a}", "Content-Type": "application/x-www-form-urlencoded"}), timeout=30) as x: return json.load(x)["access_token"]
FX = {"USD": 1.0}
def load_fx():
    try:
        r = json.load(urllib.request.urlopen("https://api.frankfurter.app/latest?from=USD", timeout=30))["rates"]
        FX.update({c: 1.0 / v for c, v in r.items() if v})       # 1 unit of c in USD
    except Exception: pass
def usd(p):
    if not p or p.get("value") is None: return None
    rate = FX.get(p.get("currency", "USD"))
    return round(float(p["value"]) * rate, 2) if rate else None
def norm_entries(raw):
    items = list(raw.items()) if isinstance(raw, dict) else [(e.get("id"), e) for e in raw]
    out = []
    for k, e in items:
        e = dict(e) if isinstance(e, dict) else {"queries": e}
        e["id"] = e.get("id") or k
        out.append(e)
    return out
def core_tokens(s): return [w for w in re.findall(r"[a-z0-9]{3,}", (s or "").lower()) if w not in GENERIC]
def relevant(title, ent):
    t = title.lower()
    names = [ent.get("title") or ""] + ([ent["orig"]] if isinstance(ent.get("orig"), str) else list(ent.get("orig") or []))
    for n in names:
        tok = core_tokens(n)
        if tok and sum(1 for w in tok if w in t) >= max(1, round(0.6 * len(tok))): return True
    return False
def lang_ok(title, lang):
    lang = (lang or "english").lower().split(";")[0].strip()
    others = [v for k, v in LANGS.items() if k != lang]
    if lang == "english": return not any(re.search(v, title, re.I) for v in others if v != LANGS["english"])
    return bool(LANGS.get(lang) and re.search(LANGS[lang], title, re.I))
def record(h, ent, mk, q, lang):
    t = h.get("title", "")
    if NOISE.search(t) or not relevant(t, ent) or not lang_ok(t, lang): return None
    auc = "AUCTION" in (h.get("buyingOptions") or [])
    price = usd(h.get("currentBidPrice") or h.get("price"))
    if price is None: return None
    so = (h.get("shippingOptions") or [{}])[0].get("shippingCost"); ship = usd(so) if so else None
    allin = round((price + (ship or 0)) * TAX, 2)
    tgt = ent.get("targetAllIn"); s = h.get("seller") or {}
    return {"id": ent["id"], "itemId": h.get("itemId"), "title": t, "price": price, "shipping": ship, "shipUnknown": ship is None, "allIn": allin,
            "format": "auction" if auc else "buy-it-now", "bids": h.get("bidCount") if auc else None, "ends": h.get("itemEndDate"), "seller": s.get("username"),
            "feedbackPct": s.get("feedbackPercentage"), "feedbackScore": s.get("feedbackScore"), "location": (h.get("itemLocation") or {}).get("country"),
            "marketplace": mk, "query": q, "condition": h.get("condition"), "url": (h.get("itemWebUrl") or "").split("?")[0],
            "underTarget": bool(tgt) and allin <= tgt, "targetAllIn": tgt, "seen": TODAY}
def main():
    ents = norm_entries(ld("jumbo_watch_queries.json", []))
    cov = ld("jumbo_coverage.json", {"entries": {}})
    if not ents:
        cov.update({"status": "jumbo_watch_queries.json missing or empty - nothing swept", "checkedAt": TODAY}); json.dump(cov, open(os.path.join(ROOT, "jumbo_coverage.json"), "w"), indent=1); print(cov["status"]); return
    langs = {k: v.get("lang") for k, v in ld("jumbo_ids.json", {}).items()}; cats = {x["id"]: x for x in ld("jumbo_catalogue.json", [])}
    old = ld("jumbo_listings.json", {"listings": []}); keep = {r["itemId"]: r for r in old.get("listings", [])}
    if not (CID and CSEC): print("no eBay credentials"); return
    load_fx(); H0 = {"Authorization": "Bearer " + token(), **SHIP_TO}
    st = cov.setdefault("entries", {})
    order = sorted(ents, key=lambda e: (st.get(e["id"], {}).get("lastChecked") or "", e["id"]))
    swept = []
    for ent in order:
        if RL["hit"] or DIAG["calls"] >= MAX_CALLS: break
        eid = ent["id"]; lang = ent.get("lang") or langs.get(eid) or (cats.get(eid) or {}).get("lang")
        ent.setdefault("title", (cats.get(eid) or {}).get("title"))
        qs = list(ent.get("queries") or [])
        orig = ent.get("orig"); qs += ([orig] if isinstance(orig, str) else list(orig or []))
        if not qs: qs = [ent["title"]] if ent.get("title") else []
        tgt = ent.get("targetAllIn"); cap = max(60, round((tgt or 20) * 3))
        filt = f"price:[1..{cap}],priceCurrency:USD,buyingOptions:{{FIXED_PRICE|AUCTION}},deliveryCountry:US"
        found = {}
        for mk in MARKETS:
            for q in dict.fromkeys(qs):
                if RL["hit"]: break
                j = get("https://api.ebay.com/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode({"q": q, "filter": filt, "limit": 50, "sort": "price"}), {**H0, "X-EBAY-C-MARKETPLACE-ID": mk})
                time.sleep(0.3)
                for h in j.get("itemSummaries", []):
                    r = record(h, ent, mk, q, lang)
                    if r and r["itemId"] not in found: found[r["itemId"]] = r
        if RL["hit"]: break           # entry only partially searched: do not record it as checked
        for iid in [i for i, r in keep.items() if r["id"] == eid]: keep.pop(iid)
        keep.update(found); swept.append(eid)
        e = st.setdefault(eid, {}); e["lastChecked"] = TODAY; e["lastCount"] = len(found)
        if found: e["lastHit"] = TODAY
    for iid in [i for i, r in keep.items() if r.get("ends") and r["ends"] < NOW.strftime("%Y-%m-%dT%H:%M:%S")]: keep.pop(iid)      # ended
    listings = sorted(keep.values(), key=lambda r: (not r["underTarget"], r["allIn"]))
    changed = {r["itemId"]: (r["allIn"], r["bids"]) for r in listings} != {r["itemId"]: (r["allIn"], r.get("bids")) for r in old.get("listings", [])}
    if changed or not old.get("generated"):
        json.dump({"generated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "listings": listings, "underTarget": sum(1 for r in listings if r["underTarget"]),
                   "note": "eBay asks / current bids, unverified; all-in = (price or current bid + shipping) x 1.10; underTarget compares all-in with the entry's targetAllIn"}, open(os.path.join(ROOT, "jumbo_listings.json"), "w"), indent=1)
    ids = {e["id"] for e in ents}; cutoff = (NOW - datetime.timedelta(days=14)).strftime("%Y-%m-%d")
    nohit = [i for i in ids if (st.get(i, {}).get("lastHit") or "") < cutoff and (st.get(i, {}).get("lastChecked"))]
    never = [i for i in ids if not st.get(i, {}).get("lastChecked")]
    live = {r["id"] for r in listings}
    cov.update({"checkedAt": TODAY, "status": "rate limited (eBay 429): sweep stopped early, remaining entries rotate to the next run" if RL["hit"] else "ok", "entriesTotal": len(ids),
                "entriesChecked": len(ids) - len(never), "entriesCheckedThisRun": len(swept), "entriesWithLiveListing": len(live & ids), "entriesNoHitIn14Days": len(nohit), "neverChecked": len(never),
                "noHit14DayIds": sorted(nohit), "markets": MARKETS, "apiCalls": DIAG["calls"], "errors": DIAG["errors"], "maxCalls": MAX_CALLS})
    json.dump(cov, open(os.path.join(ROOT, "jumbo_coverage.json"), "w"), indent=1)
    print(cov["status"], "swept", len(swept), "of", len(ids), "listings", len(listings), "calls", DIAG["calls"])
if __name__ == "__main__": main()
