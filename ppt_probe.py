import json, os, sys, urllib.request, urllib.error
KEY = os.environ.get("PPT_KEY", "")
if not KEY:
    sys.exit("PPT_KEY secret missing")
tracked = json.load(open("tracked.json"))
items = tracked if isinstance(tracked, list) else list(tracked.values())
want = ("booster box", "elite trainer", "collection", "tin", "etb")
picked = [t for t in items if any(w in (t.get("title","")).lower() for w in want) and t.get("productId")][:5]
BASE = "https://www.pokemonpricetracker.com/api/v2/sealed-products"
def call(pid, hdr):
    req = urllib.request.Request(f"{BASE}?tcgPlayerId={pid}&includeHistory=true&days=30", headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()[:2500]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
for t in picked:
    print("=====", t.get("title"), t["productId"])
    for name, hdr in (("bearer", {"Authorization": f"Bearer {KEY}"}), ("x-api-key", {"X-API-Key": KEY})):
        code, body = call(t["productId"], hdr)
        print(f"[{name}] HTTP {code}\n{body}\n")
        if code == 200:
            break
