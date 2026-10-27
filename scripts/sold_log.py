#!/usr/bin/env python3
"""Final prices of ended eBay auctions, free, from GitHub (replaces the Tracker's page fetches).

Uses the eBay Browse API (ended listings stay readable there; the public pages block GitHub with 403).
Registry: every auction seen in the scan feeds (ebay_sealed, ebay_wants, jumbo_listings, booklet_hits) plus
data/sold_queue.json, keyed by eBay item number with its end time. Once an auction has ended (+1h), fetch
https://www.ebay.com/itm/<id> and read the winning bid, shipping and bid count. Up to 3 tries per item.
Output: sold_prices.json {generated, items: {id: {status: sold|nosale|unknown, final, ship, bids, currency, end, checked, tries, title}}}
The Tracker copies these onto its auctions docs instead of opening the pages itself."""
import datetime, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_ebay_wants import get, token  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.datetime.now(datetime.timezone.utc)
MAX = int(os.environ.get("SOLD_MAX", "150"))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}


def load(n, d):
    try:
        return json.load(open(os.path.join(ROOT, n)))
    except Exception:
        return d


def ts(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def legacy(x):
    for k in ("itemId", "id", "url"):
        m = re.search(r"(?:v1\|)?(\d{10,13})", str(x.get(k) or ""))
        if m:
            return m.group(1)


def harvest(reg):
    def walk(x):
        if isinstance(x, dict):
            end = x.get("endDate") or x.get("itemEndDate") or x.get("ends") or x.get("endTime") or x.get("endsAt")
            auction = (str(x.get("type") or x.get("format") or x.get("buyingOptions") or "").upper().find("AUCTION") >= 0
                       or x.get("bids") is not None or x.get("bidCount") is not None)
            iid = legacy(x) if end and auction else None
            if iid and ts(end):
                reg.setdefault(iid, {"end": end, "url": x.get("url"), "title": (x.get("title") or x.get("name") or "")[:80]})
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    for f in ("ebay_sealed.json", "ebay_wants.json", "jumbo_listings.json", "booklet_hits.json"):
        walk(load(f, {}))
    for iid, v in load("data/sold_queue.json", {}).items():
        reg.setdefault(iid, v)


def check(iid, H):
    """eBay Browse API keeps returning ended listings: currentBidPrice is the winning bid,
    estimatedSoldQuantity says whether it sold. Page scraping is blocked (403) from GitHub."""
    d = get("https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id?legacy_item_id=" + iid, H, tries=2)
    if not d:
        g = get("https://api.ebay.com/buy/browse/v1/item/get_items_by_item_group?item_group_id=" + iid, H, tries=1) or {}
        d = (g.get("items") or [None])[0]
    if not d:
        return {"status": "unknown", "note": "not returned by the eBay API"}
    end = ts(d.get("itemEndDate"))
    if end and end > NOW:
        return {"status": "unknown", "note": "still live (relisted or extended)"}
    av = (d.get("estimatedAvailabilities") or [{}])[0]
    out = {"bids": d.get("bidCount"), "url": d.get("itemWebUrl")}
    so = d.get("shippingOptions") or []
    if so and (so[0].get("shippingCost") or {}).get("value") is not None:
        out["ship"] = float(so[0]["shippingCost"]["value"])
    if (av.get("estimatedSoldQuantity") or 0) >= 1:
        p = d.get("currentBidPrice") or d.get("price") or {}
        out.update(status="sold", final=float(p["value"]), currency=p.get("currency"))
    else:
        out["status"] = "nosale"
    return out


def main():
    reg = load("data/sold_registry.json", {})
    harvest(reg)
    res = load("sold_prices.json", {}).get("items", {})
    due = [i for i, v in reg.items() if ts(v["end"]) and ts(v["end"]) < NOW - datetime.timedelta(hours=1)
           and res.get(i, {}).get("status") not in ("sold", "nosale") and res.get(i, {}).get("tries", 0) < 3]
    due.sort(key=lambda i: ts(reg[i]["end"]))
    n = 0
    H = {"Authorization": "Bearer " + token(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    for iid in due[:MAX]:
        r = dict(res.get(iid, {}), title=reg[iid].get("title"), end=reg[iid]["end"], checked=NOW.isoformat(timespec="minutes"))
        p = check(iid, H)
        if p.get("status") in ("sold", "nosale"):
            r.update(p)
        else:
            r.update(status="unknown", tries=r.get("tries", 0) + 1, note=p.get("note"))
        res[iid] = r
        n += 1
        time.sleep(0.2)
    # forget registry entries over 45 days past their end
    cut = NOW - datetime.timedelta(days=45)
    reg = {i: v for i, v in reg.items() if ts(v["end"]) and ts(v["end"]) > cut}
    res = {i: v for i, v in res.items() if i in reg}
    json.dump(reg, open(os.path.join(ROOT, "data/sold_registry.json"), "w"), indent=0)
    json.dump({"generated": NOW.isoformat(timespec="minutes"), "items": res}, open(os.path.join(ROOT, "sold_prices.json"), "w"), indent=0)
    from collections import Counter
    print(len(reg), "auctions known;", n, "checked this run;", dict(Counter(v.get("status") for v in res.values())))


if __name__ == "__main__":
    main()
