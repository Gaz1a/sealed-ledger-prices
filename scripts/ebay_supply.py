#!/usr/bin/env python3
"""Weekly eBay Browse API supply proxy for tracked sealed products -> ebay_supply.json. Uses EBAY_CLIENT_ID/EBAY_CLIENT_SECRET (already set)."""
import base64, json, os, re, statistics, sys, time, datetime, urllib.request, urllib.parse, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_market as sm
CID, CSEC = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
TODAY = datetime.date.today().isoformat()
BAD = re.compile(r"\b(empty|lot of|custom|sleeve|opened|no cards|code card|repack|mystery|break|proxy|sticker|display case|storage|replica|pack art|single pack|card only|case of)\b", re.I)
def call(url, hdr, data=None):
    req = urllib.request.Request(url, data=data, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=40) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429: raise SystemExit("rate limited; partial results kept")
        return None
    except Exception: return None
def main():
    if not CID or not CSEC: sys.exit("EBAY keys not set")
    tok = call("https://api.ebay.com/identity/v1/oauth2/token", {"Authorization": "Basic " + base64.b64encode(f"{CID}:{CSEC}".encode()).decode(), "Content-Type": "application/x-www-form-urlencoded"},
               urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode())
    if not tok: sys.exit("eBay token request failed")
    H = {"Authorization": "Bearer " + tok["access_token"], "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    tracked = sm.load("tracked.json", {}); prices = sm.load("prices.json", {}).get("prices", {})
    prev = sm.load("ebay_supply.json", {}); items = dict(prev.get("items", {}))
    sealed_re = re.compile(sm.SEALED_WORDS.pattern, re.I); n = 0
    for lid, t in tracked.items():
        title = t.get("title") or ""
        if not sealed_re.search(title) or re.search(r"\d+/\d+|\bTG\d", title): continue
        need = {w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in {"the", "of", "and"}}
        asks, total = [], None
        for off in (0, 200):
            q = urllib.parse.urlencode({"q": title + " pokemon", "limit": 200, "offset": off, "filter": "buyingOptions:{FIXED_PRICE},conditions:{NEW},priceCurrency:USD", "fieldgroups": "MATCHING_ITEMS"})
            j = call("https://api.ebay.com/buy/browse/v1/item_summary/search?" + q, H); time.sleep(0.5)
            if not j: break
            total = j.get("total", total)
            for it in j.get("itemSummaries", []):
                ttl = it.get("title", "")
                if BAD.search(ttl) or not need <= set(re.findall(r"[a-z0-9]+", ttl.lower())): continue
                p = it.get("price") or {}
                if p.get("currency") == "USD":
                    ship = 0.0
                    asks.append(float(p["value"]))
            if len(j.get("itemSummaries", [])) < 200: break
        n += 1
        mk = (prices.get(lid) or {}).get("market")
        rec = {"title": title, "productId": t["productId"], "apiTotalListings": total, "matchedListings": len(asks),
               "medianAsk": round(statistics.median(asks), 2) if asks else None, "lowAsk": min(asks) if asks else None,
               "tcgMarket": mk, "asOf": TODAY}
        hist = (items.get(lid) or {}).get("history", [])
        if not hist or hist[-1][0] != TODAY: hist.append([TODAY, rec["matchedListings"], rec["medianAsk"]])
        rec["history"] = hist[-60:]
        base = next((h for h in hist if 21 <= (datetime.date.fromisoformat(TODAY) - datetime.date.fromisoformat(h[0])).days <= 35), None)
        if base and base[1] and base[2] and rec["medianAsk"]:
            dc, da = rec["matchedListings"] / base[1] - 1, rec["medianAsk"] / base[2] - 1
            rec["listingsChange4w"], rec["askChange4w"] = round(dc, 3), round(da, 3)
            rec["signal"] = "tightening" if dc <= -0.15 and da >= 0.05 else "loosening" if dc >= 0.15 and da <= -0.05 else "neutral"
        else:
            rec["signal"] = "needs_history"
        items[lid] = rec
    json.dump({"generated": TODAY, "source": "eBay Browse API (active FIXED_PRICE, NEW, USD listings; title-filtered)", "note": "Counts are of up to 400 returned listings after title filtering, not eBay's raw total; trend needs ~4 weekly runs.",
               "items": items}, open("ebay_supply.json", "w"), indent=1)
    print(n, "sealed products;", sum(1 for r in items.values() if r.get("matchedListings")), "with listings")
if __name__ == "__main__": main()
