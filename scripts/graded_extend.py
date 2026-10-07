#!/usr/bin/env python3
"""Add the top 3 chase cards of each main set (2023+, from untracked_singles.json) plus any held tracked single to graded_watch.json."""
import json, os
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
watch = load("graded_watch.json", [])
sg = load("untracked_singles.json", {})
if not sg.get("cards"): raise SystemExit("untracked_singles.json missing; run that audit first")
have = {str(c["productId"]): c for c in watch}
per = {}
for c in sg["cards"]:                     # already sorted by market desc
    per.setdefault(c["set"], [])
    meta = sg["sets"].get(c["set"], {})
    if meta.get("mainSet2023plus") and len(per[c["set"]]) < 3: per[c["set"]].append(c)
    elif c["tracked"] and c["setHeld"] and c["productId"] not in [x["productId"] for x in per[c["set"]]] and str(c["productId"]) not in have:
        per[c["set"]].append(c)
added = 0
for cards in per.values():
    for c in cards:
        k = str(c["productId"])
        if k in have:
            have[k]["rawMarket"] = c["market"]; have[k]["subtype"] = c["subtype"]; continue
        w = {"id": f"c-{k}", "name": f'{c["name"]} {c["number"]} ({c["set"]})', "productId": c["productId"],
             "rawMarket": c["market"], "subtype": c["subtype"], "set": c["set"]}
        watch.append(w); have[k] = w; added += 1
json.dump(watch, open("graded_watch.json", "w"), indent=1)
print("watch size", len(watch), "added", added)
