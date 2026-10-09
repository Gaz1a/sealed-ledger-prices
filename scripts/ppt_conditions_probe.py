import json, os, urllib.request, urllib.error
K = os.environ["PPT_KEY"]
out = {}
for pid in (42382, 45122):
    for label, q in (("plain", ""), ("ebay", "&includeEbay=true"), ("history", "&includeHistory=true")):
        url = f"https://www.pokemonpricetracker.com/api/v2/cards?tcgPlayerId={pid}&limit=1{q}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": f"Bearer {K}"}), timeout=40) as r:
                j = json.load(r)
        except urllib.error.HTTPError as e: out[f"{pid}:{label}"] = {"error": e.code}; continue
        except Exception as e: out[f"{pid}:{label}"] = {"error": type(e).__name__}; continue
        d = j.get("data", j); d = d[0] if isinstance(d, list) and d else d
        def trim(o, depth=0):
            if isinstance(o, dict): return {k: trim(v, depth + 1) for k, v in list(o.items())[:30]} if depth < 4 else "{...}"
            if isinstance(o, list): return [trim(o[0], depth + 1), f"...{len(o)} items"] if o else []
            return o
        out[f"{pid}:{label}"] = {"keys": list(d.keys()) if isinstance(d, dict) else None, "prices": trim((d or {}).get("prices")), "extra": {k: trim(v) for k, v in (d or {}).items() if k in ("tcgplayer", "conditions", "listings", "ebay") and label != "ebay"}}
json.dump(out, open("ppt_conditions_probe.json", "w"), indent=1)
print("ok")
