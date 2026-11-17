import json,os,urllib.request
K=os.environ["JOTFORM_API_KEY"]
s=json.load(urllib.request.urlopen(f"https://api.jotform.com/form/263147084103046/submissions?apiKey={K}&limit=4&orderby=created_at&direction=DESC"))["content"]
for x in s:
    print(x["id"],x["created_at"],{k:(v.get("text"),str(v.get("answer"))[:150]) for k,v in x["answers"].items() if v.get("answer")})
q=json.load(urllib.request.urlopen(f"https://api.jotform.com/form/263147084103046/questions?apiKey={K}"))["content"]
print({k:(v.get("text"),v.get("type"),v.get("hidden")) for k,v in q.items()})
