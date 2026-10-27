#!/usr/bin/env python3
"""Final prices of ended eBay auctions, read from the public item pages (free; replaces the Tracker's page fetches).

Registry: every auction seen in the scan feeds (ebay_sealed, ebay_wants, jumbo_listings, booklet_hits) plus
data/sold_queue.json, keyed by eBay item number with its end time. Once an auction has ended (+1h), fetch
https://www.ebay.com/itm/<id> and read the winning bid, shipping and bid count. Up to 3 tries per item.
Output: sold_prices.json {generated, items: {id: {status: sold|nosale|unknown, final, ship, bids, currency, end, checked, tries, title}}}
The Tracker copies these onto its auctions docs instead of opening the pages itself."""
import datetime, json, os, re, sys, time, urllib.request

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


MONEY = r"([A-Z]{0,3}\s?[$£€]|EUR|GBP|AU \$|C \$)\s?([\d,]+\.\d{2})"


def parse(html):
    t = re.sub(r"<[^>]+>", " ", html)
    t = re.sub(r"&nbsp;|\s+", " ", t)
    out = {}
    if re.search(r"(This listing (has )?ended|Bidding has ended|This listing was ended|no longer available)", t, re.I) is None and "Winning bid" not in t:
        out["status"] = "live"
        return out
    m = re.search(r"Winning bid:?\s*" + MONEY, t)
    if m:
        out.update(status="sold", currency=m.group(1).strip(), final=float(m.group(2).replace(",", "")))
    elif re.search(r"(Starting bid|Price):?.{0,40}\[\s*0 bids?\s*\]|0 bids|no bids", t, re.I):
        out["status"] = "nosale"
    m = re.search(r"\[\s*(\d+)\s*bids?\s*\]", t)
    if m:
        out["bids"] = int(m.group(1))
    if re.search(r"Shipping:?\s*Free", t, re.I):
        out["ship"] = 0.0
    else:
        m = re.search(r"Shipping:?\s*" + MONEY, t)
        if m:
            out["ship"] = float(m.group(2).replace(",", ""))
    return out


def main():
    reg = load("data/sold_registry.json", {})
    harvest(reg)
    res = load("sold_prices.json", {}).get("items", {})
    due = [i for i, v in reg.items() if ts(v["end"]) and ts(v["end"]) < NOW - datetime.timedelta(hours=1)
           and res.get(i, {}).get("status") not in ("sold", "nosale") and res.get(i, {}).get("tries", 0) < 3]
    due.sort(key=lambda i: ts(reg[i]["end"]))
    n = 0
    for iid in due[:MAX]:
        r = dict(res.get(iid, {}), title=reg[iid].get("title"), end=reg[iid]["end"], checked=NOW.isoformat(timespec="minutes"))
        try:
            with urllib.request.urlopen(urllib.request.Request(f"https://www.ebay.com/itm/{iid}", headers=UA), timeout=25) as h:
                p = parse(h.read().decode("utf-8", "replace"))
        except Exception as e:
            p = {"status": "unknown", "error": str(e)[:80]}
        if p.get("status") in ("sold", "nosale"):
            r.update(p)
        else:
            r.update(status="unknown", tries=r.get("tries", 0) + 1, note=p.get("error") or p.get("status") or "price not shown")
        res[iid] = r
        n += 1
        time.sleep(1.2)
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
