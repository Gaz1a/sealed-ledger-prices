#!/usr/bin/env python3
"""Daily eBay scan for Gaz's Japanese vending sheet checklist (ledger rows vs1-01..vs3-18, vs-00; added Nov 16).
Unpeeled sheets only. Series 2 is being collected first at $300 all-in or less (Gaz, Nov 16); Series 1/3 and #00 are
watched for price only. Writes vending_sheets.json:
  deals   - Series 2 Buy It Now at or under the target landed, or Series 2 auctions under the target ending within 48 h
            (with the snipe = target - shipping)
  bySheet - cheapest live listing per sheet (all series) + count, for the checklist
Few API calls (6 searches). Secrets: EBAY_CLIENT_ID, EBAY_CLIENT_SECRET."""
import json, os, re, sys, datetime, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_ebay_wants import get, token
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = {2: 300}
BAD = re.compile(r"\bpeeled\b(?!.*\bunpeeled\b)|\bno cards\b|\bempty\b|\bsingle card\b|\bpsa\b|\bcgc\b|\bbgs\b|\breprint\b|\bproxy\b|\bcustom\b", re.I)
def sheet_of(t):
    tl = t.lower()
    if re.search(r"preview|#\s*00\b|sheet\s*00\b", tl): return "vs-00"
    s = re.search(r"series\s*(1|2|3|i{1,3})\b|\b(blue|red|green)\b", tl)
    if not s: return None
    ser = {"i": 1, "ii": 2, "iii": 3, "blue": 1, "red": 2, "green": 3}.get(s.group(1) or s.group(2)) or int(s.group(1))
    n = re.search(r"(?:sheet|#|no\.?)\s*0?(\d{1,2})\b", tl)
    if not n or not 1 <= int(n.group(1)) <= 18: return f"vs{ser}-??"
    return f"vs{ser}-{int(n.group(1)):02d}"
def main():
    H = {"Authorization": "Bearer " + token(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    now = datetime.datetime.now(datetime.timezone.utc)
    seen, items = set(), []
    for q in ("pokemon vending series 2 unpeeled sheet", "pokemon vending sheet red unpeeled", "pokemon vending series 1 unpeeled sheet",
              "pokemon vending series 3 unpeeled sheet", "pokemon vending sheet unpeeled", "pokemon vending special preview sheet 00"):
        for buying in ("FIXED_PRICE", "AUCTION"):
            url = ("https://api.ebay.com/buy/browse/v1/item_summary/search?q=" + urllib.parse.quote(q) +
                   "&filter=" + urllib.parse.quote(f"buyingOptions:{{{buying}}},deliveryCountry:US") + "&limit=100")
            for it in (get(url, H) or {}).get("itemSummaries", []):
                if it["itemId"] in seen: continue
                seen.add(it["itemId"]); t = it.get("title", "")
                if "unpeel" not in t.lower() and "un-peel" not in t.lower(): continue
                if BAD.search(t.replace("Unpeeled", "").replace("unpeeled", "")) and "unpeel" not in t.lower(): continue
                sid = sheet_of(t)
                if not sid: continue
                if re.search(r"\blot\b|complete|full set|set of \d+|\d+\s*sheets", t, re.I): sid = "lot"
                auc = buying == "AUCTION"
                price = float(((it.get("currentBidPrice") if auc else None) or it.get("price") or {}).get("value") or 0)
                ship = None
                for so in it.get("shippingOptions") or []:
                    c = (so.get("shippingCost") or {}).get("value")
                    if c is not None: ship = float(c); break
                ends = it.get("itemEndDate")
                items.append({"sheet": sid, "title": t, "url": it.get("itemWebUrl", "").split("?")[0], "auction": auc, "price": price,
                              "shipping": ship, "landed": round(price + (ship or 0), 2) if ship is not None else None,
                              "bids": it.get("bidCount"), "ends": ends, "seller": (it.get("seller") or {}).get("username")})
    deals = []
    for x in items:
        ser = int(x["sheet"][2]) if x["sheet"].startswith("vs") and x["sheet"][2].isdigit() else None
        tgt = TARGET.get(ser)
        if not tgt or x["shipping"] is None: continue
        if not x["auction"] and x["landed"] <= tgt: deals.append(dict(x, target=tgt, why="Buy It Now at or under target"))
        elif x["auction"] and x["landed"] < tgt and x["ends"]:
            left = (datetime.datetime.fromisoformat(x["ends"].replace("Z", "+00:00")) - now).total_seconds() / 3600
            if 0 < left <= 48: deals.append(dict(x, target=tgt, snipe=round(tgt - x["shipping"], 2), hoursLeft=round(left, 1), why="Auction under target, ends within 48 h"))
    by = {}
    for x in items:
        if x["sheet"] in ("lot",) or x["sheet"].endswith("??"): continue
        b = by.setdefault(x["sheet"], {"n": 0, "cheapest": None})
        b["n"] += 1
        if x["landed"] is not None and (b["cheapest"] is None or x["landed"] < b["cheapest"]["landed"]): b["cheapest"] = {k: x[k] for k in ("title", "url", "landed", "auction", "bids", "ends")}
    out = {"generated": now.isoformat(timespec="seconds"), "rule": "Series 2 at $300 all-in or less (Gaz, Nov 16); unpeeled only",
           "deals": sorted(deals, key=lambda d: d["landed"]), "bySheet": dict(sorted(by.items())), "listings": len(items),
           "lots": [x for x in items if x["sheet"] == "lot"][:20]}
    json.dump(out, open(os.path.join(ROOT, "vending_sheets.json"), "w"), indent=1)
    print(f"{len(items)} unpeeled sheet listings, {len(deals)} Series 2 deals, {len(by)} sheets seen")
if __name__ == "__main__": main()
