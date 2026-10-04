#!/usr/bin/env python3
"""Weekly eBay Browse API scan for Gyarados / Magikarp LOTS. Mechanical filtering only;
Claude judges contents and value. Writes ebay_gyarados.json."""
import json, os, re, sys, time, base64, datetime, html, urllib.request, urllib.parse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CID, CSEC = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
UA = "sealed-ledger-gyarados-scout/1.0"
MIN_P, MAX_P = 5.0, 250.0
MIN_FB, MIN_PCT = 50, 97.0
MAX_DETAIL = 30
QUERIES = ["gyarados lot pokemon cards", "magikarp lot pokemon cards", "gyarados magikarp lot",
           "gyarados holo lot", "magikarp vintage lot", "gyarados bundle pokemon", "magikarp bundle pokemon"]
NAME = re.compile(r"gyarados|magikarp", re.I)
LOT = re.compile(r"\blots?\b|\bbundle\b|\bcollection\b|\bx\s?\d+\b|\b\d+\s?(cards?|pcs|pieces)\b|\bset\b|\bcomplete\b|\bplaymat\b", re.I)
BAD = re.compile(r"\bpsa\b|\bcgc\b|\bbgs\b|\bgraded\b|\bslab\b|\breprint\b|\bcustom\b|\bproxy\b|\bfake\b|\bplush\b|"
                 r"\bfigure\b|\bfunko\b|\bsticker\b|\bjumbo\b|\boversized?\b|\bjapanese\b|\bkorean\b|\bchinese\b|"
                 r"\bdigital\b|\bcode card\b|\bdamaged\b|\bplayed\b|\bheavily\b|\bpoor\b|\bmp\b|\bhp\b", re.I)

def get(url, headers=None, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=25) as r: return json.load(r)
        except Exception as e:
            if i == tries - 1: print("FAIL", url[:90], e, file=sys.stderr); return None
            time.sleep(2 * (i + 1))

def token():
    if not CID or not CSEC: sys.exit("EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set")
    auth = base64.b64encode(f"{CID}:{CSEC}".encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode()
    req = urllib.request.Request("https://api.ebay.com/identity/v1/oauth2/token", data=body,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=25) as r: return json.load(r)["access_token"]

def main():
    tok = token(); H = {"Authorization": f"Bearer {tok}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    seen, cands = set(), []
    for q in QUERIES:
        filt = urllib.parse.quote(f"price:[{MIN_P}..{MAX_P}],priceCurrency:USD,buyingOptions:{{FIXED_PRICE|AUCTION}},conditions:{{USED|NEW}}")
        url = f"https://api.ebay.com/buy/browse/v1/item_summary/search?q={urllib.parse.quote(q)}&filter={filt}&limit=50&sort=newlyListed"
        for h in (get(url, H) or {}).get("itemSummaries", []):
            iid = h.get("itemId"); t = h.get("title", "")
            if iid in seen or not NAME.search(t) or not LOT.search(t) or BAD.search(t): continue
            sel = h.get("seller", {})
            if (sel.get("feedbackScore") or 0) < MIN_FB or float(sel.get("feedbackPercentage") or 0) < MIN_PCT: continue
            seen.add(iid); cands.append(h)
    cands.sort(key=lambda h: float(h["price"]["value"]))
    out = []
    for h in cands[:MAX_DETAIL]:
        d = get(f"https://api.ebay.com/buy/browse/v1/item/{urllib.parse.quote(h['itemId'], safe='')}", H) or {}
        ship = None
        for s in (h.get("shippingOptions") or []):
            if s.get("shippingCost"): ship = float(s["shippingCost"]["value"]); break
        desc = html.unescape(re.sub(r"<[^>]+>", " ", d.get("description") or d.get("shortDescription") or ""))
        photos = [h.get("image", {}).get("imageUrl")] + [i.get("imageUrl") for i in (d.get("additionalImages") or h.get("additionalImages") or [])]
        out.append({"itemId": h["itemId"], "title": h["title"], "url": h.get("itemWebUrl"),
            "price": float(h["price"]["value"]), "shipping": ship,
            "buyingOptions": h.get("buyingOptions"), "itemEndDate": h.get("itemEndDate"),
            "seller": h.get("seller", {}).get("username"), "feedbackScore": h.get("seller", {}).get("feedbackScore"),
            "feedbackPct": h.get("seller", {}).get("feedbackPercentage"),
            "returnsAccepted": (d.get("returnTerms") or {}).get("returnsAccepted"),
            "condition": h.get("condition"), "photos": [p for p in photos if p][:6], "desc": re.sub(r"\s+", " ", desc)[:700]})
        time.sleep(0.4)
    json.dump({"generated": datetime.date.today().isoformat(), "candidates": out}, open(os.path.join(ROOT, "ebay_gyarados.json"), "w"), indent=1)
    print(len(out), "candidates")
main()
