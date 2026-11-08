import re, urllib.request, json
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36","Accept":"text/html,*/*"}
def get(u):
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=40); return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: return e.code, ""
out=[]
for u in ["https://www.fanaticscollect.com/weekly-auction?q=pokemon%20booster%20box","https://www.fanaticscollect.com/weekly-auction?category=Trading+Card+Games+%3E+Pok%C3%A9mon+(English)"]:
    st,b=get(u)
    out.append(f"== {u} {st} {len(b)}")
    for k in ["Booster Box","currentBid","current_bid","highBid","bidCount","endsAt","listingId","slug","graphql","algolia","x-algolia","typesense","apiKey"]:
        ms=[m.start() for m in re.finditer(re.escape(k),b)][:2]
        for i in ms: out.append(f"  [{k}] "+b[max(0,i-250):i+350].replace("\n"," "))
open("auction_probe.txt","w").write("\n".join(out))
