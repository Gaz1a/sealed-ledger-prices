#!/usr/bin/env python3
"""Pre-check every buy candidate through the eBay Browse API (free) so the Buy Hunter does not open eBay pages.

Candidates: ebay_sealed.json candidates, ebay_wants.json singles/lots/jumbo items/booklet flags, jumbo_listings.json,
booklet_hits.json listings and flash.json hits; only those at or near target (or with no cap) are checked.
Output verified.json {generated, items: {legacy id: {live, ends, format, price, currentBid, bids, ship, shipKnown,
shipType, currency, seller, feedbackPct, feedbackScore, returns, condition, country, photos, title, url,
target, landed (est. all-in at the current price), snipe (auctions: highest bid that stays at or under target), src}}}.
Landed: US seller (price + ship) x 1.10 (LA tax); foreign price x 1.15 + ship + $12."""
import datetime, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_ebay_wants import get, token  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.datetime.now(datetime.timezone.utc)
MAX = int(os.environ.get("VERIFY_MAX", "700"))


def load(n, d):
    try:
        return json.load(open(os.path.join(ROOT, n)))
    except Exception:
        return d


def legacy(x):
    for k in ("itemId", "url", "id"):
        m = re.search(r"(?:v1\|)?(\d{10,13})", str(x.get(k) or ""))
        if m:
            return m.group(1)


def num(v):
    try:
        return float(v)
    except Exception:
        return None


def candidates():
    out = {}

    def add(x, src, prio, target=None):
        i = legacy(x)
        if not i:
            return
        t = target if target is not None else num(x.get("target") or x.get("targetAllIn") or x.get("capUSD") or x.get("ceiling"))
        if i not in out or prio < out[i]["prio"]:
            out[i] = {"prio": prio, "src": src, "target": t, "ref": x.get("wantId") or x.get("ledgerId") or x.get("radarPid") or (x.get("id") if str(x.get("id", "")).startswith("j-") else None)}

    def near(x):
        if x.get("underTarget"):
            return True
        a = num(x.get("allIn") or x.get("total") or x.get("allInAtCurrentBidUSD"))
        t = num(x.get("target") or x.get("targetAllIn") or x.get("capUSD"))
        return a is not None and t is not None and a <= t * 1.10

    for h in load("flash.json", {}).get("hits", []):
        add(h, "flash", 0)
    es = load("ebay_sealed.json", {})
    for x in es.get("candidates", []):
        add(x, "sealed", 1)
    for x in (es.get("jumbo") or {}).get("items", []):
        if near(x):
            add(x, "jumbo", 2)
    ew = load("ebay_wants.json", {})
    for x in ew.get("singles", []):
        if near(x) and x.get("nmVerified") is not False:
            add(x, "single", 1)
    for x in ew.get("lots", []):
        add(x, "lot", 2)
    for x in (ew.get("booklets") or {}).get("flags", []):
        add(x, "booklet", 1)
    for x in (ew.get("jumbo") or {}).get("items", []):
        if near(x):
            add(x, "jumbo", 3)
    for x in load("jumbo_listings.json", {}).get("listings", []):
        if near(x):
            add(x, "jumbo", 3)
    bh = load("booklet_hits.json", {})
    for k, v in (bh.get("items") or {}).items():
        for x in v.get("listings", []):
            add(dict(x, wantId=k), "booklet", 1)
    return dict(sorted(out.items(), key=lambda kv: kv[1]["prio"])[:MAX])


def check(i, c, H):
    d = get("https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id?legacy_item_id=" + i, H, tries=2)
    if not d:
        g = get("https://api.ebay.com/buy/browse/v1/item/get_items_by_item_group?item_group_id=" + i, H, tries=1) or {}
        d = (g.get("items") or [None])[0]
    if not d:
        return {"live": False, "note": "not returned by the eBay API (ended or removed)", "src": c["src"], "ref": c["ref"]}
    end = d.get("itemEndDate")
    av = (d.get("estimatedAvailabilities") or [{}])[0]
    ended = bool(end) and datetime.datetime.fromisoformat(end.replace("Z", "+00:00")) <= NOW
    live = not ended and av.get("estimatedAvailabilityStatus") not in ("OUT_OF_STOCK",)
    opts = d.get("buyingOptions") or []
    auction = "AUCTION" in opts
    price = num((d.get("currentBidPrice") if auction else d.get("price") or {}) and (d.get("currentBidPrice") if auction else d.get("price")).get("value"))
    so = (d.get("shippingOptions") or [{}])[0]
    ship = num((so.get("shippingCost") or {}).get("value"))
    country = (d.get("itemLocation") or {}).get("country")
    seller = d.get("seller") or {}
    r = {"live": live, "ends": end, "format": "auction" if auction else "buy-it-now", "bestOffer": "BEST_OFFER" in opts,
         "price": price, "bids": d.get("bidCount"), "ship": ship, "shipKnown": ship is not None,
         "shipType": so.get("shippingCostType"), "currency": "USD",
         "seller": seller.get("username"), "feedbackPct": num(seller.get("feedbackPercentage")), "feedbackScore": seller.get("feedbackScore"),
         "returns": (d.get("returnTerms") or {}).get("returnsAccepted"), "condition": d.get("condition"), "country": country,
         "photos": 1 + len(d.get("additionalImages") or []), "title": d.get("title"), "url": d.get("itemWebUrl"),
         "target": c["target"], "src": c["src"], "ref": c["ref"]}
    if price is not None and ship is not None:
        us = country == "US"
        r["landed"] = round((price + ship) * 1.10, 2) if us else round(price * 1.15 + ship + 12, 2)
        t = c["target"]
        if auction and t:
            s = (t / 1.10 - ship) if us else (t - ship - 12) / 1.15
            r["snipe"] = round(int(s * 100) / 100, 2) if s > 0 else None
            r["snipeOk"] = bool(r["snipe"] and r["snipe"] >= price + 1)
        if t:
            r["underTarget"] = r["landed"] <= t
    return r


def main():
    cands = candidates()
    H = {"Authorization": "Bearer " + token(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
         "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DUS%2Czip%3D91505"}   # shipping quoted to Burbank
    items = {}
    for i, c in cands.items():
        items[i] = check(i, c, H)
        time.sleep(0.1)
    json.dump({"generated": NOW.isoformat(timespec="minutes"), "checked": len(items), "items": items},
              open(os.path.join(ROOT, "verified.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    from collections import Counter
    print(len(items), "checked;", dict(Counter((v["src"], v["live"]) for v in items.values())),
          "ship known", sum(1 for v in items.values() if v.get("shipKnown")))


if __name__ == "__main__":
    main()
