#!/usr/bin/env python3
import json, urllib.request, time, datetime, os, re
BASE="https://tcgcsv.com/tcgplayer/3"
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def get(u):
    for i in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"sealed-ledger-prices/1.0"}),timeout=30))
        except Exception as e:
            if i==3: raise
            time.sleep(2*(i+1))
groups=get(f"{BASE}/groups")["results"]
g=[x for x in groups if re.search(r"(^|[: ])151$",x["name"].strip()) and "japan" not in x["name"].lower()]
assert g, "151 group not found"
gid=g[0]["groupId"]
prods=get(f"{BASE}/{gid}/products")["results"]
prices=get(f"{BASE}/{gid}/prices")["results"]
num={}
for p in prods:
    n=next((e["value"] for e in p.get("extendedData",[]) if e["name"]=="Number"),None)
    if n: num[p["productId"]]=(n,p["name"])
best={};rev={}
for r in prices:
    pid=r["productId"]
    if pid not in num or r.get("marketPrice") is None: continue
    n=num[pid][0]
    if r["subTypeName"]=="Reverse Holofoil": rev[n]=max(rev.get(n,0),r["marketPrice"])
    else: best[n]=max(best.get(n,0),r["marketPrice"])
nums={n for n,_ in num.values()}
missing=sorted(n for n in nums if n not in best and n not in rev)
out={"generated":datetime.datetime.utcnow().isoformat()+"Z","groupId":gid,"groupName":g[0]["name"],
 "cards":len(nums),"priced":len(best),"missing":missing,
 "base_total":round(sum(best.values()),2),"reverse_total":round(sum(rev.values()),2),
 "market":round(sum(best.values())+sum(rev.values()),2),
 "top10":sorted(([num[p][1],best.get(num[p][0])] for p in num if best.get(num[p][0])),key=lambda x:-x[1])[:10]}
json.dump(out,open(os.path.join(ROOT,"master151.json"),"w"),indent=1)
print(out["groupName"],out["cards"],"cards, total",out["market"],"missing",len(missing))
