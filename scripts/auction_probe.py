import re, urllib.request, urllib.parse, json
UA={"User-Agent":"Mozilla/5.0","Accept":"*/*","Origin":"https://www.fanaticscollect.com","Referer":"https://www.fanaticscollect.com/","Content-Type":"application/json"}
def get(u,data=None,h=None):
    hd=dict(UA); hd.update(h or {})
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,data=data,headers=hd),timeout=40); return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: return e.code, e.read().decode("utf-8","replace")[:800]
st,b=get("https://www.fanaticscollect.com/weekly-auction?q=pokemon",h={"Accept":"text/html"})
env={}
for s in sorted(set(re.findall(r'(/_next/static/chunks/[^"\' ]+\.js)',b))):
    _,js=get("https://www.fanaticscollect.com"+s)
    for k in ["NEXT_PUBLIC_ALGOLIA_APP_ID","NEXT_PUBLIC_ALGOLIA_API_KEY"]:
        m=re.search(k+r':"([^"]+)"',js)
        if m: env[k]=m.group(1)
    if len(env)==2: break
app,key=env["NEXT_PUBLIC_ALGOLIA_APP_ID"],env["NEXT_PUBLIC_ALGOLIA_API_KEY"]
H={"x-algolia-application-id":app,"x-algolia-api-key":key}
U=f"https://{app}-dsn.algolia.net/1/indexes/*/queries"
out=[]
def q(params):
    st,r=get(U,json.dumps({"requests":[{"indexName":"prod_item_state_v1","params":params}]}).encode(),H); return json.loads(r)["results"][0] if st==200 else {"err":r}
r=q("query=&hitsPerPage=0&facets=%5B%22status%22%2C%22marketplace%22%2C%22subCategory1%22%2C%22categoryParent%22%5D&filters="+urllib.parse.quote('category:"Pokémon"'))
out.append("facets "+json.dumps(r.get("facets"))[:2500]+" nb "+str(r.get("nbHits")))
r=q("query=booster%20box&hitsPerPage=2&filters="+urllib.parse.quote('category:"Pokémon" AND status:"Live"'))
out.append("live nb "+str(r.get("nbHits")))
for h in r.get("hits",[])[:1]: out.append(json.dumps({k:v for k,v in h.items() if k not in ("images","_highlightResult")})[:2500])
open("auction_probe.txt","w").write("\n".join(out))
