import re, urllib.request, json
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36","Accept":"text/html,application/json,*/*"}
def get(u,data=None,h=None):
    hd=dict(UA); hd.update(h or {})
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,data=data,headers=hd),timeout=40); return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: return e.code, e.read().decode("utf-8","replace")[:600]
    except Exception as e: return str(e)[:200], ""
out=[]
g=json.load(open("goldin_sold.json"))["lots"][:1]+json.load(open("goldin.json"))["wants"][:1]
for x in g:
    slug=x["url"].rsplit("/",1)[1]
    st,b=get("https://lot-retrieval-bidder.api.prod.goldin.com/api/meta_slug/"+slug,h={"Origin":"https://goldin.co","Referer":"https://goldin.co/"})
    out.append(f"GOLDIN view {slug[:40]} {st} {b[:1500]}")
for u in ["https://www.ha.com/c/search/results.zx?term=pokemon+booster+box&mode=live",
          "https://www.ha.com/c/search/results.zx?N=790+231+4294944414&type=surl-trading-card-games",
          "https://www.fanaticscollect.com/weekly-auction?q=pokemon",
          "https://www.fanaticscollect.com/",
          "https://sales-history-api.fanaticscollect.com/"]:
    st,b=get(u)
    apis=sorted(set(re.findall(r'https?://[a-zA-Z0-9.-]*(?:api|graphql)[a-zA-Z0-9./_-]*',b)))[:25]
    out.append(f"== {u} -> {st} len {len(b)} title {re.search(r'<title>(.*?)</title>',b,re.S).group(1)[:80] if '<title>' in b else ''} apis {apis}\n   {b[:300]!r}")
    for src in re.findall(r'src="([^"]+\.js[^"]*)"',b)[:12]:
        su=src if src.startswith("http") else re.match(r'https?://[^/]+',u).group(0)+src
        s2,js=get(su)
        m=sorted(set(re.findall(r'https?://[a-zA-Z0-9.-]*(?:api|graphql|algolia|search)[a-zA-Z0-9./_-]*',js)))[:20]
        if m: out.append(f"   js {src[-50:]}: {m}")
open("auction_probe.txt","w").write("\n".join(out))
