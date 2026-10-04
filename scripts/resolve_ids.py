#!/usr/bin/env python3
import json, urllib.request, time, os
BASE="https://tcgcsv.com/tcgplayer"
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WANT={
 "h-fpic2":["first partner","series 2"],
 "h-greninja":["greninja","premium collection"],
 "h-lumiose":["mini tin"],
 "h-moonlit":["moonlit","tin"],
 "h-cr-box":["chaos rising","booster box"],
 "h-po-box":["pitch black","booster box"],
 "h-pb-box":["booster box"],
 "ah-etb":["elite trainer box"],
}
def get(u):
    for i in range(4):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"sealed-ledger-prices/1.0"}),timeout=30))
        except Exception:
            if i==3: return None
            time.sleep(2)
groups=sorted(get(f"{BASE}/3/groups")["results"],key=lambda g:g.get("publishedOn",""),reverse=True)[:12]
out={k:[] for k in WANT}
for g in groups:
    prods=(get(f"{BASE}/3/{g['groupId']}/products") or {}).get("results",[])
    pr={}
    for r in (get(f"{BASE}/3/{g['groupId']}/prices") or {}).get("results",[]): pr.setdefault(r["productId"],r.get("marketPrice"))
    for k,w in WANT.items():
        for p in prods:
            if all(x in p["name"].lower() for x in w):
                out[k].append({"set":g["name"],"productId":p["productId"],"name":p["name"],"market":pr.get(p["productId"])})
    time.sleep(.2)
json.dump(out,open(os.path.join(ROOT,"resolve_candidates.json"),"w"),indent=1)
print({k:len(v) for k,v in out.items()})
