"""Read-only: PriceCharting candidates for JP Venusaur 065/128 (Base Expansion Pack e-Card, 1st Ed) and Birthday Pikachu #24 (Celebrations Classic Collection). Never prints the token."""
import json, os, re, time, urllib.request, urllib.parse
T = os.environ.get("PRICECHARTING_TOKEN", ""); API = "https://www.pricecharting.com/api"
def api(path, **q):
    time.sleep(1.1); q["t"] = T
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{API}/{path}?" + urllib.parse.urlencode(q), headers={"User-Agent": "sealed-ledger/1.0"}), timeout=40) as r: return json.load(r)
    except Exception as e: return {"error": type(e).__name__}
Q = {"venusaur": ["venusaur 65 japanese expedition", "venusaur 1st edition japanese e-card", "pokemon japanese base expansion pack venusaur", "venusaur 065/128", "pokemon japanese expedition venusaur"],
     "pikachu": ["pikachu birthday classic collection", "birthday pikachu 24 celebrations", "pokemon celebrations classic collection pikachu", "birthday pikachu #24"]}
out = {"hits": {}, "detail": {}}
ids = set()
for k, qs in Q.items():
    for q in qs:
        d = api("products", q=q)
        out["hits"][q] = [{"id": x.get("id"), "name": x.get("product-name"), "console": x.get("console-name")} for x in (d.get("products") or [])[:12]]
        for x in (d.get("products") or [])[:12]:
            n = (x.get("product-name") or "") + " " + (x.get("console-name") or "")
            if (k == "venusaur" and re.search(r"venusaur", n, re.I) and re.search(r"expedition|e-?card|expansion|base", n, re.I)) or (k == "pikachu" and re.search(r"birthday", n, re.I) and re.search(r"celebrations|classic|promo", n, re.I)):
                ids.add(x["id"])
for i in sorted(ids)[:14]:
    d = api("product", id=i)
    out["detail"][str(i)] = {k: v for k, v in d.items() if k in ("id", "product-name", "console-name", "release-date", "genre", "sales-volume", "tcg-id") or k.endswith("-price") or k.endswith("-sell-volume")}
json.dump(out, open("pc_graded_lookup.json", "w"), indent=1)
print(len(ids))
