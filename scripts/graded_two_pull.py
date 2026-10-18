"""Pull just the two new graded cards (same route/format as graded_pull.py) and merge them into graded.json; save detail to graded_two_detail.json."""
import json, os, re, sys, time, datetime
sys.argv = ["x"]; os.environ.setdefault("PPT_KEY", "")
src = open("scripts/graded_pull.py").read()
head = src[:src.index("watch = load(")]            # helpers up to the watch-list build
ns = {}; exec(compile(head, "gp", "exec"), ns)
tail = src[src.index("def num(x)"):src.index("prev = load(")]
exec(compile(tail, "gp2", "exec"), ns)
W = [c for c in json.load(open("graded_watch.json")) if c["id"] in ("s-flareon-065-svp-jp", "s-pikachu-vmax-tg29")]
g = json.load(open("graded.json")); detail = {}
for c in W:
    j = ns["fetch"](c["productId"], c.get("language")); d = j.get("data", j)
    if isinstance(d, list): d = d[0] if d else {}
    eb = d.get("ebay") or {}; sbg = eb.get("salesByGrade") or {}
    grades = {re.sub(r"[^a-z0-9]", "", k.lower()): ns["slim"](v) for k, v in sbg.items() if re.sub(r"[^a-z0-9]", "", k.lower()) in ns["WANT"]}
    pj = (eb.get("priceHistory") or {}).get("psa10") or {}
    hist = {gname: [[ns["TODAY"], s["median"], s.get("n")]] for gname, s in grades.items() if s and s.get("median") is not None}
    g["cards"][c["id"]] = {"name": c["name"], "productId": c["productId"], "grades": grades, "history": hist, "ok": bool(grades), "language": c.get("language"),
                           "psa10DailyLast10": [[k, v.get("average"), v.get("count")] for k, v in sorted(pj.items())][-10:]}
    detail[c["id"]] = {"matched": {"name": d.get("name"), "set": d.get("setName"), "number": d.get("cardNumber"), "tcgPlayerId": d.get("tcgPlayerId"), "rarity": d.get("rarity")},
                       "salesByGrade": {k: sbg[k] for k in sbg if k in ("psa10", "psa9", "ungraded", "raw")}, "gradeKeys": list(sbg.keys()),
                       "totalSales": eb.get("totalSales"), "range": [eb.get("dateRangeStart"), eb.get("dateRangeEnd")], "psa10Daily": {k: pj[k] for k in sorted(pj)[-10:]}}
    time.sleep(1.3)
g["generated"] = ns["TODAY"]
json.dump(g, open("graded.json", "w"), indent=1); json.dump(detail, open("graded_two_detail.json", "w"), indent=1)
print({k: v["matched"] for k, v in detail.items()})
