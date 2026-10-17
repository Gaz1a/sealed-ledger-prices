#!/usr/bin/env python3
"""Daily Portuguese Devir illustrated-booklet prices + buy scan -> booklet_prices.json, booklet_hits.json.
Price point per booklet per day: lowest live Portuguese/Devir buy-it-now ASKING price if one exists, else the matching English EX booklet's Cardmarket TREND ("English proxy").
All prices unverified (asking/trend, not sold). Buy scan: worldwide eBay Browse API, buy-it-now only, sealed only, all-in = item + shipping (+ estimated import cost for non-US origin).
Target = 0.85 x reference (median Portuguese ask if >=3 live listings, else English proxy trend). Never prints keys."""
import json, os, re, time, base64, datetime, urllib.request, urllib.parse, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = datetime.date.today().isoformat()
IMPORT_PCT = 0.10      # ESTIMATE added to (item+shipping) for items located outside the US (duty/brokerage/fees); not provided by eBay's API
SHIP_TO = {"X-EBAY-C-ENDUSERCTX": "contextualLocation=country=US,zip=91505"}
ROWS = {"bk-golem": "Golem", "bk-hooh": "Ho-Oh", "bk-lugia": "Lugia", "bk-machamp": "Machamp", "bk-omastar": "Omastar", "bk-ralts": "Ralts", "bk-treecko": "Treecko",
        "bk-exploud": "Exploud", "bk-mudkip": "Mudkip", "bk-rayquaza": "Rayquaza", "bk-torchic": "Torchic", "h-gengar-deck": "Gengar"}
OWNED = {"h-gengar-deck"}
BELOW_REF = 0.85       # flag when all-in <= 85% of the lowest Portuguese sealed all-in seen so far (>=15% below)
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
prices = ld("booklet_prices.json", {"items": {}})
refs = ld("booklet_refs.json", {"items": {}}); maxp = ld("booklet_max.json", {})   # booklet_max.json: {"bk-golem": 60, ...} all-in max you set; optional
out = {"generated": TODAY, "label": "unverified: asking prices, not sold; import cost is an ESTIMATE", "assumptions": {"importEstimatePct": IMPORT_PCT, "shipTo": "Burbank CA 91505",
       "rules": ["reference = lowest all-in Portuguese Devir SEALED asking price seen so far (known shipping only)", "flag if all-in <= 0.85 x reference, or <= your max for that booklet",
                 "no sealed Portuguese reference yet -> flag any sealed listing the first time its item id appears", "only sealed/new listings are flagged; others listed under notSealed", "shipping not shown -> all-in is 'shipping unknown' (item+import shown as lower bound)"]},
       "flags": [], "notSealed": [], "counts": {}, "items": {}}
for rid, nm in ROWS.items():
    cmn, cd = cm.get(nm, (None, None))
    proxy = round(cd["trendEUR"] * fx, 2) if cd and cd.get("trendEUR") else None
    ls = sorted(found[rid].values(), key=lambda x: x["itemUSD"])
    e = prices["items"].setdefault(rid, {"name": nm, "history": []})
    if ls: pt = [TODAY, ls[0]["itemUSD"], "asking", "eBay " + ls[0]["marketplace"] + " " + ls[0]["url"], "unverified"]
    elif proxy is not None: pt = [TODAY, proxy, "english-proxy", f"Cardmarket trend, {cmn} (id {cd['id']}), EUR {cd['trendEUR']} x {fx}", "English proxy; unverified"]
    else: pt = None
    if pt: e["history"] = [h for h in e["history"] if h[0] != TODAY] + [pt]
    e["latest"] = pt; e["englishProxy"] = {"usd": proxy, "product": cmn, "cardmarketId": (cd or {}).get("id"), "note": "price series only; not used as a buying benchmark"}; e["owned"] = rid in OWNED
    st = refs["items"].setdefault(rid, {"name": nm, "reference": None, "seen": {}})
    ref0 = dict(st["reference"]) if st["reference"] else None          # reference BEFORE today's listings
    mx = maxp.get(rid)
    sealed_ls = [x for x in ls if x["sealed"]]; ns_ls = [x for x in ls if not x["sealed"]]
    for x in ls:
        iid = x["url"].split("/")[-1]
        st["seen"].setdefault(iid, {"firstSeen": TODAY, "title": x["title"][:90], "sealed": x["sealed"], "itemUSD": x["itemUSD"], "url": x["url"]})
    for x in ns_ls:
        out["notSealed"].append({"id": rid, "name": nm, "reason": "opened/unspecified condition", "sealedBasis": x["sealedBasis"], "condition": x["condition"], "itemUSD": x["itemUSD"], "shippingUSD": x["shippingUSD"],
                                 "shippingUnknown": x["shipUnknown"], "title": x["title"], "seller": x["seller"], "feedbackPct": x["feedbackPct"], "itemLocation": x["originCountry"], "url": x["url"]})
    if rid not in OWNED:
        for x in sealed_ls:
            iid = x["url"].split("/")[-1]; first = st["seen"][iid]["firstSeen"] == TODAY
            unk = x["shipUnknown"]; allin = None if unk else x["allInUSD"]; lb = round(x["itemUSD"] + x["importEstUSD"], 2)
            reasons = []
            if ref0 is None and first: reasons.append("first sealed Portuguese listing seen for this booklet")
            if ref0 and (allin is not None and allin <= ref0["allInUSD"] * BELOW_REF): reasons.append(f">=15% below reference (${ref0['allInUSD']})")
            if mx is not None and ((allin is not None and allin <= mx) or (unk and lb <= mx)): reasons.append(f"at/below your max ${mx}" + (" (shipping unknown)" if unk else ""))
            if reasons:
                out["flags"].append({"id": rid, "name": nm, "reasons": reasons, "new": first, "allInUSD": allin, "allInStatus": "shipping unknown" if unk else "known", "itemOnlyLowerBoundUSD": lb,
                    "itemUSD": x["itemUSD"], "shippingUSD": x["shippingUSD"], "importEstUSD": x["importEstUSD"], "title": x["title"], "seller": x["seller"], "feedbackPct": x["feedbackPct"],
                    "feedbackScore": x["feedbackScore"], "itemLocation": x["originCountry"], "sealedBasis": x["sealedBasis"], "url": x["url"], "reference": ref0})
        known = [x for x in sealed_ls if not x["shipUnknown"]]
        if known:
            b = min(known, key=lambda x: x["allInUSD"])
            if not st["reference"] or b["allInUSD"] < st["reference"]["allInUSD"]:
                st["reference"] = {"allInUSD": b["allInUSD"], "itemUSD": b["itemUSD"], "date": TODAY, "url": b["url"], "title": b["title"]}
    out["counts"][rid] = {"name": nm, "owned": rid in OWNED, "foundToday": len(ls), "sealedToday": len(sealed_ls), "notSealedToday": len(ns_ls), "distinctEverSeen": len(st["seen"]),
                          "sealedEverSeen": sum(1 for v in st["seen"].values() if v["sealed"]), "reference": st["reference"], "max": mx}
    out["items"][rid] = {"listings": ls}
allc = out["counts"]
out["totals"] = {"foundToday": sum(c["foundToday"] for c in allc.values()), "sealedToday": sum(c["sealedToday"] for c in allc.values()), "distinctEverSeen": sum(c["distinctEverSeen"] for c in allc.values()),
                 "unownedRowsWithAnyListing": sum(1 for r, c in allc.items() if r not in OWNED and c["foundToday"])}
prices["generated"] = TODAY; refs["generated"] = TODAY
json.dump(prices, open(os.path.join(ROOT, "booklet_prices.json"), "w"), indent=1, ensure_ascii=False)
json.dump(refs, open(os.path.join(ROOT, "booklet_refs.json"), "w"), indent=1, ensure_ascii=False)
json.dump(out, open(os.path.join(ROOT, "booklet_hits.json"), "w"), indent=1, ensure_ascii=False)
if not os.path.exists(os.path.join(ROOT, "booklet_max.json")): json.dump({}, open(os.path.join(ROOT, "booklet_max.json"), "w"))
ew = ld("ebay_wants.json", {})
ew["booklets"] = {"generated": TODAY, "label": out["label"], "assumptions": out["assumptions"], "totals": out["totals"], "counts": out["counts"], "flags": out["flags"], "notSealed": out["notSealed"]}
json.dump(ew, open(os.path.join(ROOT, "ebay_wants.json"), "w"), indent=1, ensure_ascii=False)
print(out["totals"], "flags", len(out["flags"]), "notSealed", len(out["notSealed"]))
