import re, urllib.request, json
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36","Accept":"*/*"}
def get(u,data=None,h=None):
    hd=dict(UA); hd.update(h or {})
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,data=data,headers=hd),timeout=40); return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: return e.code, e.read().decode("utf-8","replace")[:1500]
    except Exception as e: return str(e), ""
out=[]
st,b=get("https://www.fanaticscollect.com/weekly-auction?q=pokemon")
srcs=sorted(set(re.findall(r'(/_next/static/chunks/[^"\' ]+\.js)',b)))
for s in srcs:
    _,js=get("https://www.fanaticscollect.com"+s)
    for m in re.finditer(r'SEARCH_API_URL(?!:")|/v\d/search|indexName|multi_search|typesense', js):
        out.append(f"{s[-20:]} @{m.start()}: "+js[max(0,m.start()-500):m.start()+700].replace("\n"," "))
# public graphql search settings
q={"query":"query { collectSearchSetting(type: LISTING) { indexes { displayName indexName indexValue type } defaultFilter { indexName } } }"}
st,r=get("https://app.fanaticscollect.com/graphql",json.dumps(q).encode(),{"Content-Type":"application/json","Origin":"https://www.fanaticscollect.com"})
out.insert(0,f"GQL settings {st}: {r[:1500]}")
open("auction_probe.txt","w").write("\n\n".join(out[:30]))
