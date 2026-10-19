#!/usr/bin/env python3
"""Daily + weekly eBay sweep for every Jumbo watch entry -> jumbo_listings.json, jumbo_coverage.json.
Input jumbo_watch_queries.json {generated, rule, entries:[...]}; entry fields used: id, title, orig (native-language name, '' for English), lang, price, targetAllIn (USD, may be null). The file's web-search `queries` (site: operators) are ignored.
Search term = orig if set else title (+ 'pokemon' for title searches); a listing must match the title or orig. Marketplaces by language: English US/GB/CA/AU; French FR/DE/IT/ES; Korean/Japanese/Portuguese/other: all 8.
Buy It Now + auctions, ships to US, same credentials/route as bk_booklets.py / scan_ebay_jumbo.py.
Quota guard: each run takes the least-recently-swept entries until MAX_CALLS is used, stops at the first eBay 429 (so a full sweep may take several days when the API quota is tight).
all-in = (item or current bid + shipping) x 1.10. Listings are unverified asks/bids, not sold prices."""
import json, os, re, sys, time, base64, datetime, urllib.request, urllib.parse, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CID, CSEC = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
MAX_CALLS = int(os.environ.get("MAX_CALLS", "1800"))
ALL = ["EBAY_US", "EBAY_GB", "EBAY_DE", "EBAY_ES", "EBAY_IT", "EBAY_FR", "EBAY_CA", "EBAY_AU"]
BY_LANG = {"english": ["EBAY_US", "EBAY_GB", "EBAY_CA", "EBAY_AU"], "french": ["EBAY_FR", "EBAY_DE", "EBAY_IT", "EBAY_ES"]}
MARKETS = ALL
def markets_for(lang): return BY_LANG.get((lang or "english").lower().split(";")[0].strip(), ALL)
TAX, NOW = 1.10, datetime.datetime.utcnow()
TODAY = NOW.strftime("%Y-%m-%d")
SHIP_TO = {"X-EBAY-C-ENDUSERCTX": "contextualLocation=country=US,zip=91505"}
NOISE = re.compile(r"\bempty\b|\bopened\b|\bopen box\b|box only|no cards?\b|cards? only|code cards?|\bpacks? only\b|\bempty pack|wrapper|\bproxy\b|\bcustom\b|\breprint\b|replica|fan ?art|\blots?\b|\bbundle\b|\bpsa\b|\bcgc\b|\bbgs\b|\bgraded\b|\bslab\b|\bfake\b|\bplush\b|\bdigital\b|damaged|\bdmg\b|\bcases?\b|\bacrylic\b|\bprotectors?\b|\bsleeves?\b|\bbinders?\b|\bstands?\b|display case|\btop ?loaders?\b|\bmagnetic\b", re.I)
SINGLE_NUM = re.compile(r"#\s?\d{1,3}\b|\b\d{1,3}\s?/\s?\d{2,3}\b|\b[A-Za-z]{1,4}-?\d{2,3}\b|\b0\d{2}\b")
SET_WORD = re.compile(r"\b(box|boxes|collection|tin|tins|set|display|booster|bundle|deck|pack|case|chest|binder|kit)\b", re.I)
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
FXINFO = {}
FX_UA = {"User-Agent": "sealed-ledger-prices/1.0 (+https://github.com/Gaz1a/sealed-ledger-prices)", "Accept": "application/json, application/xml, text/xml, */*"}
FALLBACK_RATES = {"EUR": 1.1253, "GBP": 1.3335, "CAD": 0.7062, "AUD": 0.6959, "JPY": 0.006328, "KRW": 0.000751}   # 16 Oct 2026 reference rates, USD per 1 unit
FALLBACK_DATE = "2026-10-16"
FX_CCY = ("EUR", "GBP", "CAD", "AUD", "JPY", "KRW")
def _fx_get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=FX_UA), timeout=30).read()
def fx_ecb():
    import re as _re
    x = _fx_get("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml").decode()
    date = _re.search(r"time=['\"](\d{4}-\d{2}-\d{2})['\"]", x).group(1)
    per_eur = {m.group(1): float(m.group(2)) for m in _re.finditer(r"currency=['\"]([A-Z]{3})['\"]\s+rate=['\"]([\d.]+)['\"]", x)}
    usd_per_eur = per_eur["USD"]
    return date, {"EUR": usd_per_eur, **{c: usd_per_eur / v for c, v in per_eur.items() if c != "USD" and v}}
def fx_frankfurter():
    j = json.loads(_fx_get("https://api.frankfurter.app/latest?from=USD"))
    return j["date"], {c: 1.0 / v for c, v in j["rates"].items() if v}
def fx_erapi():
    j = json.loads(_fx_get("https://open.er-api.com/v6/latest/USD"))
    d = datetime.datetime.strptime(j["time_last_update_utc"][5:16], "%d %b %Y").strftime("%Y-%m-%d")
    return d, {c: 1.0 / v for c, v in j["rates"].items() if v}
def load_fx():
    for name, fn in (("ecb", fx_ecb), ("frankfurter", fx_frankfurter), ("open.er-api", fx_erapi)):
        try:
            date, rates = fn(); rates = {c: round(rates[c], 6) for c in FX_CCY if c in rates}
            if not all(c in rates for c in ("EUR", "GBP", "CAD", "AUD")): raise ValueError("missing currencies")
            FX.update(rates); FXINFO.update({"date": date, "source": name, "rates": {"USD": 1.0, **rates}, "estimated": False}); DIAG["fxSource"] = name; return
        except Exception as ex: DIAG.setdefault("fxErrors", []).append(f"{name}: {str(ex)[:80]}")
    FX.update(FALLBACK_RATES); DIAG["fxSource"] = "fallback-constants"
    FXINFO.update({"date": FALLBACK_DATE, "source": "fallback-constants", "rates": {"USD": 1.0, **FALLBACK_RATES}, "estimated": True})
def fx_streak(cov):
    """consecutive days (ending today) on which the fallback constants were used; persisted in jumbo_coverage.json"""
    if not FXINFO.get("estimated"): return 0
    prev = cov.get("fx") or {}; pd = prev.get("lastFallbackDate") or (cov.get("checkedAt") if cov.get("fxSource") == "fallback-constants" else None)
    ps = prev.get("fallbackStreakDays") or (1 if pd else 0)
    if not pd: return 1
    gap = (datetime.date.fromisoformat(TODAY) - datetime.date.fromisoformat(pd)).days
    return ps if gap == 0 else (ps + 1 if gap == 1 else 1)
FX_FAIL_DAYS = 3
def usd(p):
    if not p or p.get("value") is None: return None
    rate = FX.get(p.get("currency", "USD"))
    return round(float(p["value"]) * rate, 2) if rate else None
def fx_est(p):
    """True when this price was converted with the fallback constants (not a live rate)"""
    return bool(FXINFO.get("estimated") and p and (p.get("currency", "USD") != "USD"))
def norm_entries(raw):
    if isinstance(raw, dict) and isinstance(raw.get("entries"), list): raw = raw["entries"]
    items = list(raw.items()) if isinstance(raw, dict) else [(e.get("id"), e) for e in raw]
    out = []
    for k, e in items:
        e = dict(e) if isinstance(e, dict) else {"queries": e}
        e["id"] = e.get("id") or k
        out.append(e)
    return out
def core_tokens(s): return [w for w in re.findall(r"[a-z0-9]{3,}", (s or "").lower()) if w not in GENERIC]
TYPE = {"box", "collection", "premium", "display", "binder", "special", "tin", "challenge", "case", "insert", "pack", "set", "jumbo", "oversized", "oversize"}
def relevant(title, ent):
    t = title.lower()
    tt = set(re.findall(r"[a-z]+", (ent.get("title") or "").lower())) & TYPE
    if tt and not (tt & set(re.findall(r"[a-z]+", t)) or re.search(r"jumbo|oversize|box|display|collection", t)): return False
    names = [ent.get("title") or ""] + ([ent["orig"]] if isinstance(ent.get("orig"), str) else list(ent.get("orig") or []))
    for n in names:
        tok = core_tokens(n)
        if tok and sum(1 for w in tok if w in t) >= max(1, round(0.8 * len(tok))): return True
    return False
def lang_ok(title, lang):
    lang = (lang or "english").lower().split(";")[0].strip()
    others = [v for k, v in LANGS.items() if k != lang]
    if lang == "english": return not any(re.search(v, title, re.I) for v in others if v != LANGS["english"])
    return bool(LANGS.get(lang) and re.search(LANGS[lang], title, re.I))
def record(h, ent, mk, q, lang):
    t = h.get("title", "")
    dr = DIAG.setdefault("drops", {}).setdefault(mk, {"noise": 0, "irrelevant": 0, "lang": 0, "floor": 0})
    if NOISE.search(t): dr["noise"] += 1; return None
    if SINGLE_NUM.search(t) and not SET_WORD.search(t): dr.setdefault("single", 0); dr["single"] += 1; return None
    if not relevant(t, ent): dr["irrelevant"] += 1; return None
    if not lang_ok(t, lang): dr["lang"] += 1; return None
    auc = "AUCTION" in (h.get("buyingOptions") or [])
    praw = h.get("currentBidPrice") or h.get("price"); price = usd(praw)
    if price is None:
        c = (h.get("currentBidPrice") or h.get("price") or {}).get("currency"); DIAG.setdefault("noPrice", {}); DIAG["noPrice"][f"{mk}:{c}"] = DIAG["noPrice"].get(f"{mk}:{c}", 0) + 1
        return None
    so = (h.get("shippingOptions") or [{}])[0].get("shippingCost"); ship = usd(so) if so else None
    allin = round((price + (ship or 0)) * TAX, 2)
    tgt = ent.get("targetAllIn"); ref = tgt or ent.get("price"); s = h.get("seller") or {}
    if allin < (0.25 * ref if ref else 10): dr["floor"] += 1; return None       # accessories / $1 placeholder listings; a real jumbo item never sells this far below market; s = h.get("seller") or {}
    return {"id": ent["id"], "itemId": h.get("itemId"), "title": t, "price": price, "shipping": ship, "shipUnknown": ship is None, "allIn": allin,
            "format": "auction" if auc else "buy-it-now", "bids": h.get("bidCount") if auc else None, "ends": h.get("itemEndDate"), "seller": s.get("username"),
            "feedbackPct": s.get("feedbackPercentage"), "feedbackScore": s.get("feedbackScore"), "location": (h.get("itemLocation") or {}).get("country"),
            "marketplace": mk, "query": q, "condition": h.get("condition"), "url": (h.get("itemWebUrl") or "").split("?")[0],
            "underTarget": (0.25 * tgt <= allin <= tgt) if tgt else None, "discovery": not tgt, "targetAllIn": tgt, "seen": TODAY,
            "priceCurrency": (praw or {}).get("currency"), "fxEstimated": fx_est(praw)}
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
    order = sorted(ents, key=lambda e: (st.get(e["id"], {}).get("lastChecked") or "", e.get("price") is not None, -(e.get("price") or 0), e["id"]))      # least recently swept first; within that, unpriced entries, then highest price first
    swept = []
    for ent in order:
        if RL["hit"] or DIAG["calls"] >= MAX_CALLS: break
        eid = ent["id"]; lang = ent.get("lang") or langs.get(eid) or (cats.get(eid) or {}).get("lang")
        ent.setdefault("title", (cats.get(eid) or {}).get("title"))
        orig = ent.get("orig"); term = orig if isinstance(orig, str) and orig.strip() else ((ent.get("title") or "") + " pokemon")
        qs = [term] if term.strip() else []
        tgt = ent.get("targetAllIn"); ref = tgt or ent.get("price")
        filt = (f"price:[1..{max(60, round(ref * 3))}]," if ref else "price:[1..5000],") + "priceCurrency:USD,buyingOptions:{FIXED_PRICE|AUCTION},deliveryCountry:US"
        found = {}
        for mk in markets_for(lang):
            for q in dict.fromkeys(qs):
                if RL["hit"]: break
                j = get("https://api.ebay.com/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode({"q": q, "filter": filt, "limit": 50, "sort": "price"}), {**H0, "X-EBAY-C-MARKETPLACE-ID": mk})
                time.sleep(0.3)
                pm = DIAG.setdefault("perMarket", {}).setdefault(mk, {"queries": 0, "raw": 0, "kept": 0}); pm["queries"] += 1; pm["raw"] += len(j.get("itemSummaries", []))
                for h in j.get("itemSummaries", []):
                    r = record(h, ent, mk, q, lang)
                    if r: pm["kept"] += 1
                    if r and r["itemId"] not in found: found[r["itemId"]] = r
        if RL["hit"]: break           # entry only partially searched: do not record it as checked
        for iid in [i for i, r in keep.items() if r["id"] == eid]: keep.pop(iid)
        keep.update(found); swept.append(eid)
        e = st.setdefault(eid, {}); e["lastChecked"] = TODAY; e["lastCount"] = len(found)
        if found: e["lastHit"] = TODAY
    for iid in [i for i, r in keep.items() if r.get("ends") and r["ends"] < NOW.strftime("%Y-%m-%dT%H:%M:%S")]: keep.pop(iid)      # ended
    listings = sorted(keep.values(), key=lambda r: (not r["underTarget"], r["allIn"]))
    changed = {r["itemId"]: (r["allIn"], r["bids"]) for r in listings} != {r["itemId"]: (r["allIn"], r.get("bids")) for r in old.get("listings", [])}
    if changed or not old.get("generated") or (old.get("fx") or {}).get("source") != FXINFO.get("source") or (old.get("fx") or {}).get("date") != FXINFO.get("date"):
        json.dump({"generated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "fx": {"date": FXINFO.get("date"), "source": FXINFO.get("source"), "rates": FXINFO.get("rates"), "estimated": FXINFO.get("estimated")}, "listings": listings, "underTarget": sum(1 for r in listings if r["underTarget"]), "discovery": sum(1 for r in listings if r.get("discovery")),
                   "note": "eBay asks / current bids, unverified; all-in = (price or current bid + shipping) x 1.10; underTarget compares all-in with the entry's targetAllIn"}, open(os.path.join(ROOT, "jumbo_listings.json"), "w"), indent=1)
    ids = {e["id"] for e in ents}; cutoff = (NOW - datetime.timedelta(days=14)).strftime("%Y-%m-%d")
    nohit = [i for i in ids if (st.get(i, {}).get("lastHit") or "") < cutoff and (st.get(i, {}).get("lastChecked"))]
    never = [i for i in ids if not st.get(i, {}).get("lastChecked")]
    live = {r["id"] for r in listings}
    cov.update({"checkedAt": TODAY, "status": "rate limited (eBay 429): sweep stopped early, remaining entries rotate to the next run" if RL["hit"] else "ok", "entriesTotal": len(ids),
                "entriesChecked": len(ids) - len(never), "entriesCheckedThisRun": len(swept), "entriesWithLiveListing": len(live & ids), "entriesNoHitIn14Days": len(nohit), "neverChecked": len(never),
                "noHit14DayIds": sorted(nohit), "markets": "by language: English US/GB/CA/AU; French FR/DE/IT/ES; others all 8", "apiCalls": DIAG["calls"], "errors": DIAG["errors"], "perMarket": DIAG.get("perMarket"), "drops": DIAG.get("drops"), "noPrice": DIAG.get("noPrice"), "fxSource": DIAG.get("fxSource"), "fxErrors": DIAG.get("fxErrors"), "maxCalls": MAX_CALLS})
    streak = fx_streak(cov)
    cov["fx"] = {"date": FXINFO.get("date"), "source": FXINFO.get("source"), "rates": FXINFO.get("rates"), "estimated": FXINFO.get("estimated"),
                 "fallbackStreakDays": streak, "lastFallbackDate": TODAY if streak else None, "errors": DIAG.get("fxErrors")}
    fail = streak > FX_FAIL_DAYS
    if fail: cov["status"] = f"FAILED: FX fallback constants used {streak} days in a row - all live FX sources are failing; converted prices are estimates"
    json.dump(cov, open(os.path.join(ROOT, "jumbo_coverage.json"), "w"), indent=1)
    print(cov["status"], "swept", len(swept), "of", len(ids), "listings", len(listings), "calls", DIAG["calls"], "fx", FXINFO.get("source"), FXINFO.get("date"))
    if fail: sys.exit(1)
if __name__ == "__main__": main()
