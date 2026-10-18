#!/usr/bin/env python3
"""Jumbo catalogue scan. Resolves TCGplayer productIds by EXACT normalized name only (never guesses), then appends today's tcgcsv marketPrice to per-product history.
Inputs: jumbo_catalogue.json (+ jumbo_ids.json for resolutions kept/confirmed). Outputs: jumbo_ids.json, jumbo_prices.json.
Prices are tcgcsv marketPrice (TCGplayer market), NOT verified against sold listings."""
import json, os, re, sys, time, datetime, unicodedata, urllib.request
TODAY = datetime.datetime.utcnow().strftime("%Y-%m-%d")
def get(u):
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sealed-ledger/1.0"}), timeout=60) as r: return json.load(r)
        except Exception: time.sleep(2)
    return {}
def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ").replace("pokemon", "").replace("—", " ").replace("–", " ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()
def ld(p, d):
    return json.load(open(p)) if os.path.exists(p) else d
cat = json.load(open("jumbo_catalogue.json"))
ids = ld("jumbo_ids.json", {})
prices = ld("jumbo_prices.json", {"items": {}})
tracked = ld("tracked.json", {})
# pre-fill the held items from tracked.json (already confirmed productIds)
HELD = {"j-2025-charizard-ex-special-collection-en": "zard-special-collection", "j-2026-mega-greninja-ex-premium-collection-en": "h-greninja"}
sealed_idx, card_idx, price_idx, name_of = {}, {}, {}, {}
for c in (3, 85):
    for g in get(f"https://tcgcsv.com/tcgplayer/{c}/groups").get("results", []):
        ps = get(f"https://tcgcsv.com/tcgplayer/{c}/{g['groupId']}/products").get("results", [])
        if not ps: continue
        for r in get(f"https://tcgcsv.com/tcgplayer/{c}/{g['groupId']}/prices").get("results", []):
            price_idx.setdefault(r["productId"], []).append(r)
        for p in ps:
            num = next((e.get("value") for e in p.get("extendedData", []) if e.get("name") == "Number"), None)
            rec = {"productId": p["productId"], "name": p["name"], "group": g["name"], "cat": c, "number": num}
            name_of[p["productId"]] = rec
            if g["name"] == "Jumbo Cards":
                base = re.sub(r"\s+-\s+[A-Za-z0-9/]+(\s*\(.*\))?$", "", p["name"])
                card_idx.setdefault(norm(base), []).append(rec)
            elif not num and not p["name"].lower().startswith("code card"):
                sealed_idx.setdefault(norm(p["name"]), []).append(rec)
def one_card(s):
    parts = [x.strip() for x in re.split(r";|,| & | and ", s or "") if x.strip()]
    return parts[0] if len(parts) == 1 else None
def pick_price(pid):
    rows = [r for r in price_idx.get(pid, []) if r.get("marketPrice") is not None]
    if not rows: return None
    if len(rows) == 1: return rows[0]
    for pref in ("Normal", "Holofoil"):
        m = [r for r in rows if r["subTypeName"] == pref]
        if m: return m[0]
    return None
for j in cat:
    jid = j["id"]; st = ids.setdefault(jid, {"title": j["title"], "lang": j["lang"], "sealedId": None, "sealedBasis": None, "cardId": None, "cardBasis": None})
    if j["id"] in HELD and not st["sealedId"] and HELD[j["id"]] in tracked:
        st["sealedId"], st["sealedBasis"] = tracked[HELD[j["id"]]]["productId"], "tracked.json (held)"
    if not st["sealedId"] and not st.get("sealedIds"):
        cands = sealed_idx.get(norm(j["title"]), [])
        st["sealedCandidates"] = [{k: c[k] for k in ("productId", "name", "group")} for c in cands][:6]
        if len(cands) == 1: st["sealedId"], st["sealedBasis"] = cands[0]["productId"], "exact-name"
    if not st["cardId"] and not st.get("cardIds") and not st.get("cardClosed"):
        one = one_card(j["cards"])
        if one:
            cands = card_idx.get(norm(one), [])
            st["cardCandidates"] = [{**{k: c[k] for k in ("productId", "name", "number")}, "market": (pick_price(c["productId"]) or {}).get("marketPrice")} for c in cands][:8]
            if len(cands) == 1: st["cardId"], st["cardBasis"] = cands[0]["productId"], "unique-name-in-Jumbo-Cards (confirm print)"
        else:
            st["cardNote"] = "multiple/unspecified jumbo cards in sheet"
    it = prices["items"].setdefault(jid, {"title": j["title"]})
    for kind, pid in (("sealed", st["sealedId"]), ("card", st["cardId"])):
        if not pid: it.pop(kind, None); continue
        e = it.setdefault(kind, {"productId": pid, "history": []})
        e["productId"] = pid
        r = pick_price(pid)
        e["name"] = name_of.get(pid, {}).get("name")
        e["source"] = "tcgcsv marketPrice (TCGplayer market; not sold-verified)"
        if r:
            e.update({"market": r["marketPrice"], "low": r.get("lowPrice"), "subType": r["subTypeName"], "date": TODAY})
            if not e["history"] or e["history"][-1][0] != TODAY: e["history"].append([TODAY, r["marketPrice"]])
        else:
            e.update({"market": None, "date": TODAY, "note": "no priced row today"})
    for _k, _ik, _mk in (("card", "cardIds", "cardMode"), ("sealed", "sealedIds", "sealedMode")):
        if not st.get(_ik): it.pop(_k + "Set", None); continue
        its = []
        for pid in st[_ik]:
            r = pick_price(pid)
            its.append({"productId": pid, "name": name_of.get(pid, {}).get("name"), "market": (r or {}).get("marketPrice"), "subType": (r or {}).get("subTypeName")})
        ms = [x["market"] for x in its if x["market"] is not None]
        it[_k + "Set"] = {"mode": st.get(_mk) or "separate", "items": its, "byId": {str(x["productId"]): x for x in its}, "low": min(ms) if ms else None, "high": max(ms) if ms else None,
                         "sum": round(sum(ms), 2) if ms and len(ms) == len(its) and st.get(_mk) == "components" else None,
                         "date": TODAY, "source": "tcgcsv marketPrice (TCGplayer market; not sold-verified)"}
json.dump(ids, open("jumbo_ids.json", "w"), indent=1)
json.dump({"generated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "items": prices["items"]}, open("jumbo_prices.json", "w"), indent=1)
print("sealed resolved", sum(1 for v in ids.values() if v["sealedId"]), "card resolved", sum(1 for v in ids.values() if v["cardId"]), "of", len(ids))
