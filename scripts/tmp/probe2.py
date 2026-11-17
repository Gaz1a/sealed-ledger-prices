import json,os,urllib.request,urllib.parse
K=os.environ["JOTFORM_API_KEY"]
b=urllib.parse.urlencode({"question[hidden]":"No"}).encode()
try:
    r=json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.jotform.com/form/263147084103046/question/2?apiKey={K}",data=b),timeout=30))
    print("unhide", r.get("responseCode"), r.get("message"))
except Exception as e: print("unhide failed", e)
q=json.load(urllib.request.urlopen(f"https://api.jotform.com/form/263147084103046/questions?apiKey={K}"))["content"]
print({k:(v.get("text"),v.get("hidden")) for k,v in q.items() if k in ("2","3","6")})
