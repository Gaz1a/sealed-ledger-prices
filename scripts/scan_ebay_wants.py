#!/usr/bin/env python3
"""Weekly eBay Browse API scan driven by the want list (wants.json: ledgerId -> title).
Finds (1) single listings at/near each wanted card's max price and (2) lots that name wanted cards.
Mechanical matching only; Claude judges photos, condition and value. Writes ebay_wants.json."""
import json, os, re, sys, time, base64, datetime, html, urllib.request, urllib.parse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CID, CSEC = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
UA = "sealed-ledger-wants-scout/1.0"
TAX = 1.10
MIN_FB, MIN_PCT = 50, 97.0
MAX_LOT_DETAIL = 60
NOISE = re.compile(r"\bpsa\b|\bcgc\b|\bbgs\b|\bgraded\b|\bslab\b|\breprint\b|\bcustom\b|\bproxy\b|\bfake\b|\bplush\b|"
                   r"\bfigure\b|\bfunko\b|\bsticker\b|\bjumbo\b|\boversized?\b|\bjapanese\b|\bkorean\b|\bchinese\b|"
                   r"\bdigital\b|\bcode card\b|\bdamaged\b|\bheavily played\b|\bpoor\b|\bhp\b|\bmp\b|\bmetal card\b|\bfan ?art\b", re.I)
LOT = re.compile(r"\blots?\b|\bbundle\b|\bcollection\b|\bx\s?\d+\b|\b\d+\s?(cards?|pcs|pieces)\b|\bcomplete\b|\bholos?\b", re.I)
LOTQ = ["gyarados lot pokemon cards", "magikarp lot pokemon cards", "gyarados magikarp lot",
        "base set holo lot", "jungle holo lot", "fossil holo lot", "team rocket holo lot",
        "wotc holo rare lot pokemon", "vintage pokemon holo lot"]

def load(n, d):
    p = os.path.join(ROOT, n)
    return json.load(open(p)) if os.path.exists(p) else d

def get(url, h=None, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, **(h or {})}), timeout=25) as r:
                return json.load(r)
        except Exception as e:
            if i == tries - 1: print("FAIL", url[:100], e, file=sys.stderr); return None
            time.sleep(2 * (i + 1))

def token():
    if not CID or not CSEC: sys.exit("EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set")
    a = base64.b64encode(f"{CID}:{CSEC}".encode()).decode()
    b = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode()
    r = urllib.request.Request("https://api.ebay.com/identity/v1/oauth2/token", data=b,
        headers={"Authorization": f"Basic {a}", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(r, timeout=25) as x: return json.load(x)["access_token"]

NUM = re.compile(r"(?<![\w/])([0-9A-Z]{1,4}/[0-9A-Z]{2,4})(?![\w/])")
def parse(title):
    t = re.sub(r"\(.*?\)", "", title)
    m = NUM.search(t)
    name = re.split(r"\s[-—–]\s|\s#|\s\d", t)[0].strip()
    return name, (m.group(1) if m else None), t.strip()

def target(m):
    return m * (1.0 if m < 10 else .9 if m < 100 else .85 if m < 300 else .8)

def seller_ok(h):
    s = h.get("seller", {})
    return (s.get("feedbackScore") or 0) >= MIN_FB and float(s.get("feedbackPercentage") or 0) >= MIN_PCT

def price_of(h):
    v = ((h.get("price") or h.get("currentBidPrice") or {}).get("value"))
    return float(v) if v is not None else None

def ship_of(h):
    for s in h.get("shippingOptions") or []:
        c = s.get("shippingCost")
        if c: return float(c["value"])
    return None

def has_num(text, num):
    return bool(num) and re.search(r"(?<![\w/])" + re.escape(num) + r"(?![\w/])", text, re.I) is not None

def search(q, H, filt, limit=50, offset=0, sort="newlyListed"):
    url = ("https://api.ebay.com/buy/browse/v1/item_summary/search?q=" + urllib.parse.quote(q) +
           "&filter=" + urllib.parse.quote(filt) + f"&limit={limit}&offset={offset}&sort={sort}")
    return (get(url, H) or {}).get("itemSummaries", [])

def main():
    wants, prices = load("wants.json", {}), load("prices.json", {}).get("prices", {})
    H = {"Authorization": "Bearer " + token(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    W = {}
    for wid, title in wants.items():
        name, num, clean = parse(title)
        mk = (prices.get(wid) or {}).get("market")
        W[wid] = {"title": title, "name": name, "num": num, "clean": clean, "market": mk, "target": round(target(mk), 2) if mk else None}
    singles, seen = [], set()
    nq = 0
    for wid, w in W.items():
        if not w["market"] or w["market"] < 8: continue   # cheap commons are only worth buying inside lots
        q = f"{w['name']} {w['num']}" if w["num"] else w["clean"]
        filt = f"price:[{max(2, round(w['market'] * 0.35))}..{round(w['market'] * 1.6)}],priceCurrency:USD,buyingOptions:{{FIXED_PRICE|AUCTION}}"
        nq += 1
        for h in search(q, H, filt, 40, 0, "price"):
            t = h.get("title", "")
            if h["itemId"] in seen or NOISE.search(t) or not seller_ok(h): continue
            if w["name"].lower() not in t.lower(): continue
            if w["num"] and not has_num(t, w["num"]): continue
            if not w["num"] and not all(x.lower() in t.lower() for x in re.findall(r"[A-Za-z]{3,}", w["clean"])[:3]): continue
            sh = ship_of(h); price = price_of(h)
            if price is None: continue
            all_in = round((price + (sh or 0)) * TAX, 2)
            if all_in > w["target"] * 1.15: continue
            seen.add(h["itemId"])
            singles.append({"wantId": wid, "want": w["title"], "market": w["market"], "target": w["target"],
                "title": t, "url": h.get("itemWebUrl"), "price": price, "shipping": sh, "shipUnknown": sh is None, "allIn": all_in,
                "underTarget": all_in <= w["target"], "buyingOptions": h.get("buyingOptions"),
                "bids": h.get("bidCount"), "itemEndDate": h.get("itemEndDate"), "condition": h.get("condition"),
                "seller": h.get("seller", {}).get("username"), "feedbackPct": h.get("seller", {}).get("feedbackPercentage"),
                "feedbackScore": h.get("seller", {}).get("feedbackScore"), "image": (h.get("image") or {}).get("imageUrl")})
        time.sleep(0.25)
    names = {w["name"].lower() for w in W.values() if w["name"]}
    cands = {}
    for q in LOTQ:
        filt = "price:[5..250],priceCurrency:USD,buyingOptions:{FIXED_PRICE|AUCTION}"
        for off in (0, 100):
            nq += 1
            for h in search(q, H, filt, 100, off):
                t = h.get("title", "")
                if h["itemId"] in cands or NOISE.search(t) or not LOT.search(t) or not seller_ok(h): continue
                if not any(n in t.lower() for n in names) and not re.search(r"base set|jungle|fossil|team rocket|gym|neo", t, re.I): continue
                cands[h["itemId"]] = h
            time.sleep(0.25)
    lots = []
    for h in sorted(cands.values(), key=lambda x: price_of(x) or 1e9)[:MAX_LOT_DETAIL * 2]:
        if len(lots) >= MAX_LOT_DETAIL: break
        d = get("https://api.ebay.com/buy/browse/v1/item/" + urllib.parse.quote(h["itemId"], safe=""), H) or {}
        desc = html.unescape(re.sub(r"<[^>]+>", " ", d.get("description") or d.get("shortDescription") or ""))
        text = h["title"] + " " + desc
        matched = [wid for wid, w in W.items() if w["num"] and w["name"].lower() in text.lower() and has_num(text, w["num"])]
        namedhit = re.search(r"gyarados|magikarp", text, re.I) is not None
        if not matched and not namedhit: continue
        photos = [(h.get("image") or {}).get("imageUrl")] + [i.get("imageUrl") for i in (d.get("additionalImages") or h.get("additionalImages") or [])]
        lots.append({"itemId": h["itemId"], "title": h["title"], "url": h.get("itemWebUrl"), "price": price_of(h),
            "shipping": ship_of(h), "shipUnknown": ship_of(h) is None, "buyingOptions": h.get("buyingOptions"), "itemEndDate": h.get("itemEndDate"),
            "seller": h.get("seller", {}).get("username"), "feedbackScore": h.get("seller", {}).get("feedbackScore"),
            "feedbackPct": h.get("seller", {}).get("feedbackPercentage"), "returnsAccepted": (d.get("returnTerms") or {}).get("returnsAccepted"),
            "condition": h.get("condition"), "matchedIds": matched, "photos": [p for p in photos if p][:6], "desc": re.sub(r"\s+", " ", desc)[:700]})
        time.sleep(0.3)
    json.dump({"generated": datetime.date.today().isoformat(), "wants": len(W), "queries": nq,
               "singles": singles, "lots": lots}, open(os.path.join(ROOT, "ebay_wants.json"), "w"), indent=1)
    print(len(singles), "singles,", len(lots), "lots,", nq, "queries")

if __name__ == "__main__":
    main()
