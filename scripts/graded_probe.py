#!/usr/bin/env python3
"""Probe: what does PPT return for graded (eBay sold) prices? Writes graded_probe.json."""
import json, os, sys, time, urllib.request, urllib.error
KEY=os.environ.get("PPT_KEY","")
if not KEY: sys.exit("PPT_KEY secret missing")
API="https://www.pokemonpricetracker.com/api/v2/cards"
TCG="https://tcgcsv.com/tcgplayer/3"
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if os.path.basename(os.path.dirname(os.path.abspath(__file__)))=="scripts" else os.path.dirname(os.path.abspath(__file__))
def getj(u,hdr=None):
    for i in range(3):
        try:
            r=urllib.request.urlopen(urllib.request.Request(u,headers=hdr or {"User-Agent":"sealed-ledger-prices/1.0"}),timeout=40)
            return r.status,dict(r.headers),json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code==429 and i<2: time.sleep(int(e.headers.get("Retry-After") or 20)); continue
            return e.code,dict(e.headers),e.read().decode()[:300]
        except Exception as e:
            if i==2: return 0,{},str(e)
            time.sleep(2)
cards={
 "Mega Greninja ex SIR 116/086":693517,"Mewtwo 10/102 holo":42347,"Chansey 3/102 holo":42371,
 "Pidgeot 8/64 holo":45134,"Vaporeon 12/64 holo":45123,"Victreebel 14/64 holo":45125,"Hitmonlee 7/62 holo":106523,
 "Mew ex FR 158/128":696688,"Mewtwo ex FR 157/128":696687}
want={"199":"Charizard ex","200":"Blastoise ex","198":"Venusaur ex","168":"Charmander","170":"Squirtle","202":"Zapdos ex","173":"Pikachu","201":"Alakazam ex","166":"Bulbasaur","203":"Erika's Invitation","205":"Mew ex"}
st,_,g=getj(f"{TCG}/groups")
gid=next(x["groupId"] for x in g["results"] if x["name"].strip().endswith("151") and "japan" not in x["name"].lower())
st,_,pr=getj(f"{TCG}/{gid}/products")
for p in pr["results"]:
    n=next((e["value"] for e in p.get("extendedData",[]) if e["name"]=="Number"),"")
    if "/165" in n and n.split("/")[0].lstrip("0") in want and want[n.split("/")[0].lstrip("0")].split()[0] in p["name"]:
        cards[f"151 {p['name']}"]=p["productId"]
out={"generated":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"cards":{}}
for name,pid in cards.items():
    st,hdr,d=getj(f"{API}?tcgPlayerId={pid}&includeEbay=true&limit=1",{"Authorization":f"Bearer {KEY}","User-Agent":"sealed-ledger-prices/1.0"})
    rl={k:v for k,v in hdr.items() if any(s in k.lower() for s in ("credit","ratelimit","remaining","limit"))}
    row={"productId":pid,"status":st,"limits":rl}
    if isinstance(d,dict):
        dd=d.get("data")
        c=dd[0] if isinstance(dd,list) and dd else (dd if isinstance(dd,dict) else d)
        row["dataType"]=type(dd).__name__
        if isinstance(c,dict):
            row["topKeys"]=sorted(c.keys())
            row["ebay"]=json.dumps(c.get("ebay"))[:6000] if c.get("ebay") is not None else None
            row["rawPrices"]=json.dumps(c.get("prices"))[:600]
        row["meta"]={k:d[k] for k in d if k not in ("data",)}
    else: row["error"]=str(d)
    out["cards"][name]=row
    print(name,st,"ebay" if row.get("ebay") else "no-ebay",rl)
    time.sleep(1.2)
json.dump(out,open(os.path.join(ROOT,"graded_probe.json"),"w"),indent=1)
