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

if "--run" in sys.argv:
    # every ledger want (and graded slab) with a PriceCharting id: cheapest live offers and the latest marketplace sales
    wants = load("wants_auto.json", {}).get("items", {})
    pcj = load("pricecharting.json", {})
    pcid = {k: v.get("pcId") for sec in ("cards", "sealed") for k, v in (pcj.get(sec) or {}).items() if v.get("matched") and v.get("pcId")}
    for k, v in idc.items():
        if v.get("pcId"): pcid.setdefault(k, v["pcId"])
    prev = load("pc_offers.json", {}).get("items", {})
    out, calls = {}, 0
    def offers(status, pid):
        global calls
        st, b = get("/api/offers", status=status, id=pid, sort="lowest-price" if status == "available" else "starts"); time.sleep(1.2)
        calls += 1
        if st != 200: return None
        try: return json.loads(b).get("offers") or []
        except Exception: return None
    def slim(o):
        return {"price": round(o.get("price", 0) / 100, 2), "cond": o.get("condition-string") or o.get("include-string"),
                "graded": bool(o.get("grade-co-id")), "cert": o.get("cert-id") or None, "desc": (o.get("description") or "")[:120],
                "url": "https://www.pricecharting.com" + (o.get("offer-url") or ""), "img": o.get("image-url"),
                "date": (o.get("date-sold") or o.get("date-listed") or o.get("starts") or "")[:10] or None}
    for lid in sorted(wants):
        pid = pcid.get(lid)
        if not pid: continue
        a = offers("available", pid)
        s = offers("sold", pid)
        if a is None and s is None:
            if lid in prev: out[lid] = prev[lid]
            continue
        out[lid] = {"pcId": pid, "live": [slim(o) for o in (a or [])[:3]], "sold": [slim(o) for o in (s or [])[:5]]}
    doc = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
           "note": "PriceCharting marketplace: cheapest live offers (asking, any condition unless graded) and latest sales, per ledger want",
           "calls": calls, "items": out}
    json.dump(doc, open(os.path.join(ROOT, "pc_offers.json"), "w"), separators=(",", ":"), ensure_ascii=False)
    print(len(out), "wants with marketplace data,", sum(1 for v in out.values() if v["live"]), "with live offers,", calls, "calls")
