import re, urllib.request, json
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36","Accept":"text/html,*/*"}
def get(u):
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=40); return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: return e.code, ""
st,b=get("https://www.fanaticscollect.com/weekly-auction?q=pokemon")
out=[]
for s in sorted(set(re.findall(r'(/_next/static/chunks/[^"\' ]+\.js)',b))):
    _,js=get("https://www.fanaticscollect.com"+s)
    for m in re.finditer(r'["`/](?:items|listing|weekly-auction|lot)/\$\{[^`"]{0,120}', js):
        out.append(s[-15:]+": "+js[max(0,m.start()-150):m.start()+200].replace("\n"," "))
for u in ["https://www.fanaticscollect.com/weekly-auction/bf1ac76a-d288-11f1-ac7a-0affdda36b9d","https://www.fanaticscollect.com/items/bf1ac76a-d288-11f1-ac7a-0affdda36b9d/WEEKLY","https://www.fanaticscollect.com/items/bf1ac76a-d288-11f1-ac7a-0affdda36b9d"]:
    st,b=get(u); t=re.search(r'<title>(.*?)</title>',b,re.S); out.insert(0,f"{u} -> {st} {t.group(1)[:120] if t else ''}")
open("auction_probe.txt","w").write("\n".join(out[:25]))
