#!/usr/bin/env python3
"""Weekly scan of eBay's Browse API for active Base Set / Jungle / Fossil
common-uncommon and holo lot listings, for Gaz's Kanto 151 vintage project.
Pure mechanical collection: price/keyword/seller filtering only. No authenticity
or "is this a good buy" judgment — that happens in the Claude task that reads
this file, which can actually look at the listing photos.

Auth: eBay's client_credentials app token (no user login needed; Browse API
search/getItem are public-data endpoints under this grant). Requires repo
secrets EBAY_CLIENT_ID / EBAY_CLIENT_SECRET (Production keys, not Sandbox).
Stdlib only."""
import json, os, re, sys, time, base64, datetime, urllib.request, urllib.parse

ROOT = "."
TODAY = datetime.date.today()
UA = "sealed-ledger-ebay-scout/1.0"
CLIENT_ID = os.environ.get("EBAY_CLIENT_ID")
CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET")

QUERIES = [
    "pokemon base set lot common uncommon",
    "pokemon jungle set lot common uncommon",
    "pokemon fossil set lot common uncommon",
    "pokemon base set holo lot",
    "pokemon wotc common uncommon lot",
]
MIN_PRICE, MAX_PRICE = 30.0, 90.0
MIN_FEEDBACK_SCORE = 50
MIN_FEEDBACK_PCT = 97.0
MAX_DETAIL_CALLS_PER_QUERY = 8   # only fetch full photos/returns for the best few per query

BAD_WORDS = re.compile(
    r"\bpsa\b|\bcgc\b|\bbgs\b|\bgraded\b|\breprint\b|\bcustom\b|\bproxy\b|\bfake\b|"
    r"\bdigital\b|\bonline\b|\bcode card\b|\bsingle card\b|\b1st edition\b|\bfirst edition\b",
    re.I)

def get(url, headers=None, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception as e:
            if i == tries - 1:
                print("FAIL", url, e, file=sys.stderr)
                return None
            time.sleep(2 * (i + 1))

def get_token():
    if not CLIENT_ID or not CLIENT_SECRET:
        sys.exit("EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set")
    auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }).encode()
    req = urllib.request.Request(
        "https://api.ebay.com/identity/v1/oauth2/token", data=body,
        headers={"Authorization": f"Basic {auth}",
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)["access_token"]

def search(query, token):
    q = urllib.parse.quote(query)
    filt = urllib.parse.quote(f"price:[{MIN_PRICE}..{MAX_PRICE}],priceCurrency:USD,buyingOptions:{{FIXED_PRICE}}")
    url = (f"https://api.ebay.com/buy/browse/v1/item_summary/search"
           f"?q={q}&filter={filt}&limit=30&sort=price")
    d = get(url, headers={"Authorization": f"Bearer {token}",
                           "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"})
    return (d or {}).get("itemSummaries", [])

def get_item_detail(item_id, token):
    iid = urllib.parse.quote(item_id, safe="")
    url = f"https://api.ebay.com/buy/browse/v1/item/{iid}"
    return get(url, headers={"Authorization": f"Bearer {token}",
                              "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"})

def main():
    token = get_token()
    seen_ids = set()
    candidates = []

    for q in QUERIES:
        hits = search(q, token)
        if not hits:
            continue
        filtered = []
        for h in hits:
            title = h.get("title", "")
            if BAD_WORDS.search(title):
                continue
            if "lot" not in title.lower():
                continue
            seller = h.get("seller", {}) or {}
            score = seller.get("feedbackScore", 0) or 0
            pct = float(seller.get("feedbackPercentage", 0) or 0)
            if score < MIN_FEEDBACK_SCORE or pct < MIN_FEEDBACK_PCT:
                continue
            iid = h.get("itemId")
            if not iid or iid in seen_ids:
                continue
            price = float((h.get("price") or {}).get("value", 0) or 0)
            ship = h.get("shippingOptions", [{}])
            ship_cost = 0.0
            if ship:
                sc = (ship[0].get("shippingCost") or {}).get("value")
                ship_cost = float(sc) if sc else 0.0
            filtered.append({
                "itemId": iid, "title": title, "price": price, "shipping": ship_cost,
                "total": round(price + ship_cost, 2), "condition": h.get("condition"),
                "seller": seller.get("username"), "feedbackScore": score, "feedbackPct": pct,
                "url": h.get("itemWebUrl"), "image": (h.get("image") or {}).get("imageUrl"),
                "query": q,
            })
        filtered.sort(key=lambda x: x["total"])
        top = filtered[:MAX_DETAIL_CALLS_PER_QUERY]
        for c in top:
            seen_ids.add(c["itemId"])
            detail = get_item_detail(c["itemId"], token)
            time.sleep(0.3)
            if detail:
                imgs = [detail.get("image", {}).get("imageUrl")] if detail.get("image") else []
                imgs += [i.get("imageUrl") for i in (detail.get("additionalImages") or [])]
                c["images"] = [i for i in imgs if i][:6]
                terms = detail.get("returnTerms") or {}
                c["returnsAccepted"] = terms.get("returnsAccepted", False)
                c["description"] = (detail.get("shortDescription") or "")[:500]
            else:
                c["images"] = [c["image"]] if c.get("image") else []
                c["returnsAccepted"] = None
                c["description"] = ""
            candidates.append(c)

    candidates.sort(key=lambda x: x["total"])
    out = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "queries": QUERIES, "candidates": candidates}
    json.dump(out, open(f"{ROOT}/ebay_kanto.json", "w"), indent=1, ensure_ascii=False)
    print(f"scanned {len(QUERIES)} queries, {len(candidates)} candidates written")

if __name__ == "__main__":
    main()
