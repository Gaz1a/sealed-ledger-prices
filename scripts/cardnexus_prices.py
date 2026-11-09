#!/usr/bin/env python3
"""Daily CardNexus cross-check: Cardmarket (EUR) + TCGplayer (USD) price snapshots for every tracked.json item.
Writes cardnexus.json and caches ledgerId -> CardNexus id in cardnexus_ids.json.
Fails soft: if the API is unreachable the previous cardnexus.json stays in place."""
import datetime, json, os, sys, time, urllib.error, urllib.request

BASE = "https://public-api.cardnexus.com/v1"
TOKEN = os.environ.get("CARDNEXUS_TOKEN", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLEEP = 1.2
CM_KEYS = ("low", "marketValue", "change24h", "change7d", "change30d", "date")
TCG_KEYS = ("low", "mid", "high", "marketValue", "change24h", "change7d", "change30d", "date")


class RateLimited(Exception):
    pass


def load(name, default):
    p = os.path.join(ROOT, name)
    try:
        return json.load(open(p))
    except Exception:
        return default


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited()
        return e.code, None
    except Exception:
        return 0, None


def pick(d, keys):
    return {k: d.get(k) for k in keys if isinstance(d, dict) and k in d}


def main():
    if not TOKEN:
        sys.exit("CARDNEXUS_TOKEN is not set")
    tracked = load("tracked.json", {})
    ids = load("cardnexus_ids.json", {})
    prev = load("cardnexus.json", {})
    items = dict(prev.get("items", {}))
    errors = 0
    limited = False
    finish_of = {lid: v.get("finish") for lid, v in items.items()}  # ledgerId -> finish for that TCGplayer id
    for lid, m in (ids.get("_manual") or {}).items():   # manual mappings carry their own finish
        finish_of.setdefault(lid, m.get("finish"))
    exclude = set(ids.get("_exclude") or [])      # ledger ids whose CardNexus link is known to be wrong
    for lid in exclude:
        ids.pop(lid, None)
        items.pop(lid, None)
    unmatched = []

    try:
        # 1. resolve CardNexus ids for anything not cached (batched by TCGplayer id, 200 per call)
        need = {lid: t["productId"] for lid, t in tracked.items() if lid not in ids and lid not in exclude}
        by_tcg = {}
        for lid, pid in need.items():
            by_tcg.setdefault(int(pid), []).append(lid)
        tcg_ids = sorted(by_tcg)
        found = {}  # tcg id -> (cnId, finish)
        search_ok = False
        for i in range(0, len(tcg_ids), 200):
            chunk = tcg_ids[i:i + 200]
            offset = 0
            while True:
                st, j = call("POST", "/products/search", {"tcgplayerId": chunk, "limit": 200, "offset": offset})
                time.sleep(SLEEP)
                if st != 200 or not isinstance(j, dict):
                    errors += 1
                    break
                search_ok = True
                for p in j.get("data", []):
                    for e in (p.get("externalIds") or {}).get("tcgplayer", []) or []:
                        tid = e.get("id")
                        if tid in chunk and tid not in found:
                            found[tid] = (p["id"], e.get("finish"))
                pg = j.get("pagination") or {}
                if not pg.get("hasMore"):
                    break
                offset += 200
        # batch lookups can miss ids (multi-page results); retry any id still missing on its own
        for tid in [t for t in tcg_ids if t not in found][:40]:
            st, j = call("POST", "/products/search", {"tcgplayerId": [tid], "limit": 10})
            time.sleep(SLEEP)
            if st != 200 or not isinstance(j, dict):
                errors += 1
                continue
            for p in sorted(j.get("data", []), key=lambda x: x["id"]):
                hit = next((e for e in (p.get("externalIds") or {}).get("tcgplayer", []) or [] if e.get("id") == tid), None)
                if hit:
                    found[tid] = (p["id"], hit.get("finish"))
                    break
        if not search_ok and tcg_ids:
            print("CardNexus API unavailable; keeping previous cardnexus.json")
            return
        for tid, lids in by_tcg.items():
            for lid in lids:
                if tid in found:
                    ids[lid] = found[tid][0]
                    finish_of[lid] = found[tid][1]
                else:
                    unmatched.append(lid)
        unmatched += sorted(exclude)
        json.dump(ids, open(os.path.join(ROOT, "cardnexus_ids.json"), "w"), indent=1, sort_keys=True)

        # 2. CardNexus stopped returning Cardmarket/TCGplayer prices on 2026-10-29; its /prices now gives only its own
        #    marketplace listings. So: (a) keep those as 'cnx' (lowest asking, NM English, by region: a buy source, never a value);
        #    (b) take Cardmarket's own free daily price guide for real Cardmarket prices, matched through the
        #    Cardmarket id CardNexus lists for each product (cached in cardnexus_ids.json under _cm).
        cmids = ids.setdefault("_cm", {})
        matched = [lid for lid in tracked if lid in ids]
        for lid in [l for l in matched if l not in cmids][:600]:
            st, j = call("GET", f"/products/{ids[lid]}")
            time.sleep(SLEEP)
            if st != 200 or not isinstance(j, dict): errors += 1; continue
            cms = (j.get("externalIds") or {}).get("cardmarket") or []
            fin = finish_of.get(lid)
            hit = next((c for c in cms if c.get("finish") == fin), cms[0] if cms else None)
            cmids[lid] = [hit["id"], hit.get("finish")] if hit else None
        guide = {}
        try:
            with urllib.request.urlopen("https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json", timeout=120) as r:
                guide = {g["idProduct"]: g for g in json.loads(r.read())["priceGuides"]}
        except Exception as e:
            print("Cardmarket price guide unavailable:", repr(e)[:120])
        fx = (load("cardmarket_jumbo.json", {}) or {}).get("fx") or 1.10   # USD per EUR, from the jumbo Cardmarket feed
        def eur(v): return round(v * fx, 2) if isinstance(v, (int, float)) and v else None
        for lid in matched:
            cn = ids[lid]
            st, j = call("GET", f"/products/{cn}/prices")
            time.sleep(SLEEP)
            if st != 200 or not isinstance(j, dict):
                errors += 1
                continue
            pbf = j.get("pricesByFinish") or {}
            fin = finish_of.get(lid)
            if fin not in pbf:
                fin = "Standard" if "Standard" in pbf else next(iter(pbf), None)
            blk = (pbf.get(fin) or {}).get("cardnexus") or {}
            cnx = {}
            for reg, r in (blk.get("regions") or {}).items():
                nm = ((r.get("byCondition") or {}).get("NM") or {})
                en = (nm.get("byLanguage") or {}).get("en") or {}
                if en.get("low"): cnx[reg] = {"low": en["low"], "cur": r.get("currency"), "n": en.get("listingCount")}
            cm = {}
            c = cmids.get(lid)
            g = guide.get(c[0]) if c else None
            if g:
                rev = lid.endswith("-rev")
                k = (lambda n: n + "-holo") if rev else (lambda n: n)
                t, a7, a30, lo = g.get(k("trend")), g.get(k("avg7")), g.get(k("avg30")), g.get(k("low"))
                if t:
                    cm = {"marketValue": eur(t), "low": eur(lo), "avg7": eur(a7), "avg30": eur(a30), "trendEUR": t,
                          "change7d": round(a7 / a30 - 1, 4) if a7 and a30 else None, "src": "Cardmarket price guide", "fx": fx}
            items[lid] = {"cnId": cn, "finish": fin, "cm": cm, "tcg": {}, "cnx": cnx}
    except RateLimited:
        limited = True
        unmatched = unmatched or prev.get("unmatched", [])

    out = {"generated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
           "currency": {"cm": "USD (converted from Cardmarket EUR)", "cnx": "as listed"},
           "note": "cm = Cardmarket daily price guide (trend, avg7, avg30, low), converted to USD; tcg is empty since CardNexus dropped it on 2026-10-29; cnx = lowest CardNexus marketplace listing (NM, English) by region, an asking price",
           "items": items, "unmatched": sorted(unmatched)}
    if limited:
        out["partial"] = True
    json.dump(out, open(os.path.join(ROOT, "cardnexus.json"), "w"), indent=1)
    print(f"cardmarket priced: {sum(1 for v in items.values() if v.get('cm'))}, cnx listings: {sum(1 for v in items.values() if v.get('cnx'))}")
    print(f"cardnexus: {len([l for l in tracked if l in items])} priced / {len(tracked)} tracked, "
          f"{len(unmatched)} unmatched, {errors} errors" + (", stopped on 429" if limited else ""))


if __name__ == "__main__":
    main()
