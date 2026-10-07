#!/usr/bin/env python3
"""PriceCharting cross-reference -> pricecharting.json. Uses only the official paid API (/api/products, /api/product),
1 call/sec as the docs require. Data is for the owner's internal use only (PriceCharting licence). Never prints the token.
Prices come back in cents; stored here in USD."""
import json, os, re, sys, time, datetime, urllib.request, urllib.parse, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_market as sm

TOKEN = os.environ.get("PRICECHARTING_TOKEN", "")
API = "https://www.pricecharting.com/api"
ROOT, TODAY = sm.ROOT, datetime.date.today().isoformat()
SLEEP, CALL_CAP = 1.1, 1500
FIELDS = {  # PriceCharting trading-card field -> meaning (docs); verified by mappingCheck below
    "loose-price": "ungraded", "cib-price": "psa7", "new-price": "psa8", "graded-price": "psa9",
    "box-only-price": "psa9_5", "manual-only-price": "psa10"}
calls = 0

class Stop(Exception): pass

def load(p, d):
    try: return json.load(open(os.path.join(ROOT, p)))
    except Exception: return d

def api(path, **q):
    global calls
    if calls >= CALL_CAP: raise Stop("call cap")
    q["t"] = TOKEN
    url = f"{API}/{path}?" + urllib.parse.urlencode(q)
    calls += 1; time.sleep(SLEEP)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "sealed-ledger/1.0"}), timeout=40) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code in (429, 403): raise Stop(f"HTTP {e.code}")
        return None
    except Exception:
        return None
    return j if isinstance(j, dict) and j.get("status", "success") == "success" else None

def usd(v): return round(v / 100, 2) if isinstance(v, (int, float)) and v else None

def shape(p):
    out = {n: usd(p.get(k)) for k, n in FIELDS.items()}
    out.update({"salesVolumeYearly": p.get("sales-volume"), "pcId": int(p["id"]), "productName": p.get("product-name"),
                "console": p.get("console-name"), "tcgId": p.get("tcg-id")})
    return out

def edition(text):
    t = (text or "").lower()
    return "1st" if "1st edition" in t else "shadowless" if "shadowless" in t else "unlimited"

def toks(s): return set(re.findall(r"[a-z0-9]+", (s or "").lower())) - {"pokemon", "the", "of", "and", "ex", "card"}

def resolve(q, pid, number=None, want_ed=None, require_tokens=None, jp=False):
    """Return (product, how) or (None, reason). A match is accepted only on an exact tcg-id, or on number + name tokens."""
    j = api("products", q=q)
    prods = (j or {}).get("products") or []
    for p in prods:
        if str(p.get("tcg-id") or "") == str(pid): return p, "tcg-id"
    cands = []
    for p in prods:
        name, con = p.get("product-name", ""), p.get("console-name", "")
        if jp and "japan" not in con.lower(): continue
        if number and not re.search(r"#?\b0*" + re.escape(str(number).split("/")[0].lstrip("0") or "0") + r"\b", name): continue
        if require_tokens and not require_tokens <= toks(name + " " + con): continue
        cands.append(p)
    if want_ed:
        same = [p for p in cands if edition(p.get("console-name", "") + " " + p.get("product-name", "")) == want_ed]
        cands = same or cands
    if len(cands) == 1: return cands[0], "name"
    return None, "ambiguous" if cands else "none"

def main():
    if not TOKEN: sys.exit("PRICECHARTING_TOKEN is not set")
    tracked, prices = load("tracked.json", {}), load("prices.json", {}).get("prices", {})
    graded = load("graded.json", {}).get("cards", {})
    idc = load("pricecharting_ids.json", {})
    prev = load("pricecharting.json", {})
    out = {"cards": dict(prev.get("cards", {})), "sealed": dict(prev.get("sealed", {})), "japan": dict(prev.get("japan", {}))}
    notes = {"errors": [], "stopped": None}
    sealed_re = re.compile(sm.SEALED_WORDS.pattern, re.I)
    def is_sealed_title(t): return bool(sealed_re.search(t or "")) and not re.search(r"\d+/\d+|\bTG\d|\b#\d", t or "")

    # mapping self-check against the website (Base Set Charizard #4 showed ungraded $446.29 / Grade 9 $3,309.38 / PSA 10 $24,077.50)
    check = {}
    try:
        p, how = resolve("pokemon base set charizard 4", None, number="4", want_ed="unlimited", require_tokens={"charizard", "base", "set"})
        if p:
            s = shape(p)
            site = {"ungraded": 446.29, "psa9": 3309.38, "psa10": 24077.50}
            check = {"card": p.get("product-name"), "console": p.get("console-name"), "api": {k: s[k] for k in site}, "site_snapshot": site,
                     "ratio": {k: (round(s[k] / site[k], 2) if s[k] else None) for k in site}}
            check["mappingConfirmed"] = all(r and 0.5 < r < 2 for r in check["ratio"].values())
    except Stop as e: notes["stopped"] = str(e)

    # ---- cards: graded.json + tracked singles
    jobs = []
    for cid, c in graded.items():
        jobs.append((cid, c.get("name"), c.get("productId")))
    for lid, t in tracked.items():
        if not is_sealed_title(t.get("title")) and lid not in graded: jobs.append((lid, t.get("title"), t["productId"]))
    sg = {c["productId"]: c for c in load("untracked_singles.json", {}).get("cards", [])}
    try:
        for cid, name, pid in jobs:
            rec = out["cards"].get(cid, {})
            sgc = sg.get(pid, {})
            number = (sgc.get("number") or "") or (re.search(r"(\d+)/\d+", name or "") or [None, None])[1]
            clean = re.sub(r"\(.*?\)|\[.*?\]|—.*$|holo|rare|reverse", "", name or "", flags=re.I)
            clean = re.sub(r"\s+\d+/\d+|\s+-\s*$", "", clean).strip()
            want_ed = edition(name)
            setname = (sgc.get("set") or "") or ((re.search(r"\((.*?)\)", name or "") or [None, ""])[1])
            if cid in idc and idc[cid].get("pcId"):
                j = api("product", id=idc[cid]["pcId"]); p, how = (j, idc[cid]["how"]) if j else (None, "refresh-failed")
            else:
                q = f"pokemon {re.sub(r'^[A-Za-z0-9]+: ', '', setname)} {clean} {number or ''}".strip()
                p, how = resolve(q, pid, number=number, want_ed=want_ed, require_tokens=toks(clean))
                if not p and setname:
                    p, how = resolve(f"pokemon {clean} {number or ''}", pid, number=number, want_ed=want_ed, require_tokens=toks(clean))
            if not p:
                rec = dict(rec, matched=False, reason=how, name=name, productId=pid, asOf=TODAY); out["cards"][cid] = rec; continue
            s = shape(p); idc[cid] = {"pcId": s["pcId"], "how": how}
            ed_pc = edition(s["console"] + " " + (s["productName"] or ""))
            ed_ok = True if how == "tcg-id" else (ed_pc == want_ed)
            out["cards"][cid] = dict(s, matched=True, how=how, name=name, productId=pid, wantedEdition=want_ed, pcEdition=ed_pc,
                                     editionMatched=ed_ok, asOf=TODAY)
    except Stop as e: notes["stopped"] = str(e)

    # ---- sealed cross-check (tracked sealed + Japan sealed from the audit)
    try:
        for lid, t in tracked.items():
            if not is_sealed_title(t.get("title")): continue
            title, pid = t["title"], t["productId"]; key = "sealed:" + lid
            if key in idc and idc[key].get("pcId"):
                j = api("product", id=idc[key]["pcId"]); p, how = (j, idc[key]["how"]) if j else (None, "refresh-failed")
            else:
                p, how = resolve(f"pokemon {title}", pid, require_tokens=toks(title) - {"box"} if len(toks(title)) > 3 else toks(title))
            if not p: out["sealed"][lid] = {"matched": False, "reason": how, "title": title, "productId": pid, "asOf": TODAY}; continue
            s = shape(p); idc[key] = {"pcId": s["pcId"], "how": how}
            tcg = (prices.get(lid) or {}).get("market")
            pcp = s["ungraded"]            # PriceCharting lists the sealed price under loose-price for sealed Pokemon products
            out["sealed"][lid] = dict(s, matched=True, how=how, title=title, productId=pid, pcSealed=pcp, tcgMarket=tcg,
                                      diffPct=(round((pcp / tcg - 1) * 100, 1) if pcp and tcg else None), asOf=TODAY)
        # Japan: sealed boxes for every JP set in the audit, plus top-2 cards of recent JP sets from tcgcsv category 85
        aud = load("untracked_sealed.json", {})
        for e in aud.get("coverage", []):
            if e.get("category") != "Pokemon JP": continue
            for b in (e["boosterBox"] if isinstance(e["boosterBox"], list) else [])[:1]:
                key = f"jp-box:{b['productId']}"
                if key in idc and idc[key].get("pcId"):
                    j = api("product", id=idc[key]["pcId"]); p, how = (j, idc[key]["how"]) if j else (None, "refresh-failed")
                else:
                    nm = re.sub(r"^[A-Za-z0-9\-]+:\s*", "", e["set"])
                    p, how = resolve(f"pokemon japanese {nm} booster box", b["productId"], jp=True, require_tokens=toks(nm) | {"booster", "box"})
                if p:
                    s = shape(p); idc[key] = {"pcId": s["pcId"], "how": how}
                    out["japan"][key] = dict(s, kind="booster box", set=e["set"], tcgProductId=b["productId"], tcgMarket=b["market"],
                                             diffPct=(round((s["ungraded"] / b["market"] - 1) * 100, 1) if s["ungraded"] and b["market"] else None), how=how, asOf=TODAY)
                else:
                    out["japan"][key] = {"matched": False, "reason": how, "kind": "booster box", "set": e["set"], "tcgProductId": b["productId"], "asOf": TODAY}
        groups = [g for g in (sm.get(f"{sm.BASE}/85/groups") or {}).get("results", []) if (g.get("publishedOn") or "")[:10] >= "2024-01-01"]
        groups.sort(key=lambda g: g.get("publishedOn") or "", reverse=True)
        for g in groups[:20]:
            prods = sm.get(f"{sm.BASE}/85/{g['groupId']}/products"); pr = sm.get(f"{sm.BASE}/85/{g['groupId']}/prices")
            if not prods or not pr: continue
            info = {p["productId"]: p for p in prods.get("results", []) if any(x.get("name") == "Number" for x in p.get("extendedData") or [])}
            best = sorted([r for r in pr.get("results", []) if r["productId"] in info and r.get("marketPrice")], key=lambda r: -r["marketPrice"])[:2]
            for r in best:
                p0 = info[r["productId"]]; num = next(x["value"] for x in p0["extendedData"] if x["name"] == "Number")
                key = f"jp-card:{r['productId']}"
                nm = re.sub(r"\s*-\s*\S+/\S+$", "", p0["name"]).strip()
                if key in idc and idc[key].get("pcId"):
                    j = api("product", id=idc[key]["pcId"]); p, how = (j, idc[key]["how"]) if j else (None, "refresh-failed")
                else:
                    p, how = resolve(f"pokemon japanese {nm} {num}", r["productId"], number=num, jp=True, require_tokens=toks(nm))
                if p:
                    s = shape(p); idc[key] = {"pcId": s["pcId"], "how": how}
                    out["japan"][key] = dict(s, kind="card", set=g["name"], name=p0["name"], number=num, tcgProductId=r["productId"],
                                             tcgMarket=r["marketPrice"], how=how, asOf=TODAY)
                else:
                    out["japan"][key] = {"matched": False, "reason": how, "kind": "card", "set": g["name"], "name": p0["name"], "tcgProductId": r["productId"], "asOf": TODAY}
    except Stop as e: notes["stopped"] = str(e)

    json.dump(idc, open(os.path.join(ROOT, "pricecharting_ids.json"), "w"), indent=1, sort_keys=True)
    cards = out["cards"]
    out.update({"generated": TODAY, "freshness": TODAY,
                "units": "USD (API returns cents; converted /100)",
                "fieldMapping": {k: v for k, v in FIELDS.items()}, "mappingCheck": check,
                "note": "Data licensed to the owner for internal use only; do not publish. PriceCharting API has current prices only (no sales history); salesVolumeYearly is units/yr.",
                "stats": {"cards": len(cards), "cardsMatched": sum(1 for c in cards.values() if c.get("matched")),
                          "editionMatched": sum(1 for c in cards.values() if c.get("editionMatched")),
                          "editionMismatch": sum(1 for c in cards.values() if c.get("editionMatched") is False),
                          "sealedMatched": sum(1 for c in out["sealed"].values() if c.get("matched")), "sealed": len(out["sealed"]),
                          "japanMatched": sum(1 for c in out["japan"].values() if c.get("matched", True) and c.get("pcId")), "japan": len(out["japan"]),
                          "apiCalls": calls}, "run": notes})
    json.dump(out, open(os.path.join(ROOT, "pricecharting.json"), "w"), indent=1, ensure_ascii=False)
    print(json.dumps(out["stats"]), "| stopped:", notes["stopped"], "| mappingConfirmed:", check.get("mappingConfirmed"))

if __name__ == "__main__":
    main()
