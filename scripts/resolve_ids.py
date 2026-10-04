#!/usr/bin/env python3
import json, urllib.request, time, os
BASE="https://tcgcsv.com/tcgplayer/3"
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WANT={
 "h-fpic2":["first partner","series 2"],
 "h-greninja":["greninja","premium collection"],
 "h-lumiose":["mini tin","lumiose"],
 "h-moonlit":["moonlit","tin"],
 "h-cr-box":["chaos rising","booster box"],
 "h-pb-box":["pitch black","booster box"],
 "h-po-box":["perfect order","booster box"],
 "ah-etb":["ascended heroes","elite trainer box"],
}
def get(u):
    for i in range(4):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"sealed-ledger-prices/1.0"}),timeout=30))
        except Exception:
            if i==3: return None
            time.sleep(2)
out={k:[] for k in WANT}; hit={}
for g in get(f"{BASE}/groups")["results"]:
    prods=(get(f"{BASE}/{g['groupId']}/products") or {}).get("results",[]); time.sleep(.15)
    for p in prods:
        s=(g["name"]+" "+p["name"]).lower()
        for k,w in WANT.items():
            if all(x in s for x in w):
                out[k].append({"set":g["name"],"groupId":g["groupId"],"productId":p["productId"],"name":p["name"]})
                hit.setdefault(g["groupId"],set()).add(p["productId"])
pr={}
for gid in hit:
    for r in (get(f"{BASE}/{gid}/prices") or {}).get("results",[]):
        if r["productId"] in hit[gid] and r.get("marketPrice") is not None: pr[r["productId"]]=r["marketPrice"]
for v in out.values():
    for m in v: m["market"]=pr.get(m["productId"])
json.dump(out,open(os.path.join(ROOT,"resolve_candidates.json"),"w"),indent=1)
print({k:len(v) for k,v in out.items()})
