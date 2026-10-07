import json, os, sys, urllib.request, urllib.error

BASE = "https://public-api.cardnexus.com/v1"
TOKEN = os.environ.get("CARDNEXUS_TOKEN", "")
if not TOKEN:
    sys.exit("CARDNEXUS_TOKEN is not set")

OUT = {}


def call(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, repr(e)


def show(label, status, text, n=1500):
    print(f"\n=== {label} -> {status}")
    print(text[:n])
    OUT[label] = {"status": status, "body": text[:20000]}


for u in [
    "https://public-api.cardnexus.com/openapi.json",
    "https://public-api.cardnexus.com/v1/openapi.json",
    "https://docs.cardnexus.com/openapi.json",
]:
    s, t = call("GET", u)
    show("openapi " + u, s, t, 300)
    if s == 200 and t.lstrip().startswith("{"):
        with open("cardnexus_openapi.json", "w") as f:
            f.write(t)
        break

QUERY = "Super Electric Breaker Booster Box"
shapes = [
    {"query": QUERY},
    {"q": QUERY},
    {"text": QUERY},
    {"search": QUERY},
    {"query": QUERY, "game": "pokemon"},
    {"name": QUERY},
]
found = None
for i, b in enumerate(shapes):
    s, t = call("POST", BASE + "/products/search", b)
    show(f"search shape {i} {json.dumps(b)}", s, t)
    if s == 200 and found is None:
        found = t
        break

pid = None
if found:
    try:
        j = json.loads(found)
        items = j if isinstance(j, list) else next(
            (v for v in j.values() if isinstance(v, list)), [])
        if items:
            first = items[0]
            pid = first.get("id") or first.get("productId")
            print("\nfirst result keys:", sorted(first.keys()))
    except Exception as e:
        print("could not parse search result:", e)

if pid:
    s, t = call("GET", f"{BASE}/products/{pid}/prices")
    show(f"prices {pid}", s, t, 2500)

with open("cardnexus_probe.json", "w") as f:
    json.dump(OUT, f, indent=1)
print("\ndone")
