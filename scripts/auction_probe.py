import re, urllib.request, json
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36","Accept":"*/*","Origin":"https://www.fanaticscollect.com","Referer":"https://www.fanaticscollect.com/"}
def get(u,data=None,h=None):
    hd=dict(UA); hd.update(h or {})
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,data=data,headers=hd),timeout=40); return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: return e.code, e.read().decode("utf-8","replace")[:800]
    except Exception as e: return str(e), ""
out=[]
st,b=get("https://www.fanaticscollect.com/weekly-auction?q=pokemon")
srcs=sorted(set(re.findall(r'(/_next/static/chunks/[^"\' ]+\.js)',b)))
env={}
for s in srcs:
    _,js=get("https://www.fanaticscollect.com"+s)
    for k in ["NEXT_PUBLIC_ALGOLIA_APP_ID","NEXT_PUBLIC_ALGOLIA_API_KEY","NEXT_PUBLIC_SEARCH_API_URL","NEXT_PUBLIC_FAN_SEARCH_URL","NEXT_PUBLIC_API_KEY"]:
        m=re.search(k+r':"([^"]+)"',js)
        if m: env[k]=m.group(1)
    for m in re.finditer(r'SEARCH_API_URL\}?[^;]{0,300}', js):
        if "fetch" in m.group(0) or "/" in m.group(0)[20:]: out.append("use: "+m.group(0)[:300])
out.append("env keys: "+", ".join(f"{k}={'set' if v else ''} len{len(v)}" for k,v in env.items()))
app=env.get("NEXT_PUBLIC_ALGOLIA_APP_ID"); key=env.get("NEXT_PUBLIC_ALGOLIA_API_KEY"); su=env.get("NEXT_PUBLIC_SEARCH_API_URL")
body=json.dumps({"requests":[{"indexName":"prod_item_state_v1","params":"query=pokemon%20booster%20box&hitsPerPage=3"}]}).encode()
h={"Content-Type":"application/json"}
if app: h.update({"x-algolia-application-id":app,"x-algolia-api-key":key})
for base in [su, f"https://{app}-dsn.algolia.net" if app else None]:
    if not base: continue
    for path in ["/1/indexes/*/queries"]:
        st,r=get(base.rstrip("/")+path,body,h)
        out.append(f"{base}{path} -> {st} {r[:1800]}")
open("auction_probe.txt","w").write("\n".join(out))
