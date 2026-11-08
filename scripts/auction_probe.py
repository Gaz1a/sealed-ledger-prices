import re, urllib.request, json
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36","Accept":"text/html,*/*"}
def get(u):
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=40); return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: return e.code, ""
    except Exception as e: return str(e), ""
out=[]
st,b=get("https://www.fanaticscollect.com/weekly-auction?q=pokemon")
srcs=sorted(set(re.findall(r'(/_next/static/chunks/[^"\' ]+\.js)',b)))
out.append(f"{len(srcs)} chunks")
seen=set()
for s in srcs:
    _,js=get("https://www.fanaticscollect.com"+s)
    for m in re.findall(r'https?://[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9._/-]*)?',js):
        h=m.split('/')[2]
        if any(x in m for x in ("api","graphql","search","algolia","typesense","gql")) and m not in seen:
            seen.add(m); out.append(f"{s[-25:]}: {m}")
    for m in re.findall(r'(query [A-Za-z]+\([^)]{0,200}\)\s*\{[^}]{0,300})',js)[:3]:
        out.append(f"{s[-25:]} GQL: {m[:400]}")
open("auction_probe.txt","w").write("\n".join(out[:200]))
