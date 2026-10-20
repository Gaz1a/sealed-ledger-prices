"""Keeps tracked.json free of duplicate rip-pick copies. Runs first in the daily prices workflow.
Rule: an 'rp-*' entry is dropped when any non-rp entry tracks the same productId+variant (the owned/ledger row always wins), or when it is listed in tracked_blocklist.json.
Other duplicate productIds (non-rp) are only reported in tracked_guard.json, never auto-removed. Also strips dropped ids from prices.json and ebay_supply.json."""
import json, os, datetime, collections
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def ld(n, d):
    try: return json.load(open(os.path.join(R, n)))
    except Exception: return d
tr = ld("tracked.json", {}); block = ld("tracked_blocklist.json", {}); block.pop("_note", None)
keep = collections.defaultdict(list)
for k, v in tr.items():
    if not k.startswith("rp-"): keep[(v["productId"], v.get("variant"))].append(k)
drop = {}
for k, v in tr.items():
    if k.startswith("rp-"):
        owner = keep.get((v["productId"], v.get("variant")))
        if owner: drop[k] = "duplicate of " + owner[0]
        elif k in block: drop[k] = block[k]
if drop:
    for k in drop: tr.pop(k)
    json.dump(tr, open(os.path.join(R, "tracked.json"), "w"), indent=1)
    p = ld("prices.json", None)
    if p:
        for k in drop: p.get("prices", {}).pop(k, None)
        json.dump(p, open(os.path.join(R, "prices.json"), "w"), indent=1)
    e = ld("ebay_supply.json", None)
    if e:
        for k in drop: e.get("items", {}).pop(k, None)
        json.dump(e, open(os.path.join(R, "ebay_supply.json"), "w"), indent=1)
dups = {}
for k, v in tr.items(): dups.setdefault(f"{v['productId']}|{v.get('variant')}", []).append(k)
rep = {"generated": datetime.date.today().isoformat(), "removed": drop, "otherDuplicates": {k: v for k, v in dups.items() if len(v) > 1}}
json.dump(rep, open(os.path.join(R, "tracked_guard.json"), "w"), indent=1)
print("removed", drop, "other dup keys", len(rep["otherDuplicates"]))
