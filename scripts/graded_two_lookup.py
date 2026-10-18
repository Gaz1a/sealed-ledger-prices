"""Read-only lookup: (1) Flareon 065/SV-P (Yu Nagaba x Pokemon Card Game promo, 2023, Japanese) and (2) Pikachu VMAX TG29/TG30 (Lost Origin Trainer Gallery, SWSH11, English).
Finds TCGplayer product ids in tcgcsv, pulls PokemonPriceTracker v2 includeEbay for each candidate, and tries PriceCharting (tcg-id match first). Never prints keys."""
import json, os, re, time, urllib.request, urllib.parse, urllib.error
KEY, PCT = os.environ.get("PPT_KEY", ""), os.environ.get("PRICECHARTING_TOKEN", "")
def get(u, h=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sealed-ledger/1.0", **(h or {})}), timeout=60) as r: return json.load(r)
    except urllib.error.HTTPError as e: return {"error": e.code, "results": []}
    except Exception as e: return {"error": type(e).__name__, "results": []}
out = {"tcg": {"flareon": [], "pikachu": []}, "ppt": {}, "pc": {}}
for cat in (85, 3):
    for g in get(f"https://tcgcsv.com/tcgplayer/{cat}/groups")["results"]:
        n = g["name"]; fl = cat == 85 and re.search(r"promo|nagaba|sv-?p", n, re.I); pk = cat == 3 and re.search(r"lost origin|swsh ?11|trainer gallery", n, re.I)
        if not (fl or pk): continue
        pr = {}
        for r in get(f"https://tcgcsv.com/tcgplayer/{cat}/{g['groupId']}/prices")["results"]: pr.setdefault(r["productId"], []).append([r.get("subTypeName"), r.get("marketPrice")])
        for p in get(f"https://tcgcsv.com/tcgplayer/{cat}/{g['groupId']}/products")["results"]:
            ext = {e["name"]: e.get("value") for e in p.get("extendedData", [])}
            nm = p["name"]
            if fl and re.search(r"flareon", nm, re.I) and re.search(r"065|nagaba", nm + str(ext.get("Number")), re.I) or pk and re.search(r"pikachu vmax", nm, re.I) and re.search(r"TG\s?29|29/30", nm + str(ext.get("Number")), re.I):
                out["tcg"]["flareon" if fl else "pikachu"].append({"cat": cat, "group": n, "groupId": g["groupId"], "pid": p["productId"], "name": nm, "number": ext.get("Number"), "rarity": ext.get("Rarity"), "prices": pr.get(p["productId"], [])})
def finds(o, path=""):
    """locate lists of dicts that look like individual sales"""
    res = []
    if isinstance(o, dict):
        for k, v in o.items(): res += finds(v, path + "/" + k)
    elif isinstance(o, list) and o and isinstance(o[0], dict) and any(x in o[0] for x in ("soldDate", "date", "endDate", "saleDate")):
        res.append((path, o))
    return res
for key in ("flareon", "pikachu"):
    for c in out["tcg"][key]:
        j = get(f"https://www.pokemonpricetracker.com/api/v2/cards?tcgPlayerId={c['pid']}&includeEbay=true&limit=1", {"Authorization": f"Bearer {KEY}"}) if KEY else {"error": "no key"}
        time.sleep(1.3)
        d = j.get("data", j)
        if isinstance(d, list): d = d[0] if d else {}
        eb = (d.get("ebay") or {}) if isinstance(d, dict) else {}
        sbg = eb.get("salesByGrade") or {}
        out["ppt"][str(c["pid"])] = {"error": j.get("error"), "pptName": d.get("name") if isinstance(d, dict) else None, "pptSet": d.get("setName") if isinstance(d, dict) else None,
            "pptNumber": d.get("cardNumber") if isinstance(d, dict) else None, "pptRarity": d.get("rarity") if isinstance(d, dict) else None, "pptTcgPlayerId": d.get("tcgPlayerId") if isinstance(d, dict) else None,
            "ebayKeys": list(eb.keys()), "salesByGrade": {k: sbg[k] for k in sbg if re.sub(r"[^a-z0-9]", "", k.lower()) in ("psa10", "psa9", "ungraded", "raw")},
            "gradeKeys": list(sbg.keys()), "saleLists": {p: l[:12] for p, l in finds(eb)}}
    if PCT:
        for q in (("pokemon japanese flareon 065 sv-p", "pokemon flareon yu nagaba") if key == "flareon" else ("pokemon pikachu vmax tg29", "pokemon lost origin pikachu vmax tg29")):
            time.sleep(1.2)
            j = get("https://www.pricecharting.com/api/products?" + urllib.parse.urlencode({"t": PCT, "q": q}))
            out["pc"].setdefault(key, {})[q] = [{"id": x.get("id"), "name": x.get("product-name"), "console": x.get("console-name"), "tcgId": x.get("tcg-id"), "ungraded": x.get("loose-price"), "psa10": x.get("manual-only-price"), "psa9": x.get("graded-price")} for x in (j.get("products") or [])[:8]]
json.dump(out, open("graded_two_lookup.json", "w"), indent=1)
print({k: len(v) for k, v in out["tcg"].items()}, list(out["ppt"]))
