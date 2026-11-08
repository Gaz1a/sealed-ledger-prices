import re, urllib.request, json
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
def get(u,data=None,h=None):
    hd=dict(UA); hd.update(h or {})
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,data=data,headers=hd),timeout=60); return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: return e.code, e.read().decode("utf-8","replace")[:500]
    except Exception as e: return str(e), ""
out=[]
s,h=get("https://goldin.co/buy?search=pokemon")
src=[x for x in re.findall(r'src="([^"]+\.js[^"]*)"',h) if "index-" in x][0]
_,js=get("https://goldin.co"+src)
for key in ["lots_v2","searchalgolia","lot-retrieval-bidder","getAlgoliaSearchData","/api/auctions"]:
    for m in list(re.finditer(re.escape(key),js))[:4]:
        out.append(f"== {key} @{m.start()}: "+js[max(0,m.start()-700):m.start()+700].replace("\n"," "))
open("goldin_probe.txt","w").write("\n".join(out))
