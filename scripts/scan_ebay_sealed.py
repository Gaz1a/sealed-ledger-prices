#!/usr/bin/env python3
"""Weekly scan of eBay's Browse API for active AUCTION listings on sealed
product Gaz already tracks or that the market radar flagged as interesting.
Pure mechanical collection: price/keyword/seller/end-date filtering only.
No "is this a good buy" judgment — that happens in the Claude task that
reads this file, using each candidate's ceiling from the ledger's rules.

Auth: eBay's client_credentials app token (no user login needed; Browse API
search/getItem are public-data endpoints under this grant). Requires repo
secrets EBAY_CLIENT_ID / EBAY_CLIENT_SECRET (Production keys, not Sandbox) —
the same ones scan_ebay_kanto.py already uses. Stdlib only."""
import json, os, re, sys, time, base64, datetime, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = datetime.date.today()
UA = "sealed-ledger-ebay-sealed-scout/1.0"
CLIENT_ID = os.environ.get("EBAY_CLIENT_ID")
CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET")

MIN_PRICE, MAX_PRICE = 15.0, 2000.0
MAX_DAYS_TO_END = 9          # only auctions ending before next week's scan
MIN_FEEDBACK_SCORE = 20
MIN_FEEDBACK_PCT = 96.0
MAX_DETAIL_CALLS_PER_QUERY = 6
MAX_QUERIES = 40             # keep the run and the rate-limit budget bounded

BAD_WORDS = re.compile(
    r"\bpsa\b|\bcgc\b|\bbgs\b|\bgraded\b|\breprint\b|\bcustom\b|\bproxy\b|\bfake\b|"
    r"\bdigital\b|\bonline\b|\bcode card\b|\bsingle card\b|\bempty\b|\bbox only\b|"
    r"\bwrapper\b|\bsleeve\b|\bproxy\b|\blot of 1\b",
    re.I)

# Same sealed-product vocabulary scan_market.py uses to decide a TCGplayer
# product is sealed, reused here to decide a tracked *title* is sealed
# (tracked.json has no extendedData to check, only a title string).
SEALED_WORDS = re.compile(
    r"booster box|booster bundle|booster pack\b|elite trainer|"
    r"trainer box|premium collection|special collection|ultra[- ]premium|"
    r"super[- ]premium|collection box|mini tin|tin\b|blister|"
    r"theme deck|starter deck|starter set|battle deck|deck kit|"
    r"trainer'?s? (kit|toolkit|box)|build ?& ?battle|prerelease kit|"
    r"pin collection|figure collection|binder collection|poster collection|"
    r"illustration collection|sticker collection|surprise box|gift set|value box|fun ?pack|"
    r"3[- ]pack|6[- ]pack|check ?lane|display box|booster display",
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


def load(name, default):
    p = os.path.join(ROOT, name)
    return json.load(open(p)) if os.path.exists(p) else default


def build_queries():
    """One query per tracked sealed item + top radar candidates, deduped."""
    seen_titles, queries = set(), []

    tracked = load("tracked.json", {})
    # Many ledger titles are generic ("Elite Trainer Box", "Booster Box (36
    # packs)") shared across several sets — item_sets.json gives the set
    # name to prefix so the eBay search is actually specific. Update this
    # file when a new sealed item is added to tracked.json; entries missing
    # from it just search on the bare title.
    item_sets = load("item_sets.json", {})
    for lid, t in tracked.items():
        title = (t.get("title") or "").strip()
        if not title or not SEALED_WORDS.search(title):
            continue
        set_name = item_sets.get(lid, "")
        q = f"{set_name} {title}".strip() if set_name else title
        key = q.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        queries.append({"q": q, "source": "tracked", "ledgerId": lid})

    radar = load("radar.json", {}).get("candidates", [])
    for c in radar:
        if c.get("score", 0) < 2:
            continue
        title = (c.get("name") or "").strip()
        key = title.lower()
        if not title or key in seen_titles:
            continue
        seen_titles.add(key)
        queries.append({"q": title, "source": "radar", "pid": c.get("pid")})

    return queries[:MAX_QUERIES]


def search_auctions(query, token):
    q = urllib.parse.quote(query)
    filt = urllib.parse.quote(
        f"price:[{MIN_PRICE}..{MAX_PRICE}],priceCurrency:USD,buyingOptions:{{AUCTION}}")
    url = (f"https://api.ebay.com/buy/browse/v1/item_summary/search"
           f"?q={q}&filter={filt}&limit=20&sort=endingSoonest")
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
    queries = build_queries()
    seen_ids = set()
    candidates = []
    now = datetime.datetime.now(datetime.timezone.utc)

    for query in queries:
        hits = search_auctions(query["q"], token)
        if not hits:
            continue
        filtered = []
        for h in hits:
            title = h.get("title", "")
            if BAD_WORDS.search(title):
                continue
            end_raw = h.get("itemEndDate")
            if not end_raw:
                continue
            try:
                end_dt = datetime.datetime.strptime(end_raw, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                    tzinfo=datetime.timezone.utc)
            except ValueError:
                continue
            days_left = (end_dt - now).total_seconds() / 86400
            if days_left < 0 or days_left > MAX_DAYS_TO_END:
                continue
            seller = h.get("seller", {}) or {}
            score = seller.get("feedbackScore", 0) or 0
            pct = float(seller.get("feedbackPercentage", 0) or 0)
            if score < MIN_FEEDBACK_SCORE or pct < MIN_FEEDBACK_PCT:
                continue
            iid = h.get("itemId")
            if not iid or iid in seen_ids:
                continue
            price = float((h.get("currentBidPrice") or h.get("price") or {}).get("value", 0) or 0)
            ship = h.get("shippingOptions", [{}])
            ship_cost = 0.0
            if ship:
                sc = (ship[0].get("shippingCost") or {}).get("value")
                ship_cost = float(sc) if sc else 0.0
            filtered.append({
                "itemId": iid, "title": title, "price": price, "shipping": ship_cost,
                "total": round(price + ship_cost, 2), "condition": h.get("condition"),
                "bidCount": h.get("bidCount"), "endDate": end_raw,
                "daysLeft": round(days_left, 2),
                "seller": seller.get("username"), "feedbackScore": score, "feedbackPct": pct,
                "url": h.get("itemWebUrl"), "image": (h.get("image") or {}).get("imageUrl"),
                "query": query["q"], "source": query["source"],
                "ledgerId": query.get("ledgerId"), "radarPid": query.get("pid"),
            })
        filtered.sort(key=lambda x: x["daysLeft"])
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

    candidates.sort(key=lambda x: x["daysLeft"])
    out = {"generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "queryCount": len(queries), "candidates": candidates}
    json.dump(out, open(os.path.join(ROOT, "ebay_sealed.json"), "w"), indent=1, ensure_ascii=False)
    print(f"scanned {len(queries)} queries, {len(candidates)} auction candidates written")


if __name__ == "__main__":
    main()
