#!/usr/bin/env python3
"""Daily PriceCharting refresh for the hand-matched h-* graded rows in h_manual_pc.json -> h_manual_pc_prices.json.
graded-price is PriceCharting's PSA 9 field (mapping verified in pricecharting.json); it is NOT CGC-specific, so every value is labelled unverified. Never prints the token."""
import json, os, time, datetime, urllib.request, urllib.parse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); T = os.environ.get("PRICECHARTING_TOKEN", "")
rows = json.load(open(os.path.join(ROOT, "h_manual_pc.json"))); p = os.path.join(ROOT, "h_manual_pc_prices.json")
out = json.load(open(p)) if os.path.exists(p) else {"rows": {}}
today = datetime.date.today().isoformat()
usd = lambda v: round(v / 100, 2) if isinstance(v, (int, float)) and v else None
for k, r in rows.items():
    time.sleep(1.1)
    try:
        with urllib.request.urlopen(urllib.request.Request("https://www.pricecharting.com/api/product?" + urllib.parse.urlencode({"t": T, "id": r["pcId"]}), headers={"User-Agent": "sealed-ledger/1.0"}), timeout=40) as f: d = json.load(f)
    except Exception: continue
    if d.get("status") != "success": continue
    e = out["rows"].setdefault(k, {"history": []})
    e.update({"pcId": r["pcId"], "product": d.get("product-name"), "console": d.get("console-name"), "grade9": usd(d.get("graded-price")), "ungraded": usd(d.get("loose-price")), "psa10": usd(d.get("manual-only-price")), "salesVolume": d.get("sales-volume"), "date": today,
              "label": "unverified: PriceCharting graded-price (PSA 9 field), not CGC-specific, not checked against sold listings"})
    e["history"] = [h for h in e["history"] if h[0] != today] + [[today, e["grade9"]]]
out["generated"] = today
json.dump(out, open(p, "w"), indent=1)
