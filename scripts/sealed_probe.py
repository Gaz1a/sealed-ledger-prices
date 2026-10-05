import json, os, urllib.request, urllib.error, urllib.parse

KEY = os.environ["PPT_KEY"]
BASE = "https://www.pokemonpricetracker.com/api/v2"
BOXES = {565250: "Paradigm Trigger BB", 565236: "Ruler of the Black Flame BB", 565248: "Triple Beat BB"}

def get(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KEY}", "User-Agent": "sealed-ledger"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:300]}
    except Exception as e:
        return 0, {"error": str(e)[:300]}

def keys(o, depth=0):
    if isinstance(o, dict) and depth < 3:
        return {k: keys(v, depth + 1) for k, v in list(o.items())[:25]}
    if isinstance(o, list):
        return [keys(o[0], depth + 1)] if o else []
    return type(o).__name__

out = {}
for pid, label in BOXES.items():
    tries = {
        "cards_ebay": f"{BASE}/cards?tcgPlayerId={pid}&includeEbay=true&limit=1",
        "sealed_ebay": f"{BASE}/sealed-products?tcgPlayerId={pid}&includeEbay=true&limit=1",
        "sealed_ebay_b": f"{BASE}/sealed?tcgPlayerId={pid}&includeEbay=true&limit=1",
        "sealed_search": f"{BASE}/sealed-products?search={urllib.parse.quote(label.replace(' BB',''))}&includeEbay=true&limit=1",
    }
    res = {}
    for name, url in tries.items():
        st, body = get(url)
        txt = json.dumps(body)
        res[name] = {"status": st, "has_ebay": "ebay" in txt.lower(), "has_sales": "sale" in txt.lower(),
                     "shape": keys(body), "sample": txt[:600]}
        print(pid, label, name, st, "ebay" if res[name]["has_ebay"] else "-", "sales" if res[name]["has_sales"] else "-")
    out[str(pid)] = {"label": label, "tries": res}
json.dump(out, open("sealed_probe.json", "w"), indent=1)
