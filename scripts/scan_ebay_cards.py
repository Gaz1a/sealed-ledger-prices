#!/usr/bin/env python3
"""Weekly eBay Browse API scan for the Football and Wrestling ledgers.
Mechanical only: for each query in cards/ebay_queries.json it records the
cheapest active listings (asks, NOT sold prices; the Browse API has no sold data)
and, where a legacyItemId is given, whether that exact listing is still live and
at what price. Judgment happens in the Claude weekly task. Needs the same
EBAY_CLIENT_ID / EBAY_CLIENT_SECRET repo secrets as the other eBay scans. Stdlib only."""
import json, os, re, sys, time, base64, datetime, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CID, SEC = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
HDR = {"X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
BAD = re.compile(r"\breprint\b|\bcustom\b|\bproxy\b|\bfake\b|\bdigital\b|\bcode card\b|\bcase of\b|\bbulk\b|\bjob lot\b", re.I)

def get(url, headers=None, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "card-ledger-ebay/1.0", **(headers or {})})
            with urllib.request.urlopen(req, timeout=25) as r: return json.load(r)
        except Exception as e:
            if i == tries - 1: print("FAIL", url, e, file=sys.stderr); return None
            time.sleep(2 * (i + 1))

def token():
    if not CID or not SEC: sys.exit("EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set")
    auth = base64.b64encode(f"{CID}:{SEC}".encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode()
    req = urllib.request.Request("https://api.ebay.com/identity/v1/oauth2/token", data=body,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=25) as r: return json.load(r)["access_token"]

def money(o): return float((o or {}).get("value", 0) or 0)

def main():
    tok = token(); H = {"Authorization": f"Bearer {tok}", **HDR}
    queries = json.load(open(os.path.join(ROOT, "cards", "ebay_queries.json")))
    out, links = [], []
    for q in queries:
        d = get("https://api.ebay.com/buy/browse/v1/item_summary/search?q=" + urllib.parse.quote(q["q"]) +
                "&filter=" + urllib.parse.quote("priceCurrency:USD,buyingOptions:{FIXED_PRICE|AUCTION}") + "&limit=30&sort=price", H)
        asks = []
        for h in (d or {}).get("itemSummaries", []):
            if BAD.search(h.get("title", "")): continue
            ship = ((h.get("shippingOptions") or [{}])[0].get("shippingCost") or {}).get("value")
            price = money(h.get("price")); tot = round(price + (float(ship) if ship else 0), 2)
            asks.append({"title": h.get("title"), "total": tot, "price": price, "bids": h.get("bidCount"),
                         "buying": h.get("buyingOptions"), "seller": (h.get("seller") or {}).get("username"),
                         "feedbackPct": (h.get("seller") or {}).get("feedbackPercentage"), "url": h.get("itemWebUrl")})
        asks.sort(key=lambda a: a["total"])
        da = get("https://api.ebay.com/buy/browse/v1/item_summary/search?q=" + urllib.parse.quote(q["q"]) +
                 "&filter=" + urllib.parse.quote("priceCurrency:USD,buyingOptions:{AUCTION}") + "&limit=15&sort=endingSoonest", H)
        auctions = []
        now = datetime.datetime.now(datetime.timezone.utc)
        for h in (da or {}).get("itemSummaries", []):
            if BAD.search(h.get("title", "")) or not h.get("itemEndDate"): continue
            try: end = datetime.datetime.strptime(h["itemEndDate"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=datetime.timezone.utc)
            except ValueError: continue
            left = (end - now).total_seconds() / 86400
            if left < 0 or left > 9: continue
            ship = ((h.get("shippingOptions") or [{}])[0].get("shippingCost") or {}).get("value")
            bid = money(h.get("currentBidPrice") or h.get("price"))
            auctions.append({"title": h.get("title"), "total": round(bid + (float(ship) if ship else 0), 2), "bids": h.get("bidCount"),
                             "daysLeft": round(left, 2), "endDate": h["itemEndDate"], "seller": (h.get("seller") or {}).get("username"),
                             "feedbackPct": (h.get("seller") or {}).get("feedbackPercentage"), "url": h.get("itemWebUrl")})
        out.append({"ledger": q["ledger"], "id": q["id"], "q": q["q"], "total": (d or {}).get("total", 0), "asks": asks[:6], "auctions": auctions[:5]})
        if q.get("legacyItemId"):
            it = get("https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id?legacy_item_id=" + q["legacyItemId"], H)
            links.append({"ledger": q["ledger"], "id": q["id"], "legacyItemId": q["legacyItemId"], "live": bool(it and it.get("itemId")),
                          "price": money((it or {}).get("price")), "title": (it or {}).get("title"),
                          "url": (it or {}).get("itemWebUrl"), "returnsAccepted": ((it or {}).get("returnTerms") or {}).get("returnsAccepted")})
        time.sleep(0.3)
    json.dump({"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "note": "active asks and auctions ending within 9 days; not sold prices", "queries": out, "links": links},
              open(os.path.join(ROOT, "cards", "ebay_cards.json"), "w"), indent=1, ensure_ascii=False)
    print(f"{len(out)} queries, {len(links)} link checks")

main()
