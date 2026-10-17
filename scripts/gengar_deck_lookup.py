"""Read-only: find the Devir (Brazil 2007) 'Estampas Ilustradas - Origem das Lendas - Gengar Livro Ilustrado' on Cardmarket (public catalogue files) and eBay (Browse API active listings, several marketplaces).
Asking prices only; nothing is sold-verified. Never prints keys."""
import json, os, re, time, base64, urllib.request, urllib.parse, urllib.error
def get(u, h=None, data=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=h or {"User-Agent": "sealed-ledger"}, data=data), timeout=120) as r: return json.load(r)
    except urllib.error.HTTPError as e: return {"error": e.code}
    except Exception as e: return {"error": type(e).__name__}
out = {"cardmarket": {}, "ebay": {}}
B = "https://downloads.s3.cardmarket.com/productCatalog/"
KW = re.compile(r"devir|estampas|livro|origem das lendas|ilustrad|illustrated (book|booklet)", re.I)
for f in ("productList/products_nonsingles_6.json", "productList/products_singles_6.json"):
    d = get(B + f)
    ps = d.get("products", [])
    hits = [p for p in ps if re.search(r"gengar", p["name"], re.I) and KW.search(p["name"])]
    out["cardmarket"][f] = {"products": len(ps), "error": d.get("error"), "hits": [{"id": p["idProduct"], "name": p["name"]} for p in hits]}
guide = get(B + "priceGuide/price_guide_6.json").get("priceGuides", [])
gi = {g["idProduct"]: g for g in guide}
for f, v in out["cardmarket"].items():
    for h in v["hits"]:
        g = gi.get(h["id"]) or {}
        h["price"] = {k: g.get(k) for k in ("low", "trend", "avg", "avg7", "avg30")}
CID, CS = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
tok = get("https://api.ebay.com/identity/v1/oauth2/token", {"Authorization": "Basic " + base64.b64encode(f"{CID}:{CS}".encode()).decode(), "Content-Type": "application/x-www-form-urlencoded"},
          urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode())
if "access_token" in tok:
    for mk in ("EBAY_US", "EBAY_GB", "EBAY_DE", "EBAY_ES", "EBAY_IT", "EBAY_FR"):
        H = {"Authorization": "Bearer " + tok["access_token"], "X-EBAY-C-MARKETPLACE-ID": mk}
        for q in ("Devir Livro Ilustrado Gengar", "Estampas Ilustradas Gengar", "Pokemon Origem das Lendas Gengar Devir", "Pokemon Estampas Ilustradas Devir"):
            time.sleep(0.5)
            j = get("https://api.ebay.com/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode({"q": q, "limit": 50}), H)
            its = j.get("itemSummaries", []) if isinstance(j, dict) else []
            out["ebay"].setdefault(mk, {})[q] = {"total": j.get("total"), "error": j.get("error"), "items": [
                {"title": i.get("title"), "price": i.get("price"), "condition": i.get("condition"), "buyingOptions": i.get("buyingOptions"), "url": i.get("itemWebUrl"), "loc": (i.get("itemLocation") or {}).get("country")}
                for i in its if re.search(r"gengar", i.get("title", ""), re.I) and KW.search(i.get("title", ""))][:15], "gengarResults": sum(1 for i in its if re.search(r"gengar", i.get("title", ""), re.I))}
else:
    out["ebay"] = {"error": "token request failed"}
json.dump(out, open("gengar_deck_lookup.json", "w"), indent=1, ensure_ascii=False)
