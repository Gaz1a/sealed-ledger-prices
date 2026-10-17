#!/usr/bin/env python3
"""Daily Portuguese Devir illustrated-booklet prices + buy scan -> booklet_prices.json, booklet_hits.json.
Price point per booklet per day: lowest live Portuguese/Devir buy-it-now ASKING price if one exists, else the matching English EX booklet's Cardmarket TREND ("English proxy").
All prices unverified (asking/trend, not sold). Buy scan: worldwide eBay Browse API, buy-it-now only, sealed only, all-in = item + shipping (+ estimated import cost for non-US origin).
Target = 0.85 x reference (median Portuguese ask if >=3 live listings, else English proxy trend). Never prints keys."""
import json, os, re, time, base64, datetime, urllib.request, urllib.parse, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = datetime.date.today().isoformat()
IMPORT_PCT = 0.10      # ESTIMATE added to (item+shipping) for items located outside the US (duty/brokerage/fees); not provided by eBay's API
TARGET_X = 0.85
SHIP_TO = {"X-EBAY-C-ENDUSERCTX": "contextualLocation=country=US,zip=91505"}
ROWS = {"bk-golem": "Golem", "bk-hooh": "Ho-Oh", "bk-lugia": "Lugia", "bk-machamp": "Machamp", "bk-omastar": "Omastar", "bk-ralts": "Ralts", "bk-treecko": "Treecko",
        "bk-exploud": "Exploud", "bk-mudkip": "Mudkip", "bk-rayquaza": "Rayquaza", "bk-torchic": "Torchic", "h-gengar-deck": "Gengar"}
OWNED = {"h-gengar-deck"}
LEDGER_TARGET = {"bk-golem": 104.98, "bk-hooh": 19.69, "bk-lugia": 25.36, "bk-machamp": 14.85, "bk-omastar": 18.88, "bk-ralts": 19.67, "bk-treecko": 21.69}   # from the ledger (Gaz, Oct 16)
MARKETS = ("EBAY_US", "EBAY_GB", "EBAY_DE", "EBAY_ES", "EBAY_IT", "EBAY_FR", "EBAY_CA", "EBAY_AU")
PT = re.compile(r"devir|livro ilustrado|estampas ilustradas|portugu[eê]s|portuguese|brasil|brazil", re.I)
BAD = re.compile(r"\blots?\b|loose|incomplete|missing|opened|aberto|usado|\bused\b|empty|cards only|proxy|custom|reprint|\bpsa\b|\bcgc\b|\bbgs\b|graded", re.I)
SEALED = re.compile(r"sealed|lacrado|selado|\bnew\b|\bnovo\b", re.I)
def ld(p, d):
    try: return json.load(open(os.path.join(ROOT, p)))
    except Exception: return d
def get(u, h=None, data=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=h or {"User-Agent": "sealed-ledger"}, data=data), timeout=60) as r: return json.load(r)
    except Exception: return {}
bk = ld("booklets.json", {}); fx = bk.get("fx") or 1.1208
cm = {}
for n, d in bk.get("decks", {}).items():
    m = re.search(r"Booklet - (.+)$", n)
    if m: cm[m.group(1)] = (n, d)
def usd(p):
    if not p: return None
    v, c = float(p["value"]), p.get("currency")
    return v if c == "USD" else round(v * fx, 2) if c == "EUR" else None
CID, CS = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
tok = get("https://api.ebay.com/identity/v1/oauth2/token", {"Authorization": "Basic " + base64.b64encode(f"{CID}:{CS}".encode()).decode(), "Content-Type": "application/x-www-form-urlencoded"},
          urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode()).get("access_token")
found = {k: {} for k in ROWS}
if tok:
    for mk in MARKETS:
        H = {"Authorization": "Bearer " + tok, "X-EBAY-C-MARKETPLACE-ID": mk, **SHIP_TO}
        for rid, nm in ROWS.items():
            for q in (f"Devir Livro Ilustrado {nm}", f"Estampas Ilustradas {nm}", f"Pokemon Devir {nm} Portuguese booklet", f"Pokemon Origem das Lendas {nm} Devir", f"Devir Pokemon {nm}"):
                time.sleep(0.35)
                j = get("https://api.ebay.com/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode({"q": q, "limit": 50, "filter": "buyingOptions:{FIXED_PRICE},deliveryCountry:US"}), H)
                for i in j.get("itemSummaries", []):
                    t = i.get("title", "")
                    if not re.search(r"(?<![a-z])" + re.escape(nm).replace("\\-", "[- ]?") + r"(?![a-z])", t, re.I) or not PT.search(t) or BAD.search(t): continue
                    if "FIXED_PRICE" not in (i.get("buyingOptions") or []): continue
                    item = usd(i.get("price"))
                    if item is None: continue
                    so = (i.get("shippingOptions") or [{}])[0].get("shippingCost")
                    ship = usd(so) if so else None
                    loc = (i.get("itemLocation") or {}).get("country")
                    imp = round((item + (ship or 0)) * IMPORT_PCT, 2) if loc and loc != "US" else 0.0
                    sealed = (i.get("condition") == "New") or bool(SEALED.search(t))
                    found[rid][i["itemId"]] = {"title": t, "url": i.get("itemWebUrl", "").split("?")[0], "marketplace": mk, "itemUSD": item, "shippingUSD": ship, "shipUnknown": ship is None,
                        "importEstUSD": imp, "allInUSD": round(item + (ship or 0) + imp, 2), "originCountry": loc, "condition": i.get("condition"), "sealed": sealed,
                        "sealedBasis": "condition New" if i.get("condition") == "New" else "title says sealed/new" if SEALED.search(t) else "unconfirmed",
                        "seller": (i.get("seller") or {}).get("username"), "feedbackPct": (i.get("seller") or {}).get("feedbackPercentage"), "feedbackScore": (i.get("seller") or {}).get("feedbackScore")}
prices = ld("booklet_prices.json", {"items": {}}); hits_out = {"generated": TODAY, "assumptions": {"importEstimatePct": IMPORT_PCT, "importNote": "ESTIMATE for non-US origin; eBay's API does not return duty/fees",
    "targetMultiplier": TARGET_X, "targets": "ledger targets for 7 rows; 0.85 x English Cardmarket trend for the rest once a trend exists", "reference": "median Portuguese ask if >=3 live listings, else English proxy (Cardmarket trend)", "shipTo": "Burbank CA 91505", "label": "unverified: asking prices/trend, not sold"}, "items": {}, "hits": []}
for rid, nm in ROWS.items():
    cmn, cd = cm.get(nm, (None, None))
    proxy = round(cd["trendEUR"] * fx, 2) if cd and cd.get("trendEUR") else None
    ls = sorted(found[rid].values(), key=lambda x: x["itemUSD"])
    e = prices["items"].setdefault(rid, {"name": nm, "history": []})
    if ls:
        pt = [TODAY, ls[0]["itemUSD"], "asking", "eBay " + ls[0]["marketplace"] + " " + ls[0]["url"], "unverified"]
    elif proxy is not None:
        pt = [TODAY, proxy, "english-proxy", f"Cardmarket trend, {cmn} (id {cd['id']}), EUR {cd['trendEUR']} x {fx}", "English proxy; unverified"]
    else: pt = None
    if pt: e["history"] = [h for h in e["history"] if h[0] != TODAY] + [pt]
    e["latest"] = pt; e["englishProxy"] = {"usd": proxy, "cardmarketLowEURNotUsed": (cd or {}).get("lowEUR") if proxy is None else None, "note": None if proxy is not None else "Cardmarket has the English booklet but no trend price; its low (if any) is an asking floor and is not used as a price", "product": cmn, "cardmarketId": (cd or {}).get("id")}; e["owned"] = rid in OWNED
    ref = round(sorted(x["itemUSD"] for x in ls)[len(ls) // 2], 2) if len(ls) >= 3 else proxy
    tgt = LEDGER_TARGET.get(rid) or (round(proxy * TARGET_X, 2) if proxy else None)
    tbasis = "ledger target" if rid in LEDGER_TARGET else "0.85 x English proxy (Cardmarket trend)" if proxy else "none (no English proxy trend yet)"
    rec = {"name": nm, "owned": rid in OWNED, "reference": ref, "referenceBasis": "median Portuguese ask" if len(ls) >= 3 else "English proxy (Cardmarket trend)", "target": tgt, "targetBasis": tbasis, "portugueseListings": len(ls), "listings": []}
    for x in ls:
        x = dict(x); x["underTarget"] = bool(tgt and x["sealed"] and x["allInUSD"] <= tgt)
        x["nearMiss"] = bool(tgt and x["sealed"] and tgt < x["allInUSD"] <= tgt * 1.15)
        rec["listings"].append(x)
        row = {"id": rid, "name": nm, "target": tgt, "allInUSD": x["allInUSD"], "itemUSD": x["itemUSD"], "shippingUSD": x["shippingUSD"], "shipUnknown": x["shipUnknown"], "importEstUSD": x["importEstUSD"],
               "title": x["title"], "seller": x["seller"], "feedbackPct": x["feedbackPct"], "feedbackScore": x["feedbackScore"], "itemLocation": x["originCountry"], "url": x["url"], "sealedBasis": x["sealedBasis"]}
        if rid not in OWNED:
            if x["underTarget"]: hits_out["hits"].append(row)
            elif x["nearMiss"]: hits_out.setdefault("nearMisses", []).append(row)
    hits_out["items"][rid] = rec
allL = [(r, l) for r, v in hits_out["items"].items() for l in v["listings"]]
hits_out["totals"] = {"portugueseBuyItNowListingsFound": len(allL), "ofWhichSealedConfirmed": sum(1 for _, l in allL if l["sealed"]), "unownedRows": sum(1 for r, _ in allL if r not in OWNED),
                      "perRow": {r: len(v["listings"]) for r, v in hits_out["items"].items()}, "note": "title-matched (Devir/Livro Ilustrado/Estampas Ilustradas/Portuguese + Pokemon name), buy-it-now, ships to US, excluding lots/loose/graded"}
hits_out.setdefault("nearMisses", [])
ew = ld("ebay_wants.json", {})
ew["booklets"] = {"generated": TODAY, "label": "unverified: asking prices; import cost is an estimate", "assumptions": hits_out["assumptions"], "totals": hits_out["totals"], "hits": hits_out["hits"], "nearMisses": hits_out["nearMisses"]}
json.dump(ew, open(os.path.join(ROOT, "ebay_wants.json"), "w"), indent=1, ensure_ascii=False)
prices["generated"] = TODAY
json.dump(prices, open(os.path.join(ROOT, "booklet_prices.json"), "w"), indent=1, ensure_ascii=False)
json.dump(hits_out, open(os.path.join(ROOT, "booklet_hits.json"), "w"), indent=1, ensure_ascii=False)
print({k: (v["portugueseListings"], v["reference"]) for k, v in hits_out["items"].items()}, "hits", len(hits_out["hits"]))
