"""Shape check: what /products/{id}/prices returns now (CardNexus prices went empty on 2026-10-29). No token printed."""
import json, os, sys, urllib.request, urllib.error
BASE = "https://public-api.cardnexus.com/v1"; TOKEN = os.environ.get("CARDNEXUS_TOKEN", "")
if not TOKEN: sys.exit("CARDNEXUS_TOKEN is not set")
def call(m, path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None, method=m)
    req.add_header("Authorization", "Bearer " + TOKEN); req.add_header("Accept", "application/json")
    if body: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, e.read().decode()[:500]
ids = json.load(open("cardnexus_ids.json"))
out = {}
for lid in ["pe-etb", "k-149", "s-darkrai-sir"]:
    cn = ids.get(lid)
    st, j = call("GET", f"/products/{cn}/prices")
    out[lid] = {"cn": cn, "status": st, "body": j if isinstance(j, str) else json.loads(json.dumps(j)[:3000] if len(json.dumps(j)) < 3000 else json.dumps({k: (str(v)[:600]) for k, v in j.items()}))}
st, j = call("GET", "/products/" + str(ids.get("pe-etb")))
out["product"] = {"status": st, "keys": list(j.keys()) if isinstance(j, dict) else str(j)[:300], "sample": str(j)[:1500]}
json.dump(out, open("cardnexus_probe.json", "w"), indent=1)
print(json.dumps(out)[:4000])
