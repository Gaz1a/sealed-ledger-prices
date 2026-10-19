#!/usr/bin/env python3
"""One-off diagnostic: why was a live sealed Portuguese booklet listing not flagged? Writes bk_diag.json (no secrets)."""
import json, os, re, base64, time, urllib.request, urllib.parse, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, "scripts/bk_booklets.py")).read()
ns = {"re": re}
for name in ("PT", "BAD", "SEALED"):
    exec(re.search(r"^%s = .*$" % name, src, re.M).group(0), ns)
PT, BAD, SEALED = ns["PT"], ns["BAD"], ns["SEALED"]
ROWS = dict(re.findall(r'"(bk-[a-z]+)": "([^"]+)"', src))
ITEMS = ["800795730845", "287654059500"]
CID, CS = os.environ["EBAY_CLIENT_ID"], os.environ["EBAY_CLIENT_SECRET"]
def call(u, h=None, data=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=h or {}, data=data), timeout=60) as r: return json.load(r)
    except urllib.error.HTTPError as e: return {"_http": e.code, "_body": e.read()[:300].decode("utf8", "replace")}
    except Exception as e: return {"_err": str(e)[:100]}
tok = call("https://api.ebay.com/identity/v1/oauth2/token", {"Authorization": "Basic " + base64.b64encode(f"{CID}:{CS}".encode()).decode(), "Content-Type": "application/x-www-form-urlencoded"},
           urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode())["access_token"]
H = {"Authorization": "Bearer " + tok, "X-EBAY-C-MARKETPLACE-ID": "EBAY_US", "X-EBAY-C-ENDUSERCTX": "contextualLocation=country=US,zip=91505"}
out = {"items": {}, "queries": []}
for n in ITEMS:
    j = call(f"https://api.ebay.com/buy/browse/v1/item/v1%7C{n}%7C0", H)
    keep = {k: j.get(k) for k in ("title", "condition", "conditionId", "categoryPath", "categoryId", "buyingOptions", "price", "currentBidPrice", "bidCount", "itemEndDate", "itemLocation", "seller", "estimatedAvailabilities", "shippingOptions", "itemWebUrl", "primaryItemGroup", "itemGroupType", "_http", "_body", "_err")}
    keep["localizedAspects"] = [a for a in (j.get("localizedAspects") or [])][:25]
    out["items"][n] = keep
    t = j.get("title") or ""
    nm = next((v for v in ROWS.values() if re.search(r"(?<![a-z])" + re.escape(v) + r"(?![a-z])", t, re.I)), None)
    out["items"][n]["filterCheck"] = {"bookletNameFound": nm, "PT": bool(PT.search(t)), "BAD": (BAD.search(t).group(0) if BAD.search(t) else None), "SEALED": bool(SEALED.search(t)), "conditionIsNew": j.get("condition") == "New"}
def run(q, nm, extra=None, label="existing"):
    prm = {"q": q, "limit": 50, "filter": "buyingOptions:{FIXED_PRICE|AUCTION},deliveryCountry:US", **(extra or {})}
    j = call("https://api.ebay.com/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode(prm), H); time.sleep(0.4)
    sm = j.get("itemSummaries", []); ids = [i["itemId"].split("|")[1] for i in sm]
    out["queries"].append({"query": q, "label": label, "total": j.get("total"), "returned": len(sm), "http": j.get("_http"),
        "found": {n: (ids.index(n) + 1 if n in ids else None) for n in ITEMS}, "firstTitles": [i["title"][:70] for i in sm[:3]]})
for rid, nm in (("bk-hooh", "Ho-Oh"),):
    for q in (f"Devir Livro Ilustrado {nm}", f"Estampas Ilustradas {nm}", f"Pokemon Devir {nm} Portuguese booklet", f"Pokemon Origem das Lendas {nm} Devir", f"Devir Pokemon {nm}", "9788575322352", "PKLIVFO07"):
        run(q, nm, label="existing-plan")
    for q in (f"Pokemon Portuguese {nm}", f"{nm} Half Theme Deck Portuguese", f"Pokemon EX Unseen Forces {nm} half deck", f"{nm} Portuguese sealed", f"Pokemon {nm} half deck", "Pokemon Portuguese Half Theme Deck", "Pokemon Portuguese theme deck sealed", "Pokemon Portuguese deck sealed", "Pokemon Portugues deck", "Pokemon Ex Forcas Ocultas Ho-Oh"):
        run(q, nm, label="candidate")
cat = (out["items"]["800795730845"].get("categoryId") or "")
if cat:
    for q in ("Portuguese", "Portuguese sealed", "Portuguese Half Deck", "Ho-Oh"): run(q, "Ho-Oh", {"category_ids": cat}, label="category " + cat)
json.dump(out, open(os.path.join(ROOT, "bk_diag.json"), "w"), indent=1, ensure_ascii=False)
for q in out["queries"]: print(q["label"], "|", q["query"], "| total", q["total"], "| found", q["found"])
