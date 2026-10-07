import gzip, json, os, sys, urllib.request, urllib.error

BASE = "https://public-api.cardnexus.com/v1"
TOKEN = os.environ.get("CARDNEXUS_TOKEN", "")
if not TOKEN:
    sys.exit("CARDNEXUS_TOKEN is not set")

OUT = {}


def call(method, url, body=None, auth=True):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if auth:
        req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, repr(e).encode()


def jcall(method, url, body=None):
    s, b = call(method, url, body)
    t = b.decode("utf-8", "replace")
    try:
        return s, json.loads(t), t
    except Exception:
        return s, None, t


def show(label, status, text, n=2000):
    print(f"\n=== {label} -> {status}")
    print(text[:n])
    OUT[label] = {"status": status, "body": text[:12000]}


def items_of(j):
    if isinstance(j, list):
        return j
    if isinstance(j, dict):
        for k in ("data", "items", "results", "products"):
            if isinstance(j.get(k), list):
                return j[k]
        return next((v for v in j.values() if isinstance(v, list)), [])
    return []


def names(items, n=10):
    return [(i.get("id"), i.get("name"), (i.get("game") or {}).get("id"),
             (i.get("expansion") or {}).get("name"), i.get("productType")) for i in items[:n]]


# --- games: find the Pokemon game id
s, j, t = jcall("GET", BASE + "/games")
games = items_of(j)
poke = [g for g in games if "pok" in json.dumps(g).lower()]
print("games:", s, len(games), "| pokemon-like:", [(g.get("id"), g.get("name")) for g in poke])
OUT["games_pokemon"] = poke
GAME = (poke[0].get("id") if poke else "pokemon")

SEALED = {"op": "or", "values": ["sealed"]}
found = {}


def search(label, body, must=None):
    s, j, t = jcall("POST", BASE + "/products/search", body)
    items = items_of(j) if j is not None else []
    hit = [i for i in items if must and must.lower() in (i.get("name") or "").lower()]
    print(f"\n=== {label} {json.dumps(body)} -> {s}; {len(items)} results; name-matching: {len(hit)}")
    for row in names(items, 10):
        print("  ", row)
    OUT[label] = {"status": s, "body": body, "count": len(items), "matches": len(hit),
                  "first10": names(items, 10), "raw": t[:6000]}
    return items, hit


# 1. by name
items, hit = search("name: Super Electric Breaker",
                    {"name": "Super Electric Breaker", "productType": SEALED}, "Super Electric Breaker")
for h in hit:
    found[h["id"]] = h.get("name")

# 2. by tcgplayerId
items2, _ = search("tcgplayerId 587728", {"tcgplayerId": [587728]})
for h in items2:
    found[h["id"]] = h.get("name")
if items2:
    print("tcgplayerId result keys:", sorted(items2[0].keys()))
    print(json.dumps(items2[0])[:1500])

# 3. illustrated booklet / half deck
for q in ("Illustrated Booklet", "Half Deck"):
    its, hits = search("name: " + q, {"name": q, "productType": SEALED}, q)
    OUT["first10 " + q] = names(its, 10)

# 4. prices for real matches
for pid, nm in list(found.items())[:5]:
    s, j, t = jcall("GET", f"{BASE}/products/{pid}/prices")
    show(f"prices {pid} {nm}", s, t, 6000)

# per-game feed
s, j, t = jcall("GET", f"{BASE}/feeds/{GAME}/prices")
show(f"feeds/{GAME}/prices (metadata)", s, t, 1500)
if isinstance(j, dict) and j.get("url"):
    fs, raw = call("GET", j["url"], auth=False)
    print(f"\nfeed download -> {fs}; gzip bytes: {len(raw)}")
    try:
        txt = gzip.decompress(raw).decode("utf-8", "replace")
        print("decompressed chars:", len(txt), "| lines:", txt.count("\n"))
        print(txt[:1000])
        OUT["feed"] = {"status": fs, "gzip_bytes": len(raw), "chars": len(txt),
                       "lines": txt.count("\n"), "first1000": txt[:1000]}
    except Exception as e:
        print("could not gunzip:", repr(e)[:200])
        OUT["feed"] = {"status": fs, "gzip_bytes": len(raw), "error": repr(e)[:200]}

with open("cardnexus_probe.json", "w") as f:
    json.dump(OUT, f, indent=1)
print("\ndone")
