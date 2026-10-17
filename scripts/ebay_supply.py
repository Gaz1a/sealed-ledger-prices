#!/usr/bin/env python3
"""Weekly eBay Browse API supply proxy for tracked sealed products -> ebay_supply.json. Uses EBAY_CLIENT_ID/EBAY_CLIENT_SECRET (already set)."""
import base64, json, os, re, statistics, sys, time, datetime, urllib.request, urllib.parse, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_market as sm
import jumbo_util as ju
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

CARD_BAD = re.compile(r"\b(psa|cgc|bgs|graded|slab|lot of|lot|custom|proxy|replica|fake|mystery|repack|empty|code card|sticker)\b", re.I)
def measure(title, H, need, new_only, bad, extra_q=""):
    asks, total = [], None
    filt = "buyingOptions:{FIXED_PRICE}," + ("conditions:{NEW}," if new_only else "") + "priceCurrency:USD"
    for off in (0, 200):
        q = urllib.parse.urlencode({"q": title + extra_q, "limit": 200, "offset": off, "filter": filt, "fieldgroups": "MATCHING_ITEMS"})
        j = call("https://api.ebay.com/buy/browse/v1/item_summary/search?" + q, H); time.sleep(0.5)
        if not j: break
        total = j.get("total", total)
        for it in j.get("itemSummaries", []):
            ttl = it.get("title", "")
            if bad.search(ttl) or not need <= set(re.findall(r"[a-z0-9]+", ttl.lower())): continue
            p = it.get("price") or {}
            if p.get("currency") == "USD": asks.append(float(p["value"]))
        if len(j.get("itemSummaries", [])) < 200: break
    return asks, total
def record(items, key, title, pid, asks, total, mk, extra=None):
    rec = {"title": title, "productId": pid, "apiTotalListings": total, "matchedListings": len(asks),
           "medianAsk": round(statistics.median(asks), 2) if asks else None, "lowAsk": min(asks) if asks else None,
           "tcgMarket": mk, "asOf": TODAY, **(extra or {})}
    hist = (items.get(key) or {}).get("history", [])
    if not hist or hist[-1][0] != TODAY: hist.append([TODAY, rec["matchedListings"], rec["medianAsk"]])
    rec["history"] = hist[-60:]
    base = next((h for h in hist if 21 <= (datetime.date.fromisoformat(TODAY) - datetime.date.fromisoformat(h[0])).days <= 35), None)
    if base and base[1] and base[2] and rec["medianAsk"]:
        dc, da = rec["matchedListings"] / base[1] - 1, rec["medianAsk"] / base[2] - 1
        rec["listingsChange4w"], rec["askChange4w"] = round(dc, 3), round(da, 3)
        rec["signal"] = "tightening" if dc <= -0.15 and da >= 0.05 else "loosening" if dc >= 0.15 and da <= -0.05 else "neutral"
    else:
        rec["signal"] = "needs_history"
    items[key] = rec
def main():
    if not CID or not CSEC: sys.exit("EBAY keys not set")
    tok = call("https://api.ebay.com/identity/v1/oauth2/token", {"Authorization": "Basic " + base64.b64encode(f"{CID}:{CSEC}".encode()).decode(), "Content-Type": "application/x-www-form-urlencoded"},
               urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode())
    if not tok: sys.exit("eBay token request failed")
    H = {"Authorization": "Bearer " + tok["access_token"], "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    tracked = sm.load("tracked.json", {}); prices = sm.load("prices.json", {}).get("prices", {})
    sets = sm.load("item_sets.json", {})
    prev = sm.load("ebay_supply.json", {}); items = dict(prev.get("items", {}))
    sealed_re = re.compile(sm.SEALED_WORDS.pattern, re.I); n = 0
    for lid, t in tracked.items():
        title = t.get("title") or ""
        st = sets.get(lid, "")
        if re.search(r"gundam|one piece|lorcana|riftbound", st + " " + title, re.I): continue   # non-Pokemon: query would be wrong
        if not sealed_re.search(title) or re.search(r"\d+/\d+|\bTG\d", title): continue
        if st and st != "Pokemon" and not set(re.findall(r"[a-z0-9]+", st.lower())) <= set(re.findall(r"[a-z0-9]+", title.lower())):
            title = f"{st} {title}"
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
    # --- jumbo products: sealed (NEW, title-filtered) and loose jumbo cards (any condition, must say jumbo/oversize) ---
    jp = ju.prices(); jid_map = ju.ids(); jn = 0
    for jid, v in jid_map.items():
        jt = jp.get(jid, {})
        if v.get("sealedId"):
            sn = (jt.get("sealed") or {}).get("name") or v["title"]
            need = {w for w in re.findall(r"[a-z0-9]+", sn.lower()) if w not in {"the", "of", "and"}}
            asks, total = measure(sn, H, need, True, BAD, " pokemon")
            record(items, f"jumbo:{jid}:sealed", sn, v["sealedId"], asks, total, (jt.get("sealed") or {}).get("market"), {"jumbo": True, "kind": "sealed"}); jn += 1
        if v.get("cardId"):
            cn = (jt.get("card") or {}).get("name") or ""
            base = re.sub(r"\s+-\s+[A-Za-z0-9/]+(\s*\(.*\))?$", "", cn).strip()
            if not base: continue
            need = {w for w in re.findall(r"[a-z0-9]+", base.lower()) if w not in {"the", "of", "and"}} | {"jumbo"}
            asks, total = measure(base + " jumbo", H, need, False, CARD_BAD, " pokemon card")
            record(items, f"jumbo:{jid}:card", base, v["cardId"], asks, total, (jt.get("card") or {}).get("market"), {"jumbo": True, "kind": "card"}); jn += 1
    print(jn, "jumbo products scanned")
    json.dump({"generated": TODAY, "source": "eBay Browse API (active FIXED_PRICE, NEW, USD listings; title-filtered)", "note": "Counts are of up to 400 returned listings after title filtering, not eBay's raw total; trend needs ~4 weekly runs.",
               "items": items}, open("ebay_supply.json", "w"), indent=1)
    print(n, "sealed products;", sum(1 for r in items.values() if r.get("matchedListings")), "with listings")
if __name__ == "__main__": main()
