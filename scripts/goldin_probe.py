import re, urllib.request, json
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36","Origin":"https://goldin.co","Referer":"https://goldin.co/"}
def get(u,data=None,h=None):
    hd=dict(UA); hd.update(h or {})
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,data=data,headers=hd),timeout=60); return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: return e.code, e.read().decode("utf-8","replace")[:800]
    except Exception as e: return str(e), ""
out=[]
s,h=get("https://goldin.co/buy?search=pokemon")
src=[x for x in re.findall(r'src="([^"]+\.js[^"]*)"',h) if "index-" in x][0]
_,js=get("https://goldin.co"+src)
for key in ["mapFacetsToAlgoliaSearchParams=","mapFacetsToAlgoliaSearchParams=function","header:{"]:
    for m in list(re.finditer(re.escape(key),js))[:2]:
        out.append(f"== {key} @{m.start()}: "+js[max(0,m.start()-300):m.start()+3500].replace("\n"," "))
m=re.search(r'const \w+=\(\w+,\w+\)=>\{[^}]{0,200}queryType',js)
U="https://d1wu47wucybvr3.cloudfront.net/api/lots_v2"
for p in [{"search":{"queryType":"Featured","keyword":"pokemon","from":0,"size":5}},
          {"queryType":"Featured","keyword":"pokemon","from":0,"size":5},
          {"search":{"query":"pokemon","size":5,"from":0,"queryType":"Ending_Soonest"}}]:
    st,b=get(U,json.dumps(p).encode(),{"Content-Type":"application/json"})
    out.append(f"POST {json.dumps(p)} -> {st} {b[:1500]}")
open("goldin_probe.txt","w").write("\n".join(out))
