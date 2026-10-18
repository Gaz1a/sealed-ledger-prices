#!/usr/bin/env python3
"""Jumbo want-list + auction scan. For every entry in jumbo_ids.json:
  sealedId -> query the sealed box name;  cardId(s) -> query "<card name> jumbo <card number>".
Skips entries with no id and any whose ledger jumbo market (jumbo_prices.json) is under $5.
Target = 85% of market for $100-299, 90% for $10-99 ($5-9.99 uses 90% too), 80% for $300+.
Covers fixed-price AND auction listings (auction price = current bid; bids shown). Mechanical matching only.
Rotation: each run takes the MAX_Q least-recently-queried tasks (state lives in the output file), stops at the first eBay 429.
Output ebay_jumbo.json keyed by jumbo id; a summary is mirrored into ebay_wants.json['jumbo'] and ebay_sealed.json['jumbo']."""
import json, os, re, sys, time, base64, datetime, urllib.request, urllib.parse, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CID, CSEC = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
MAX_Q = int(os.environ.get("MAX_Q", "120"))
TAX = 1.10          # same all-in convention as scan_ebay_wants.py (price + shipping, x1.10 sales-tax estimate)
MIN_MARKET, MIN_FB, MIN_PCT = 5.0, 50, 97.0
NOISE = re.compile(r"\bpsa\b|\bcgc\b|\bbgs\b|\bgraded\b|\bslab\b|\breprint\b|\bcustom\b|\bproxy\b|\bfake\b|\bplush\b|\bfunko\b|\bsticker\b|\bdigital\b|\bcode card\b|\bdamaged\b|\bempty\b|box only|no cards|\bopened\b|\bheavily played\b|\bdmg\b|\bcreased?\b|\blots?\b|\bbundle\b", re.I)
def ld(n, d):
    try: return json.load(open(os.path.join(ROOT, n)))
    except Exception: return d
def pct(m): return 0.80 if m >= 300 else 0.85 if m >= 100 else 0.90
RL = {"hit": False}
def get(url, H):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429: RL["hit"] = True
        return None
    except Exception: return None
def token():
    a = base64.b64encode(f"{CID}:{CSEC}".encode()).decode()
    b = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://api.ebay.com/identity/v1/oauth2/token", data=b, headers={"Authorization": f"Basic {a}", "Content-Type": "application/x-www-form-urlencoded"}), timeout=30) as x: return json.load(x)["access_token"]
def split_card(nm):
    nm = re.sub(r"\s*\(.*?\)\s*$", "", nm or "").strip()
    m = re.match(r"^(.*?)\s+-\s+(.+)$", nm)
    return (m.group(1).strip(), m.group(2).strip()) if m else (nm, None)
def has_num(t, n): return bool(n) and re.search(r"(?<![\w/])" + re.escape(n) + r"(?![\w/])", t, re.I) is not None
def words(s): return [w for w in re.findall(r"[A-Za-z0-9]{3,}", s.lower())]

ids, prices = ld("jumbo_ids.json", {}), ld("jumbo_prices.json", {}).get("items", {})
tasks, skipped = [], {"noId": 0, "under5": 0, "noMarket": 0}
for jid, v in ids.items():
    p = prices.get(jid, {})
    if v.get("sealedId"):
        e = p.get("sealed") or {}
        tasks.append((jid, "sealed", v["sealedId"], e.get("name") or v["title"], e.get("market")))
    elif not v.get("sealedIds"): skipped["noId"] += 1
    if v.get("cardId"):
        e = p.get("card") or {}
        tasks.append((jid, "card", v["cardId"], e.get("name") or v["title"], e.get("market")))
    for it in (p.get("cardSet") or {}).get("items", []):
        tasks.append((jid, f"card_{it['productId']}", it["productId"], it.get("name") or v["title"], it.get("market")))
    for it in (p.get("sealedSet") or {}).get("items", []):
        tasks.append((jid, f"sealed_{it['productId']}", it["productId"], it.get("name") or v["title"], it.get("market")))
    if not v.get("cardId") and not v.get("cardIds"): skipped["noId"] += 1
elig = []
for t in tasks:
    if t[4] is None: skipped["noMarket"] += 1
    elif t[4] < MIN_MARKET: skipped["under5"] += 1
    else: elig.append(t)
out = ld("ebay_jumbo.json", {"items": {}})
out.setdefault("items", {})
def last(t): return ((out["items"].get(t[0]) or {}).get(t[1]) or {}).get("queriedAt") or ""
elig.sort(key=lambda t: (last(t), t[0]))
done = 0
if CID and CSEC:
    H = {"Authorization": "Bearer " + token(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    for jid, kind, pid, nm, mk in elig[:MAX_Q]:
        if RL["hit"]: break
        if kind.startswith("sealed"):
            base, num = re.sub(r"\s*\(.*?\)\s*$", "", nm).strip(), None; q = base
        else:
            base, num = split_card(nm); q = f"{base} jumbo {num}" if num else f"{base} jumbo"
        tgt = round(mk * pct(mk), 2)
        filt = f"price:[1..{max(15, round(mk * 2))}],priceCurrency:USD,buyingOptions:{{FIXED_PRICE|AUCTION}}"
        j = get("https://api.ebay.com/buy/browse/v1/item_summary/search?q=" + urllib.parse.quote(q) + "&filter=" + urllib.parse.quote(filt) + "&limit=40&sort=price", H)
        time.sleep(0.3)
        if j is None: continue
        done += 1
        ws, hits = words(base), []
        for h in j.get("itemSummaries", []):
            t = h.get("title", "")
            s = h.get("seller") or {}
            if NOISE.search(t) or (s.get("feedbackScore") or 0) < MIN_FB or float(s.get("feedbackPercentage") or 0) < MIN_PCT: continue
            if not all(w in t.lower() for w in ws): continue
            if not kind.startswith("sealed") and (not re.search(r"jumbo|oversize", t, re.I) or (num and not has_num(t, num))): continue
            pr = (h.get("currentBidPrice") or h.get("price") or {}).get("value")
            if pr is None: continue
            sh = next((float(o["shippingCost"]["value"]) for o in h.get("shippingOptions") or [] if o.get("shippingCost")), None)
            allin = round((float(pr) + (sh or 0)) * TAX, 2)
            if allin > tgt * 1.15: continue
            auc = "AUCTION" in (h.get("buyingOptions") or [])
            hits.append({"title": t, "url": h.get("itemWebUrl"), "price": float(pr), "shipping": sh, "shipUnknown": sh is None, "allIn": allin, "underTarget": allin <= tgt,
                         "auction": auc, "bids": h.get("bidCount") if auc else None, "itemEndDate": h.get("itemEndDate"), "condition": h.get("condition"),
                         "seller": s.get("username"), "feedbackPct": s.get("feedbackPercentage"), "feedbackScore": s.get("feedbackScore"), "image": (h.get("image") or {}).get("imageUrl")})
            if len(hits) >= 3: break
        out["items"].setdefault(jid, {"title": ids[jid]["title"], "lang": ids[jid]["lang"]})[kind] = {
            "productId": pid, "query": q, "refMarketUSD": mk, "refSource": "ledger jumbo market (jumbo_prices.json, TCGplayer market, unverified)",
            "targetPct": pct(mk), "targetUSD": tgt, "queriedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "hits": hits}
else: print("no eBay credentials")
# drop entries that are no longer eligible
keep = {(t[0], t[1]) for t in elig}
for jid in list(out["items"]):
    for k in [k for k in out["items"][jid] if k not in ("title", "lang") and (jid, k) not in keep]: out["items"][jid].pop(k)
    if not any(k not in ("title", "lang") for k in out["items"][jid]): out.pop("items", {}).pop(jid, None) if False else out["items"].pop(jid)
out.update({"generated": datetime.date.today().isoformat(), "eligibleQueries": len(elig), "queriedThisRun": done, "maxPerRun": MAX_Q, "skipped": skipped,
            "rateLimited": RL["hit"], "note": "eBay 429: run stopped early, remaining queries rotate to next run" if RL["hit"] else None,
            "rules": "sealed -> box name; card -> name + jumbo + number; skip no id / market < $5; target 85% ($100-299), 90% ($5-99), 80% ($300+) of ledger jumbo market; all-in = (price or current bid + shipping) x1.10"})
json.dump(out, open(os.path.join(ROOT, "ebay_jumbo.json"), "w"), indent=1)
# mirror an under-target / near-miss summary into the want-list and auction outputs (keyed by jumbo id)
flat = [{"jumboId": jid, "kind": k, "title": h["title"], "url": h["url"], "allIn": h["allIn"], "target": d["targetUSD"], "underTarget": h["underTarget"], "auction": h["auction"], "bids": h["bids"], "itemEndDate": h["itemEndDate"]}
        for jid, it in out["items"].items() for k, d in it.items() if k not in ("title", "lang") for h in d["hits"]]
for fn, sel in (("ebay_wants.json", flat), ("ebay_sealed.json", [x for x in flat if x["auction"]])):
    d = ld(fn, None)
    if d is not None: d["jumbo"] = {"generated": out["generated"], "source": "ebay_jumbo.json", "items": sel}; json.dump(d, open(os.path.join(ROOT, fn), "w"), indent=1)
print("eligible", len(elig), "queried", done, "skipped", skipped, "rateLimited", RL["hit"], "hits", len(flat))
