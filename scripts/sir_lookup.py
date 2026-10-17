"""Read-only: find TCGplayer ids for 30th Celebration SIRs (Jirachi/Sylveon), Moonlit, One Piece OP17 MR, Rayquaza Delta Reign."""
import json, re, urllib.request
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sealed-ledger/1.0"}), timeout=60) as r: return json.load(r)
    except Exception as e: return {"error": str(e)[:80], "results": []}
out = {"groups": [], "hits": []}
want = [(3, r"30th|celebration|delta reign|mega evolution|moonlit|pitch black|ascended"), (68, r"op-?17|world.s strongest|warriors")]
for cat, rx in want:
    for g in get(f"https://tcgcsv.com/tcgplayer/{cat}/groups")["results"]:
        if not re.search(rx, g["name"], re.I): continue
        out["groups"].append([cat, g["groupId"], g["name"], g.get("publishedOn")])
        ps = get(f"https://tcgcsv.com/tcgplayer/{cat}/{g['groupId']}/products")["results"]
        pr = {}
        for r in get(f"https://tcgcsv.com/tcgplayer/{cat}/{g['groupId']}/prices")["results"]:
            pr.setdefault(r["productId"], []).append([r.get("subTypeName"), r.get("marketPrice"), r.get("lowPrice")])
        for p in ps:
            n = p["name"]
            ext = {e["name"]: e.get("value") for e in p.get("extendedData", [])}
            ok = (cat == 3 and re.search(r"jirachi|sylveon|rayquaza|moonlit", n, re.I) and re.search(r"30th|celebration|delta|mega evolution|moonlit", g["name"], re.I)) or \
                 (cat == 68 and (re.search(r"manga|\bMR\b|secret|alternate", n + str(ext.get("Rarity")), re.I)))
            if ok: out["hits"].append({"cat": cat, "group": g["name"], "gid": g["groupId"], "pid": p["productId"], "name": n, "number": ext.get("Number"), "rarity": ext.get("Rarity"), "prices": pr.get(p["productId"], [])})
json.dump(out, open("sir_lookup.json", "w"), indent=1)
print(len(out["groups"]), len(out["hits"]))
