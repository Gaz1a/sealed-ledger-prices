import json, datetime, sys
drops = json.load(open("drops.json"))
today = datetime.date.today()
hits = []
for d in drops:
    n = (datetime.date.fromisoformat(d["date"]) - today).days
    if n in (0, 1):
        hits.append(("TODAY" if n == 0 else "TOMORROW") + ": " + d["date"] + " - " + d["text"])
if hits:
    print("\n".join(hits))
    sys.exit("DROP ALERT (this run is meant to fail so GitHub emails you)")
print("no drops today or tomorrow")
