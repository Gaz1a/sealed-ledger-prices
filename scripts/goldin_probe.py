import re, urllib.request, json
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=60) as r: return r.status, r.read().decode("utf-8","replace")
    except Exception as e: return str(e), ""
out=[]
s,h=get("https://goldin.co/buy?search=pokemon")
out.append(f"buy status {s} len {len(h)}")
srcs=sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"',h)))
out.append("scripts: "+" ".join(srcs[:40]))
for m in re.findall(r'https?://[a-zA-Z0-9.-]*(?:api|algolia|search)[a-zA-Z0-9./_-]*',h)[:30]: out.append("html url "+m)
nd=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',h,re.S)
if nd: out.append("NEXT_DATA "+nd.group(1)[:1500])
pat=re.compile(r'(algolia[^"\'`]{0,80}|[A-Z0-9]{10}-dsn|x-algolia[^"\'`]{0,60}|https?://[a-zA-Z0-9.-]*goldin[a-zA-Z0-9./_-]*|/api/[a-zA-Z0-9/_-]{3,60}|apiKey["\']?\s*[:=]\s*["\'][^"\']{8,60})')
seen=set()
for src in srcs:
    u=src if src.startswith("http") else "https://goldin.co"+src
    st,js=get(u)
    for m in pat.findall(js):
        if m not in seen: seen.add(m); out.append(f"{src.split('/')[-1][:30]}: {m}")
open("goldin_probe.txt","w").write("\n".join(out[:400]))
