"""Resume the PPT sales-signals probe for productIds not yet fetched. Plain card call only (recentSales + prices; no history/eBay) to stay inside the credit quota."""
import csv, json, os, time, datetime, urllib.request, urllib.error
K = os.environ["PPT_KEY"]
rows = list(csv.DictReader(open("owned_rows.csv"))); tr = json.load(open("tracked.json"))
raw = json.load(open("sales_signals_raw.json"))
P = raw["products"]
pids = sorted({r["productId"] or str(tr.get(r["id"], {}).get("productId") or "") for r in rows} - {""}, key=int)
stop = None
for pid in pids:
    if pid in P and "error" not in P[pid]: continue
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://www.pokemonpricetracker.com/api/v2/cards?tcgPlayerId={pid}&limit=1", headers={"Authorization": "Bearer " + K}), timeout=60) as r: d = json.load(r)
    except urllib.error.HTTPError as e:
        P[pid] = {"error": f"http {e.code}", "plainOnly": True}
        if e.code in (429, 402, 403): stop = f"stopped at {pid}: http {e.code}"; break
        continue
    except Exception as e: P[pid] = {"error": type(e).__name__, "plainOnly": True}; continue
    x = d.get("data", d); x = x[0] if isinstance(x, list) and x else x
    P[pid] = {"plainOnly": True, "fetchedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "meta": {k: v for k, v in d.items() if k != "data"},
              "card": {"tcgPlayerId": x.get("tcgPlayerId"), "name": x.get("name"), "setName": x.get("setName"), "tcgPlayerUrl": x.get("tcgPlayerUrl"), "prices": {k: v for k, v in (x.get("prices") or {}).items() if k != "variants"}} if isinstance(x, dict) else None} if x else {"plainOnly": True, "empty": True}
    time.sleep(1)
raw["stop2"] = stop
json.dump(raw, open("sales_signals_raw.json", "w"), indent=1)
