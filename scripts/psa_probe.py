import os, json, urllib.request, urllib.error
T = os.environ.get("PSA_TOKEN", "")
print("token present:", bool(T), "length:", len(T))
for label, path in (("cert", "/cert/GetByCertNumber/12345678"), ("pop", "/pop/GetPSASpecPopulation/1")):
    for scheme in ("Bearer ", "bearer "):
        req = urllib.request.Request("https://api.psacard.com/publicapi" + path, headers={"Authorization": scheme + T, "Accept": "application/json", "User-Agent": "sealed-ledger/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r: print(label, scheme.strip(), r.status, r.read()[:300].decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            print(label, scheme.strip(), e.code, {k: v for k, v in e.headers.items() if k.lower() in ("server", "content-type", "www-authenticate", "retry-after", "x-ratelimit-remaining")}, e.read()[:400].decode("utf-8", "replace").replace(T, "<token>") if T else "")
        except Exception as e: print(label, "err", type(e).__name__)
