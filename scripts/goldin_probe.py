import re, urllib.request, json
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36","Origin":"https://goldin.co","Referer":"https://goldin.co/","Content-Type":"application/json"}
U="https://d1wu47wucybvr3.cloudfront.net/api/lots_v2"
def post(p):
    try:
        r=urllib.request.urlopen(urllib.request.Request(U,data=json.dumps({"search":p}).encode(),headers=UA),timeout=60); d=json.load(r)
    except urllib.error.HTTPError as e: return f"ERR {e.code} {e.read()[:200]}"
    s=d.get("searchalgolia") or {}
    return {"total":s.get("total"),"n":len(s.get("lots") or []),"keys":list(d)[:8],"first":[(l.get("title")[:70],l.get("status"),l.get("current_price"),l.get("end_timestamp")) for l in (s.get("lots") or [])[:3]],"facets":[(f.get("title"),[ (b.get("key"),b.get("doc_count")) for b in (f.get("buckets") or [])[:12]]) for f in (s.get("facets") or [])][:12],"lotkeys":sorted((s.get("lots") or [{}])[0].keys())}
out=[]
tests={"size100":{"queryType":"Featured","keyword":"pokemon","from":0,"size":100},
"from100":{"queryType":"Featured","keyword":"pokemon","from":100,"size":100},
"size500":{"queryType":"Featured","keyword":"pokemon","from":0,"size":500},
"soldSold":{"queryType":"Featured","keyword":"pokemon booster box","from":0,"size":5,"show_only":"Sold"},
"soldsold":{"queryType":"Featured","keyword":"pokemon booster box","from":0,"size":5,"show_only":"sold"},
"itemtype":{"queryType":"Featured","keyword":"pokemon","from":0,"size":5,"item_type":["Cases/Boxes/Packs"]},
"itemtype2":{"queryType":"Featured","keyword":"pokemon","from":0,"size":5,"Item_Type":["Cases/Boxes/Packs"]},
"box":{"queryType":"Ending_Soonest","keyword":"pokemon booster box","from":0,"size":20}}
for k,p in tests.items(): out.append(k+" "+json.dumps(post(p))[:2500])
open("goldin_probe.txt","w").write("\n".join(out))
