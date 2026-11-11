#!/usr/bin/env python3
"""Grader log for the ledger's Grader tab (Gaz, Nov 11). Reads every grading record we keep and prints one JSON doc
{generated, items: [...newest first, max 80]} for the Tracker to copy into meta/grader. Sources (both kept for good):
grading/results.json on main (photo checks: own cards, seller photos, Grade issues) and manual.json on the checks branch
(eBay listing checks). Runs anywhere with network: python3 grader_log.py > grader.json"""
import json, urllib.request, datetime, re
RAW = "https://raw.githubusercontent.com/Gaz1a/sealed-ledger-prices/"
def get(path):
    try: return json.load(urllib.request.urlopen(urllib.request.Request(RAW + path, headers={"User-Agent": "ledger"}), timeout=30))
    except Exception: return {}
items = []
for key, x in (get("main/grading/results.json") or {}).items():
    lid = key.split("/")[0]
    title = re.sub(r"^(issue-\d+-|listing-)", "", lid).replace("-", " ")
    items.append({"key": key, "title": title, "date": x.get("date") or (x.get("checked") or "")[:10], "source": "photos",
                  "p8": x.get("graderP8"), "grade": x.get("graderGrade"), "flags": [f for f in x.get("flags", []) if not f.startswith("grader:")][:3],
                  "sheet": RAW + "main/" + x["sheet"] if x.get("sheet") else None})
m = get("checks/manual.json")
for x in (m.get("checks") if isinstance(m, dict) else m) or []:
    items.append({"key": str(x.get("itemId")), "title": x.get("title"), "date": (x.get("checked") or "")[:10], "source": "eBay listing",
                  "p8": x.get("graderP8"), "grade": x.get("graderGrade"), "flags": [f for f in (x.get("flags") or []) if not f.startswith("grader:")][:3],
                  "sheet": RAW + "checks/" + x["sheet"] if x.get("sheet") else None, "url": x.get("url"), "price": x.get("price")})
items.sort(key=lambda i: i.get("date") or "", reverse=True)
print(json.dumps({"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "count": len(items), "items": items[:80]}, separators=(",", ":")))
