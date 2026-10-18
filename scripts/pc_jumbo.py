#!/usr/bin/env python3
"""PriceCharting step for the Jumbo list -> pricecharting.json['jumbo'] (by ledger id; sealed / card parts).
Scope = jumbo_pc_scope.csv (Jumbo entries that have a TCGplayer sealedId/cardId but no current TCGplayer market). Skips anything without ids.
Method 1: PriceCharting product search, accept the product whose tcg-id equals the TCGplayer id.
Method 2 (only if 1 finds nothing): search '<box name> Pokemon'; accept ONE candidate only if the box/jumbo variant (not a regular card / other collection),
  the language fits, the set fits (TCGplayer group vs PriceCharting console, when the group is a real set) and the year fits (release-date within +-1 year when PriceCharting gives one).
Official paid API, 1 call/sec. Prices come back in cents (stored as USD). Internal use only; unverified estimates. Never prints the token."""
import csv, json, os, re, sys, time, datetime, urllib.request, urllib.parse, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN, API, TODAY = os.environ.get("PRICECHARTING_TOKEN", ""), "https://www.pricecharting.com/api", datetime.date.today().isoformat()
SLEEP, CAP = 1.1, 450
calls = 0
class Stop(Exception): pass
def ld(p, d):
    try: return json.load(open(os.path.join(ROOT, p)))
    except Exception: return d
def api(path, **q):
    global calls
    if calls >= CAP: raise Stop("call cap")
    q["t"] = TOKEN; calls += 1; time.sleep(SLEEP)
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{API}/{path}?" + urllib.parse.urlencode(q), headers={"User-Agent": "sealed-ledger/1.0"}), timeout=40) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code in (429, 403): raise Stop(f"HTTP {e.code}")
        return None
    except Exception: return None
    return j if isinstance(j, dict) and j.get("status", "success") == "success" else None
def usd(v): return round(v / 100, 2) if isinstance(v, (int, float)) and v else None
def toks(s): return set(re.findall(r"[a-z0-9]+", (s or "").lower())) - {"pokemon", "the", "of", "and", "card", "cards"}
def shape(p, method, how):
    return {"matched": True, "matchMethod": method, "detail": how, "ungraded": usd(p.get("loose-price")), "salesVolumeYearly": p.get("sales-volume"), "pcId": int(p["id"]),
            "productName": p.get("product-name"), "console": p.get("console-name"), "releaseDate": p.get("release-date"), "tcgId": p.get("tcg-id"), "asOf": TODAY,
            "label": "PriceCharting estimate (unverified; ungraded/sealed = loose-price)"}
GENERIC_GROUP = re.compile(r"jumbo|promo|miscellaneous|^$", re.I)
def tcg_groups(pids):
    """productId -> TCGplayer group name (category 3), stops once all needed pids are found."""
    need, found = set(pids), {}
    def g(u):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sealed-ledger/1.0"}), timeout=60) as r: return json.load(r)
        except Exception: return {"results": []}
    for grp in g("https://tcgcsv.com/tcgplayer/3/groups")["results"]:
        if not need: break
        for p in g(f"https://tcgcsv.com/tcgplayer/3/{grp['groupId']}/products")["results"]:
            if p["productId"] in need: found[p["productId"]] = grp["name"]; need.discard(p["productId"])
    return found
LANG = {"English": None, "French": "french", "Portuguese": "portuguese", "Japanese": "japan", "Korean": "korea", "German": "german", "Italian": "italian", "Spanish": "spanish"}
def accept(p, row, kind, qname, grp):
    name, con = p.get("product-name", ""), p.get("console-name", "")
    low = (name + " " + con).lower()
    if re.search(r"\bcase\b|\blot\b|bundle", low): return "case/lot"
    lang = LANG.get(row["language"])
    if lang is None and re.search(r"japan|korea|chinese|french|german|italian|spanish|portuguese", con, re.I): return "language"
    if lang and lang not in con.lower(): return "language"
    if kind == "card":
        if not re.search(r"jumbo|oversize", low): return "not a jumbo card"
    else:
        if re.search(r"#\d|\b\d{1,3}/\d{2,3}\b", name): return "regular card"
        if not toks(qname) <= toks(name + " " + con): return "name tokens"
    if kind == "card" and not toks(qname) <= toks(name + " " + con): return "name tokens"
    if grp and not GENERIC_GROUP.search(grp):
        gt = toks(grp) - {"sm", "xy", "bw", "sv", "swsh", "hgss", "dp", "ex", "set", "base"}
        if gt and not (gt & toks(con)): return "set"
    rd = p.get("release-date") or ""
    if rd[:4].isdigit() and abs(int(rd[:4]) - int(row["year"])) > 1: return "year"
    return None
def main():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "jumbo_pc_scope.csv"), encoding="utf-8")))
    rows = [r for r in rows if r.get("ledger id") and str(r.get("TCGplayer id", "")).strip().isdigit()]
    rows = [{"jid": r["ledger id"], "box": r["box"], "kind": r["which part"], "language": r["language"], "year": r["year"], "tcg": int(r["TCGplayer id"]),
             "q": urllib.parse.parse_qs(urllib.parse.urlparse(r["PriceCharting search"]).query).get("q", [""])[0]} for r in rows]
    groups = {}
    try: groups = tcg_groups({r["tcg"] for r in rows})
    except Exception as e: print("group lookup failed", type(e).__name__)
    prev = ld("pricecharting.json", {}); old = (prev.get("jumbo") or {}).get("items", {})
    items, stats, stopped = {}, {"scope": len(rows), "matched": 0, "unmatched": 0, "tcgIdMatches": 0, "nameMatches": 0}, None
    for r in rows:
        if stopped: break
        kind, grp = r["kind"], groups.get(r["tcg"])
        qname = r["box"] if kind == "sealed" else r["q"].replace("jumbo", "").strip()
        res, cands = None, []
        try:
            q1 = f"pokemon {qname}" + (" jumbo" if kind == "card" else "")
            j1 = (api("products", q=q1) or {}).get("products") or []
            for p in j1:
                if str(p.get("tcg-id") or "") == str(r["tcg"]): res = shape(p, "tcg-id", f"tcg-id {r['tcg']} in search '{q1}'"); break
            if not res:
                q2 = f"{qname} Pokemon" + (" jumbo" if kind == "card" else "")
                j2 = (api("products", q=q2) or {}).get("products") or []
                seen, ok = set(), []
                for p in j1 + j2:
                    if p["id"] in seen: continue
                    seen.add(p["id"]); why = accept(p, r, kind, qname, grp)
                    if why is None: ok.append(p)
                    else: cands.append({"pcId": p["id"], "productName": p.get("product-name"), "console": p.get("console-name"), "releaseDate": p.get("release-date"), "ungraded": usd(p.get("loose-price")), "rejected": why})
                if len(ok) == 1: res = shape(ok[0], "name+set+year", f"search '{q2}'; set {grp or 'n/a'}; year {r['year']}; release-date {ok[0].get('release-date') or 'n/a'}")
                elif len(ok) > 1: cands = [{"pcId": p["id"], "productName": p.get("product-name"), "console": p.get("console-name"), "releaseDate": p.get("release-date"), "ungraded": usd(p.get("loose-price")), "rejected": "ambiguous"} for p in ok] + cands
        except Stop as e: stopped = str(e); res = None
        ent = res or {"matched": False, "reason": "no tcg-id match; no single set/year/variant-fit candidate" if not stopped else f"stopped: {stopped}", "candidates": cands[:5], "tcgId": r["tcg"], "tcgGroup": grp, "asOf": TODAY}
        if res: ent["tcgGroup"] = grp
        ent.update({"box": r["box"], "language": r["language"], "year": r["year"], "tcgplayerId": r["tcg"]})
        items.setdefault(r["jid"], {})[kind] = ent
        stats["matched" if ent["matched"] else "unmatched"] += 1
        if ent["matched"]: stats["tcgIdMatches" if ent["matchMethod"] == "tcg-id" else "nameMatches"] += 1
        json.dump(dict(prev, jumbo={"generated": TODAY, "partial": True, "items": items}), open(os.path.join(ROOT, "pricecharting.json"), "w"), indent=1, ensure_ascii=False)
    stats["apiCalls"] = calls
    out = dict(prev); out["jumbo"] = {"generated": TODAY, "partial": bool(stopped), "stopped": stopped, "units": "USD (API returns cents; converted /100)", "scope": "jumbo_pc_scope.csv (entries with a TCGplayer id but no current TCGplayer market; entries with no ids skipped)",
        "note": "PriceCharting estimates, unverified. ungraded = loose-price (sealed price for sealed products). Data licensed for internal use only.", "stats": stats, "items": items}
    json.dump(out, open(os.path.join(ROOT, "pricecharting.json"), "w"), indent=1, ensure_ascii=False)
    print(json.dumps(stats), "| stopped:", stopped)
if __name__ == "__main__": main()
