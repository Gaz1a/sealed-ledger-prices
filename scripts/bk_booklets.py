#!/usr/bin/env python3
"""Daily Portuguese Devir illustrated-booklet prices + buy scan -> booklet_prices.json, booklet_hits.json.
Price point per booklet per day: lowest live Portuguese/Devir buy-it-now ASKING price if one exists, else the matching English EX booklet's Cardmarket TREND ("English proxy").
All prices unverified (asking/trend, not sold). Buy scan: worldwide eBay Browse API, buy-it-now only, sealed only, all-in = item + shipping (+ estimated import urllib.error, urllib.parse, cost for non-US origin).
Target = 0.85 x reference (median Portuguese ask if >=3 live listings, else English proxy trend). Never prints keys."""
import json, os, re, time, base64, datetime, urllib.request, urllib.parse, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = datetime.date.today().isoformat()
IMPORT_PCT = 0.12      # ESTIMATE added to (item+shipping) for items located outside the US (duty/brokerage/fees); not provided by eBay's API
SHIP_TO = {"X-EBAY-C-ENDUSERCTX": "contextualLocation=country=US,zip=91505"}
ROWS = {"bk-golem": "Golem", "bk-hooh": "Ho-Oh", "bk-lugia": "Lugia", "bk-machamp": "Machamp", "bk-omastar": "Omastar", "bk-ralts": "Ralts", "bk-treecko": "Treecko",
        "bk-exploud": "Exploud", "bk-mudkip": "Mudkip", "bk-rayquaza": "Rayquaza", "bk-torchic": "Torchic", "h-gengar-deck": "Gengar"}
OWNED = {"h-gengar-deck", "bk-machamp"}      # owned: never flagged / not a buy target
NOCAP_PREFIX = "bk-"      # Portuguese Devir booklets: NO price cap (Gaz tracks the market and buys when comfortable): every live sealed Portuguese listing of an unowned booklet is flagged, whatever the price; booklet_max.json is ignored for these rows
NOSCAN = {"bk-machamp"}      # bought 2026-10-17 (booklet_owned.json): no eBay scan at all
BELOW_REF = 0.85       # flag when all-in <= 85% of the lowest Portuguese sealed all-in seen so far (>=15% below)
MARKETS = ("EBAY_US", "EBAY_GB", "EBAY_DE", "EBAY_ES", "EBAY_IT", "EBAY_FR", "EBAY_CA", "EBAY_AU")
PT = re.compile(r"devir|livro|livraria|baralho|estampas ilustradas|origem das lendas|for[cç]as ocultas|meio[- ]baralho|portugu[eéê]s|portuguese|portoghese|portogallo|portugais|portugiesisch|portugal|brasil|brazil|\bpt[- ]?br\b", re.I)
PRODUCT = re.compile(r"half[- ]?(theme[- ])?deck|theme deck|\bdeck\b|booklet|livro|estampas|baralho", re.I)      # product-type word: required for the BROAD (non-Devir) queries so Portuguese single cards are not picked up
NAME_RX = {"Ho-Oh": r"ho[\s\-]*oh"}
UNMATCHED = {}      # self-check: Portuguese sealed-deck/booklet listings from the category sweep that match NO tracked booklet name -> booklet_unmatched.json, reviewed each run for new naming patterns      # sellers write Ho-Oh / HOOH / Ho Oh
CATS = ("183457", "183456")      # eBay: CCG Sealed Decks & Kits, CCG Sealed Packs (where these listings sit)
BAD = re.compile(r"\bcase\b|\blots?\b|loose|incomplete|missing|opened|aberto|usado|\bused\b|empty|cards only|proxy|custom|reprint|\bpsa\b|\bcgc\b|\bbgs\b|graded", re.I)
SEALED = re.compile(r"sealed|lacrado|selado|precintado|versiegelt|\bneuf\b|\bneuve\b|\bovp\b|sigillat[oa]|scell[ée]|cerrado|\bnew\b|\bnovo\b", re.I)
def ld(p, d):
    try: return json.load(open(os.path.join(ROOT, p)))
    except Exception: return d
DIAG = {"calls": 0, "errors": {}}
def get(u, h=None, data=None):
    DIAG["calls"] += 1
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=h or {"User-Agent": "sealed-ledger"}, data=data), timeout=60) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        k = "%s %s" % (e.code, urllib.parse.urlparse(u).netloc); DIAG["errors"][k] = DIAG["errors"].get(k, 0) + 1
        if e.code == 429 and "ebay" in u: DIAG["rateLimited"] = True; DIAG["note"] = "eBay 429 (daily call limit): scan stopped early; today has NO eBay listing data, not zero listings"
        return {}
    except Exception as e:
        k = type(e).__name__; DIAG["errors"][k] = DIAG["errors"].get(k, 0) + 1; return {}
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
cfg = ld("devir_retail_urls.json", {}); BK = cfg.get("booklets", {})
maxp = ld("booklet_max.json", {})
CMG, CMN = {}, {}      # Cardmarket price guide + product names, by the ledger's cardmarketId (English EX booklets used as the price proxy)
try:
    _req = lambda u: json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sealed-ledger"}), timeout=180))
    CMG = {g["idProduct"]: g for g in _req("https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json")["priceGuides"]}
    CMN = {p["idProduct"]: p["name"] for p in _req("https://downloads.s3.cardmarket.com/productCatalog/productList/products_nonsingles_6.json")["products"]}
except Exception as _e: print("cardmarket download failed", type(_e).__name__)
found = {k: {} for k in ROWS}
OTHER = {rid: re.compile(r"(?<![a-z])" + NAME_RX.get(nm, re.escape(nm)) + r"(?![a-z])", re.I) for rid, nm in ROWS.items()}
def ingest(rid, nm, i, mk, via):
    t = i.get("title", "")
    name_ok = bool(OTHER[rid].search(t))
    if via in ("title", "broad"):
        if not name_ok or not PT.search(t) or BAD.search(t) or (via == "broad" and not PRODUCT.search(t)): return
    else:      # matched by ISBN / GTIN / retailer ref: eBay's matching is fuzzy (returns novels), so still require a Pokemon/booklet signal AND a Portuguese signal
        if BAD.search(t) or not PT.search(t) or not (name_ok or re.search(r"pok[eé]mon", t, re.I)) or any(r2 != rid and p.search(t) for r2, p in OTHER.items()): return
    bo = i.get("buyingOptions") or []
    if "FIXED_PRICE" not in bo and "AUCTION" not in bo: return
    is_auc = "AUCTION" in bo
    item = usd(i.get("currentBidPrice") or i.get("price")) if is_auc else usd(i.get("price"))
    if item is None: return
    so = (i.get("shippingOptions") or [{}])[0].get("shippingCost")
    ship = usd(so) if so else None
    loc = (i.get("itemLocation") or {}).get("country")
    imp = round((item + (ship or 0)) * IMPORT_PCT, 2) if loc and loc != "US" else 0.0
    sealed = (i.get("condition") == "New") or bool(SEALED.search(t))
    found[rid][i["itemId"]] = {"title": t, "url": i.get("itemWebUrl", "").split("?")[0], "marketplace": mk, "itemUSD": item, "shippingUSD": ship, "shipUnknown": ship is None,
        "importEstUSD": imp, "allInUSD": round(item + (ship or 0) + imp, 2), "originCountry": loc, "condition": i.get("condition"), "itemEndDate": i.get("itemEndDate"), "sealed": sealed, "auction": is_auc, "bidCount": i.get("bidCount") or 0, "matchedBy": via + (" (ISBN unverified)" if via.startswith("isbn") and not b.get("isbnStatus", "").endswith("Gaz") else ""),
        "sealedBasis": "condition New" if i.get("condition") == "New" else "title says sealed/new" if SEALED.search(t) else "unconfirmed",
        "seller": (i.get("seller") or {}).get("username"), "feedbackPct": (i.get("seller") or {}).get("feedbackPercentage"), "feedbackScore": (i.get("seller") or {}).get("feedbackScore")}
if tok:
    for mk in MARKETS:
        H = {"Authorization": "Bearer " + tok, "X-EBAY-C-MARKETPLACE-ID": mk, **SHIP_TO}
        for rid, nm in ROWS.items():
            if rid in NOSCAN or DIAG.get("rateLimited"): continue
            b = BK.get(rid, {}); isbn = b.get("isbn13"); rfc = b.get("retailerRef") or ""
            plan = [(q, {}, "title") for q in (f"Devir Livro Ilustrado {nm}", f"Estampas Ilustradas {nm}", f"Pokemon Devir {nm} Portuguese booklet", f"Pokemon Origem das Lendas {nm} Devir", f"Devir Pokemon {nm}")]
            plan += [(f"Pokemon Portuguese {nm}", {}, "broad"), (f"{nm} Half Theme Deck Portuguese", {}, "broad")]      # sellers often title these "Half Theme Deck" / "Unseen Forces" with no Devir/Livro/booklet word; eBay search needs every query word in the title
            if isbn: plan += [(isbn, {}, "isbn"), (None, {"gtin": isbn}, "isbn-gtin")]
            if rfc.startswith("PK"): plan.append((rfc, {}, "retailer-ref"))
            for q, extra, via in plan:
                if DIAG.get("rateLimited"): break
                time.sleep(0.35)
                prm = {"limit": 50, "filter": "buyingOptions:{FIXED_PRICE|AUCTION},deliveryCountry:US", **extra}
                if q: prm["q"] = q
                j = get("https://api.ebay.com/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode(prm), H)
                for i in j.get("itemSummaries", []): ingest(rid, nm, i, mk, via)
        for cq in ("Portuguese", "Portuguese sealed", "Portuguese Half Deck", "Pokemon Portuguese deck", "Portuguese Pokemon booklet"):      # category sweep: finds listings whatever the seller put in the title (names matched against every unowned booklet)
            for cid in CATS:
                for off in (0, 50, 100):
                    if DIAG.get("rateLimited"): break
                    time.sleep(0.35)
                    j = get("https://api.ebay.com/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode({"q": cq, "category_ids": cid, "limit": 50, "offset": off, "filter": "buyingOptions:{FIXED_PRICE|AUCTION},deliveryCountry:US"}), H)
                    its = j.get("itemSummaries", [])
                    for i in its:
                        ti = i.get("title", "")
                        if PT.search(ti) and PRODUCT.search(ti) and not BAD.search(ti) and not any(p_.search(ti) for p_ in OTHER.values()):
                            UNMATCHED[i["itemId"]] = {"title": ti, "url": i.get("itemWebUrl", "").split("?")[0], "marketplace": mk, "price": (i.get("price") or i.get("currentBidPrice") or {}).get("value")}
                        for rid2, nm2 in ROWS.items():
                            if rid2 not in NOSCAN and OTHER[rid2].search(i.get("title", "")): ingest(rid2, nm2, i, mk, "broad")
                    if len(its) < 50: break
def valid_title(t): return bool(PT.search(t or "")) and bool(re.search(r"pok[eé]mon|booklet|half deck|theme deck|legend maker|livro", t or "", re.I)) and not BAD.search(t or "")
prices = ld("booklet_prices.json", {"items": {}})
refs = ld("booklet_refs.json", {"items": {}})
for st_ in refs["items"].values():     # drop earlier fuzzy ISBN junk (novels etc.) from the seen-log and from references
    st_["seen"] = {k: v for k, v in st_["seen"].items() if valid_title(v.get("title"))}
    if st_.get("reference") and not valid_title(st_["reference"].get("title")): st_["reference"] = None   # booklet_max.json: {"bk-golem": 60, ...} all-in max you set; optional
stock = ld("stock_check.json", {})
out = {"searchKeys": {r: {"titleQueries": [f"Devir Livro Ilustrado {n}", f"Estampas Ilustradas {n}", f"Pokemon Origem das Lendas {n} Devir"], "isbn13": BK.get(r, {}).get("isbn13"), "isbnStatus": BK.get(r, {}).get("isbnStatus"), "cardmarketId": BK.get(r, {}).get("cardmarketId"),
       "retailerRef": BK.get(r, {}).get("retailerRef")} for r, n in ROWS.items()}, "retailerInStock": stock.get("inStock", []), "retailerCheck": {"generated": stock.get("generated"), "sites": stock.get("sites"), "devirBrasil": {k: v for k, v in (stock.get("devirBrasil") or {}).items() if v.get("productLinks")},
       "productsChecked": len(stock.get("products", [])), "note": "in-stock retail copies under EUR 30 are listed here first; sites marked DISALLOWED/JS-only are skipped, not worked around"},
       "generated": TODAY, "label": "unverified: asking prices, not sold; import cost is an ESTIMATE", "assumptions": {"importEstimatePct": IMPORT_PCT, "shipTo": "Burbank CA 91505",
       "rules": ["reference = lowest all-in Portuguese Devir SEALED asking price seen so far (known shipping only)", "bk-* rows have NO cap: every live sealed Portuguese listing of an unowned booklet is flagged (US-based first, then international), whatever the price; other rows: flag only when all-in (item + shipping + 12% import for non-US sellers) is within that booklet's cap (hard gate); other reasons annotate", "auctions: current bid + shipping + import vs cap; a 0-bid auction is flagged only if shipping alone is under the cap",
                 "no sealed Portuguese reference yet -> flag any sealed listing the first time its item id appears", "only sealed/new listings are flagged; others listed under notSealed", "shipping not shown -> all-in is 'shipping unknown' (item+import shown as lower bound)"]},
       "diagnostics": DIAG, "flags": [], "notSealed": [], "counts": {}, "items": {}}
for rid, nm in ROWS.items():
    cmid = BK.get(rid, {}).get("cardmarketId"); g_ = CMG.get(cmid) if cmid else None; cmn = CMN.get(cmid) if cmid else None
    cd = {"id": cmid, "trendEUR": (g_ or {}).get("trend"), "lowEUR": (g_ or {}).get("low"), "inPriceGuide": g_ is not None} if cmid else None
    proxy = round(cd["trendEUR"] * fx, 2) if cd and cd.get("trendEUR") else None
    _all = sorted(found[rid].values(), key=lambda x: x["itemUSD"])
    ls = [x for x in _all if not x.get("auction")]; auc_all = [x for x in _all if x.get("auction")]      # auctions are evaluated against the cap only; never used as reference or in the ask log
    e = prices["items"].setdefault(rid, {"name": nm, "history": []})
    if ls: pt = [TODAY, ls[0]["itemUSD"], "asking", "eBay " + ls[0]["marketplace"] + " " + ls[0]["url"], "unverified"]
    elif proxy is not None: pt = [TODAY, proxy, "english-proxy", f"Cardmarket trend, {cmn} (id {cd['id']}), EUR {cd['trendEUR']} x {fx}", "English proxy; unverified"]
    else: pt = None
    if pt: e["history"] = [h for h in e["history"] if h[0] != TODAY] + [pt]
    e["latest"] = pt; e["englishProxy"] = {"usd": proxy, "product": cmn, "cardmarketId": (cd or {}).get("id"), "note": "price series only; not used as a buying benchmark"}; e["owned"] = rid in OWNED
    st = refs["items"].setdefault(rid, {"name": nm, "reference": None, "seen": {}})
    ref0 = dict(st["reference"]) if st["reference"] else None          # reference BEFORE today's listings
    _cp = maxp.get(rid); mx = _cp.get("cap") if isinstance(_cp, dict) else _cp; capbasis = (_cp or {}).get("basis") if isinstance(_cp, dict) else None; caplabel = (_cp or {}).get("label") if isinstance(_cp, dict) else None
    NOCAP = rid.startswith(NOCAP_PREFIX)
    if NOCAP: mx, capbasis, caplabel = None, None, "no cap: market tracking, every live sealed listing flagged"
    cmt = round(proxy * 0.85, 2) if proxy else None     # 85% of the English Cardmarket trend, once a trend exists
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
            head = None
            if mx is not None and unk:
                head = round(mx / (1 + IMPORT_PCT if x["importEstUSD"] else 1) - x["itemUSD"], 2)     # shipping must stay at/under this for the cap to hold
                if head > 0: reasons.append(f"shipping unknown: item ${x['itemUSD']}; under your ${mx} cap only if shipping stays at/under ${head}")
            elif mx is not None and allin is not None and allin <= mx: reasons.append(f"at/below your max ${mx}")
            if cmt and allin is not None and allin <= cmt: reasons.append(f"at/below 85% of the English Cardmarket trend (${cmt})")
            if mx is not None and ((allin is not None and allin > mx) or (unk and head is not None and head <= 0)): reasons = []      # per-deck cap is a hard gate
            if NOCAP and not reasons: reasons = ["no cap: live sealed Portuguese listing"]
            if reasons:
                out["flags"].append({"id": rid, "name": nm, "kind": "buy-it-now", "noCap": NOCAP, "usBased": x["originCountry"] == "US", "bidCount": 0, "itemEndDate": x.get("itemEndDate"), "originCountry": x["originCountry"], "marketplace": x["marketplace"], "capUSD": mx, "capBasis": capbasis, "capLabel": caplabel, "reasons": reasons, "new": first, "allInUSD": allin, "allInStatus": "shipping unknown" if unk else "known", "itemOnlyLowerBoundUSD": lb, "maxShippingForCapUSD": head,
                    "itemUSD": x["itemUSD"], "shippingUSD": x["shippingUSD"], "importEstUSD": x["importEstUSD"], "title": x["title"], "seller": x["seller"], "feedbackPct": x["feedbackPct"],
                    "feedbackScore": x["feedbackScore"], "itemLocation": x["originCountry"], "sealedBasis": x["sealedBasis"], "url": x["url"], "reference": ref0,
                    "readyToBuy": (not unk), "readyNote": ("ships to US (eBay deliveryCountry:US filter) with known shipping" if not unk else "NOT ready: shipping cost unknown - confirm it ships to the US and the cost first"),
                    "sellerNote": ("seller has 0 feedback" if not x["feedbackScore"] else None)})
        for x in [a for a in auc_all if a["sealed"]]:
            if mx is None and not NOCAP: continue
            loc_nonus = bool(x["originCountry"]) and x["originCountry"] != "US"; ip = IMPORT_PCT if loc_nonus else 0.0
            bid, ship, nb = x["itemUSD"], x["shippingUSD"], x["bidCount"]
            maxbid = None if (ship is None or mx is None) else round(mx / (1 + ip) - ship, 2)
            if NOCAP:
                allin = None if ship is None else round((bid + ship) * (1 + ip), 2); ok = True
                why = f"no cap: live sealed Portuguese auction, current bid ${bid} ({nb} bids) + shipping {'unknown' if ship is None else '$'+str(ship)}" + (" + import est." if ip else "")
            elif nb == 0:
                ok = ship is not None and round(ship * (1 + ip), 2) < mx      # 0-bid auction: only when shipping alone leaves room under the cap
                allin = None; why = f"0 bids: flagged only because shipping alone (${round(ship*(1+ip),2) if ship is not None else '?'} incl. import) is under the ${mx} cap; max winning bid about ${maxbid} item"
            else:
                allin = None if ship is None else round((bid + ship) * (1 + ip), 2)
                ok = (bid * (1 + ip) < mx) if ship is None else allin <= mx
                why = f"current bid ${bid} ({nb} bids) + shipping {'unknown' if ship is None else '$'+str(ship)} + import, under the ${mx} cap" if ok else ""
            if ok:
                out["flags"].append({"id": rid, "name": nm, "kind": "auction", "noCap": NOCAP, "usBased": x["originCountry"] == "US", "originCountry": x["originCountry"], "marketplace": x["marketplace"], "capUSD": mx, "capBasis": capbasis, "capLabel": caplabel, "reasons": [why], "bidCount": nb, "currentBidUSD": bid, "maxWinningBidUSD": maxbid,
                    "allInAtCurrentBidUSD": allin, "allInStatus": "shipping unknown" if ship is None else "known", "shippingUSD": ship, "importEstUSD": round((bid + (ship or 0)) * ip, 2), "itemEndDate": x.get("itemEndDate"),
                    "title": x["title"], "seller": x["seller"], "feedbackPct": x["feedbackPct"], "feedbackScore": x["feedbackScore"], "itemLocation": x["originCountry"], "url": x["url"],
                    "readyToBuy": False, "readyNote": "auction: place a bid at or below maxWinningBidUSD; not a buy-now", "sellerNote": ("seller has 0 feedback" if not x["feedbackScore"] else None)})
        known = [x for x in sealed_ls if not x["shipUnknown"]]
        if known:
            b = min(known, key=lambda x: x["allInUSD"])
            if not st["reference"] or b["allInUSD"] < st["reference"]["allInUSD"]:
                st["reference"] = {"allInUSD": b["allInUSD"], "itemUSD": b["itemUSD"], "date": TODAY, "url": b["url"], "title": b["title"]}
    out["counts"][rid] = {"name": nm, "owned": rid in OWNED, "capUSD": mx, "capBasis": capbasis, "capLabel": caplabel, "auctionsToday": len(auc_all), "foundToday": len(ls), "sealedToday": len(sealed_ls), "notSealedToday": len(ns_ls), "distinctEverSeen": len(st["seen"]),
                          "sealedEverSeen": sum(1 for v in st["seen"].values() if v["sealed"]), "reference": st["reference"], "max": mx, "cardmarketTrendUSD": proxy, "cardmarketTarget85": cmt, "cardmarketId": cmid, "cardmarketProduct": cmn}
    out["items"][rid] = {"listings": ls, "auctions": auc_all}
# ---- market log: every listing seen, disappearances = "probably sold" (unverified implied sale; asks are NOT sold prices)
import statistics
log = ld("booklet_listings.json", {"listings": {}}); log["listings"] = {k: v for k, v in log["listings"].items() if valid_title(v.get("title"))}; LG = log["listings"]; live_ids = set()
for rid in ROWS:
    for x in found[rid].values():
        iid = x["url"].split("/")[-1]; live_ids.add(iid)
        e = LG.setdefault(iid, {"row": rid, "firstSeen": TODAY})
        e.update({"row": rid, "title": x["title"], "url": x["url"], "marketplace": x["marketplace"], "lastSeen": TODAY, "lastItemUSD": x["itemUSD"], "lastShippingUSD": x["shippingUSD"],
                  "shippingUnknown": x["shipUnknown"], "sealed": x["sealed"], "itemEndDate": x.get("itemEndDate"), "status": "live", "missed": 0})
        e.pop("impliedSale", None); e.pop("goneDate", None)
for iid, e in LG.items():
    if iid in live_ids or e.get("status") != "live": continue
    e["missed"] = e.get("missed", 0) + 1
    if e["missed"] >= 2:    # absent from two consecutive daily scans (guards against one-off search misses)
        ended = e.get("itemEndDate") and e["itemEndDate"][:10] <= TODAY
        e["status"] = "ended (end date reached)" if ended else "probably sold"; e["goneDate"] = TODAY
        if not ended: e["impliedSale"] = {"price": e["lastItemUSD"], "shipping": e["lastShippingUSD"], "label": "unverified: last ask before the listing vanished before its end date; not a confirmed sale"}
def stats(v): return {"low": min(v), "median": round(statistics.median(v), 2), "high": max(v)} if v else {"low": None, "median": None, "high": None}
out["market"] = {"label": "unverified: ASKING prices of Portuguese Devir booklet listings; implied sales are last asks of vanished listings, not sold prices",
                 "disappearanceRule": "buy-it-now listing absent from 2 consecutive daily scans before its end date = 'probably sold'", "perBooklet": {}}
for rid, nm in ROWS.items():
    liv = [e for e in LG.values() if e["row"] == rid and e["status"] == "live"]; imp = [e for e in LG.values() if e["row"] == rid and e["status"] == "probably sold"]
    out["market"]["perBooklet"][rid] = {"name": nm, "liveListings": len(liv), "liveSealed": sum(1 for e in liv if e["sealed"]), "askItemUSD": stats([e["lastItemUSD"] for e in liv]),
        "cardmarketId": BK.get(rid, {}).get("cardmarketId"), "cardmarketProduct": CMN.get(BK.get(rid, {}).get("cardmarketId")), "cardmarketTrendUSD": out["counts"][rid]["cardmarketTrendUSD"], "target85OfTrend": out["counts"][rid]["cardmarketTarget85"],
        "targetNote": None if out["counts"][rid]["cardmarketTrendUSD"] else "no Cardmarket trend yet; target set automatically at 85% once one is published", "impliedSales": len(imp), "impliedSaleMedianUSD": stats([e["impliedSale"]["price"] for e in imp])["median"], "everSeen": sum(1 for e in LG.values() if e["row"] == rid)}
log["generated"] = TODAY; log["note"] = "one record per eBay item id: first/last seen, last ask, shipping, sealed y/n, status; asks only"
json.dump(log, open(os.path.join(ROOT, "booklet_listings.json"), "w"), indent=1, ensure_ascii=False)
order_ = {r: i for i, r in enumerate(ROWS)}
out["flags"].sort(key=lambda f: (order_.get(f["id"], 99), not f.get("usBased"), f.get("allInUSD") or f.get("allInAtCurrentBidUSD") or f.get("itemUSD") or f.get("currentBidUSD") or 9e9))
for r_, c_ in out["counts"].items():      # per booklet: is there a live US-based sealed listing? (the ledger job uses an international one only when there is none)
    fl_ = [f for f in out["flags"] if f["id"] == r_]
    c_["liveSealedUS"] = sum(1 for f in fl_ if f.get("usBased")); c_["liveSealedInternational"] = sum(1 for f in fl_ if not f.get("usBased")); c_["noCap"] = r_.startswith(NOCAP_PREFIX)
allc = out["counts"]
out["totals"] = {"foundToday": sum(c["foundToday"] for c in allc.values()), "sealedToday": sum(c["sealedToday"] for c in allc.values()), "distinctEverSeen": sum(c["distinctEverSeen"] for c in allc.values()),
                 "unownedRowsWithAnyListing": sum(1 for r, c in allc.items() if r not in OWNED and c["foundToday"])}
prices["generated"] = TODAY; refs["generated"] = TODAY
json.dump(prices, open(os.path.join(ROOT, "booklet_prices.json"), "w"), indent=1, ensure_ascii=False)
json.dump(refs, open(os.path.join(ROOT, "booklet_refs.json"), "w"), indent=1, ensure_ascii=False)
# canary: items Gaz is watching must always be flagged (booklet_watch.json: {"ids": ["800795730845", ...]}); a miss is recorded loudly
watch = ld("booklet_watch.json", {"ids": []}).get("ids", [])
flagged_ids = {f["url"].split("/")[-1] for f in out["flags"]}
out["diagnostics"]["watchCheck"] = {w: ("flagged" if w in flagged_ids else "NOT FLAGGED" if not DIAG.get("rateLimited") else "unchecked (rate limited)") for w in watch}
if any(v == "NOT FLAGGED" for v in out["diagnostics"]["watchCheck"].values()): print("WATCHED LISTING NOT FLAGGED", out["diagnostics"]["watchCheck"])
json.dump(UNMATCHED, open(os.path.join(ROOT, "booklet_unmatched.json"), "w"), indent=1, ensure_ascii=False)
json.dump(out, open(os.path.join(ROOT, "booklet_hits.json"), "w"), indent=1, ensure_ascii=False)
if not os.path.exists(os.path.join(ROOT, "booklet_max.json")): json.dump({}, open(os.path.join(ROOT, "booklet_max.json"), "w"))
ew = ld("ebay_wants.json", {})
ew["booklets"] = {"retailerInStock": out["retailerInStock"], "retailerCheck": out["retailerCheck"], "generated": TODAY, "label": out["label"], "assumptions": out["assumptions"], "totals": out["totals"], "counts": out["counts"], "flags": out["flags"], "notSealed": out["notSealed"]}
json.dump(ew, open(os.path.join(ROOT, "ebay_wants.json"), "w"), indent=1, ensure_ascii=False)
print(out["totals"], "flags", len(out["flags"]), "notSealed", len(out["notSealed"]))
