#!/usr/bin/env python3
"""PriceCharting marketplace (included in Gaz's API plan): live offers and recent sales for ledger rows -> pc_offers.json.
--probe: check the response shapes and whether the CSV price-guide download works on this plan (token never printed)."""
import json, os, sys, time, datetime, urllib.request, urllib.parse, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = os.environ.get("PRICECHARTING_TOKEN", "")
if not T: sys.exit("PRICECHARTING_TOKEN is not set")
def load(p, d):
    try: return json.load(open(os.path.join(ROOT, p)))
    except Exception: return d
def get(path, **q):
    q["t"] = T
    url = "https://www.pricecharting.com" + path + "?" + urllib.parse.urlencode(q)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "sealed-ledger/1.0"}), timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e: return e.code, e.read()[:400]
    except Exception as e: return 0, repr(e).encode()[:200]
idc = load("pricecharting_ids.json", {})
if "--probe" in sys.argv:
    out = {}
    st, b = get("/price-guide/download-custom", category="pokemon-cards")
    out["csv"] = {"status": st, "head": b[:300].decode("utf-8", "replace").replace(T, "<t>")}
    st, b = get("/price-guide/download-custom", category="pokemon-cards")
    txt = b.decode("utf-8", "replace"); lines = txt.splitlines()
    out["csvFull"] = {"status": st, "bytes": len(b), "rows": len(lines), "header": lines[0] if lines else "", "row1": lines[1] if len(lines) > 1 else "",
                      "k149": next((l for l in lines if l.startswith("643401,")), None)}
    for lid in []:
        pid = (idc.get(lid) or {}).get("pcId")
        for status in ("available", "sold"):
            st, b = get("/api/offers", status=status, id=pid); time.sleep(1.2)
            out[f"{lid}:{status}"] = {"status": st, "body": b[:2500].decode("utf-8", "replace").replace(T, "<t>")}
    json.dump(out, open(os.path.join(ROOT, "pc_offers_probe.json"), "w"), indent=1)
    print(json.dumps({k: v["status"] for k, v in out.items()}))
