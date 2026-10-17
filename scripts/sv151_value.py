#!/usr/bin/env python3
"""h-sv151 calculated row: daily sum of TCGplayer market (tcgcsv) over every line (product x subtype) in the English SV 151 group.
Lines with no price are listed as gaps, never counted as zero. History: one row per day appended; backfill built ONLY from card histories already
in the repo (ppt_backfill_180.json cands, NM series per variant) and kept separate, with per-day line coverage, because it is partial."""
import json, os, re, time, datetime, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://tcgcsv.com/tcgplayer/3"
TODAY = datetime.date.today().isoformat()
def get(u):
    for i in range(4):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sealed-ledger-prices/1.0"}), timeout=40))
        except Exception:
            if i == 3: raise
            time.sleep(2 * (i + 1))
def ld(p, d):
    try: return json.load(open(os.path.join(ROOT, p)))
    except Exception: return d
g = [x for x in get(f"{BASE}/groups")["results"] if re.search(r"(^|[: ])151$", x["name"].strip()) and "japan" not in x["name"].lower()]
assert g, "151 group not found"
gid = g[0]["groupId"]
prods = get(f"{BASE}/{gid}/products")["results"]; prices = get(f"{BASE}/{gid}/prices")["results"]
cards = {}
for p in prods:
    ext = {e["name"]: e.get("value") for e in p.get("extendedData", [])}
    if ext.get("Number"): cards[p["productId"]] = {"name": p["name"], "number": ext["Number"], "rarity": ext.get("Rarity")}
rows = {}
for r in prices:
    if r["productId"] in cards: rows.setdefault(r["productId"], []).append(r)
lines, gaps = [], []
for pid, c in sorted(cards.items(), key=lambda kv: kv[1]["number"]):
    rs = rows.get(pid, [])
    if not rs: gaps.append({"productId": pid, **c, "subtype": None, "why": "no price row"}); continue
    for r in sorted(rs, key=lambda r: r["subTypeName"]):
        ln = {"productId": pid, **c, "subtype": r["subTypeName"], "market": r.get("marketPrice"), "low": r.get("lowPrice")}
        lines.append(ln)
        if ln["market"] is None: gaps.append({**{k: ln[k] for k in ("productId", "name", "number", "rarity", "subtype")}, "why": "market price null"})
priced = [l for l in lines if l["market"] is not None]
total = round(sum(l["market"] for l in priced), 2)
energies = [l for l in lines if re.search(r"energy", l["name"], re.I)]
cosmos = [l for l in lines if re.search(r"cosmos", l["name"], re.I)]
now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
by = {}
for l in lines: by[l["subtype"]] = by.get(l["subtype"], 0) + 1
val = {"id": "h-sv151", "generated": now, "label": "calculated; TCGplayer market (tcgcsv), not sold-verified", "groupId": gid, "groupName": g[0]["name"],
       "cards": len(cards), "lines": len(lines), "linesPriced": len(priced), "gapCount": len(gaps), "gaps": gaps, "total": total,
       "linesBySubtype": by, "energyLines": len(energies), "cosmosEnergyLines": len(cosmos)}
json.dump(val, open(os.path.join(ROOT, "sv151_value.json"), "w"), indent=1)
json.dump(lines, open(os.path.join(ROOT, "sv151_lines.json"), "w"), separators=(",", ":"))
hist = ld("sv151_history.json", {"history": []})
hist["history"] = [h for h in hist["history"] if h["date"] != TODAY] + [{"date": TODAY, "total": total, "linesPriced": len(priced), "lines": len(lines), "gaps": len(gaps)}]
hist["note"] = "one row per daily run; gaps excluded from the sum, never zero-filled"
json.dump(hist, open(os.path.join(ROOT, "sv151_history.json"), "w"), indent=1)
# backfill: PPT NM history per variant. State comes from scripts/sv151_backfill_ppt.py (resumable, all cards x all variants);
# older card histories already in the repo (ppt_backfill_180.json) fill in until then.
tracked, b = ld("tracked.json", {}), ld("ppt_backfill_180.json", {})
st = ld("sv151_ppt_state.json", {})
want = {(l["productId"], l["subtype"]): l for l in lines}
series = {}
for lid, cs in b.get("cands", {}).items():
    pid = (tracked.get(lid) or {}).get("productId")
    for label, pts in cs.items():
        m = re.match(r"variants/(.+)/Near Mint/history$", label)
        if m and (pid, m.group(1)) in want and (pid, m.group(1)) not in series:
            series[(pid, m.group(1))] = {d: p for d, p in pts}
for pid, e in st.items():
    for sub, pts in (e.get("variants") or {}).items():
        if (int(pid), sub) in want: series[(int(pid), sub)] = {d: p for d, p in pts}
final = {"ok", "no PPT record", "no history rows"}
done_cards = sum(1 for c in cards if st.get(str(c), {}).get("status") in final)
complete = done_cards == len(cards)
dates = sorted({d for s_ in series.values() for d in s_})
bf = []
for d in dates:
    vals = [s_[d] for s_ in series.values() if d in s_]
    bf.append({"date": d, "partialTotal": round(sum(vals), 2), "linesWithHistory": len(vals), "linesTotal": len(lines), "complete": len(vals) == len(lines)})
out = {"generated": now, "cardsFetched": done_cards, "cardsTotal": len(cards), "backfillComplete": complete,
       "note": "partialTotal is NOT the master-set value unless complete=true; days are merged into sv151_history.json only once every card has been fetched (lines with no point that day are counted as gaps, never zero).",
       "linesWithAnyHistory": len(series), "linesTotal": len(lines),
       "lines": [{"productId": k[0], "subtype": k[1], "name": want[k]["name"], "number": want[k]["number"], "points": len(v)} for k, v in series.items()], "days": bf}
json.dump(out, open(os.path.join(ROOT, "sv151_backfill.json"), "w"), indent=1)
if complete:
    own = {h["date"] for h in hist["history"] if h.get("source") != "ppt-backfill"}
    first_own = min(own) if own else TODAY
    keep = [h for h in hist["history"] if h.get("source") != "ppt-backfill"]
    for r in bf:
        if r["date"] < first_own:
            keep.append({"date": r["date"], "total": r["partialTotal"], "linesPriced": r["linesWithHistory"], "lines": len(lines), "gaps": len(lines) - r["linesWithHistory"], "source": "ppt-backfill"})
    hist["history"] = sorted(keep, key=lambda h: h["date"])
    json.dump(hist, open(os.path.join(ROOT, "sv151_history.json"), "w"), indent=1)
print(len(cards), "cards", len(lines), "lines", len(priced), "priced", len(gaps), "gaps", total, "total; backfill cards", done_cards, "complete", complete)
