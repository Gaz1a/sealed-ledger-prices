#!/usr/bin/env python3
"""PSA population via the official PSA Public API -> psa_pop.json. Needs secret PSA_TOKEN. Never prints it.
The API has no search: it needs a PSA specID per card (psa_specs.json {cardId: specId}) or a cert number
(psa_certs.json {cardId: cert}) from which the specID is read. Rotates through cards; stops on the daily limit."""
import json, os, sys, time, datetime, urllib.request, urllib.error
TOKEN = os.environ.get("PSA_TOKEN", "")
DAILY = int(os.environ.get("PSA_DAILY_LIMIT", "90"))
STATE = {}
try: STATE = json.load(open("psa_find_state.json"))
except Exception: pass     # PSA's free quota is not documented in the public docs; keep a safe margin
BASE = "https://api.psacard.com/publicapi"
TODAY = datetime.date.today().isoformat()
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
class Stop(Exception): pass
used = STATE.get("callsUsed", 0) if STATE.get("callsDate") == TODAY else 0   # cert lookups by psa_find_specs count against the same daily budget
def get(path):
    global used
    if used >= DAILY: raise Stop("daily cap")
    used += 1; time.sleep(1.1)
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + TOKEN, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r: return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429): raise Stop(f"HTTP {e.code}")
        return None
    except Exception: return None
def find(d, *names):
    if isinstance(d, dict):
        low = {k.lower(): v for k, v in d.items()}
        for n in names:
            if n.lower() in low and isinstance(low[n.lower()], (int, float)): return low[n.lower()]
    return None
def main():
    if not TOKEN: sys.exit("PSA_TOKEN is not set")
    g = load("graded.json", {}).get("cards", {})
    specs, certs = load("psa_specs.json", {}), load("psa_certs.json", {})
    prev = load("psa_pop.json", {}); cards = dict(prev.get("cards", {}))
    chase = sorted([(k, v) for k, v in g.items() if v.get("rawMarket")], key=lambda kv: -kv[1]["rawMarket"])[:60]
    order = sorted(chase, key=lambda kv: (cards.get(kv[0], {}).get("asOf") or "0000"))   # stalest first = rotation
    missing, stop = [], None
    try:
        for cid, v in order:
            ent = specs.get(cid); sid = ent.get("specId") if isinstance(ent, dict) else ent
            if cards.get(cid, {}).get("asOf") and (datetime.date.today() - datetime.date.fromisoformat(cards[cid]["asOf"])).days < 6: continue   # weekly refresh
            if not sid and certs.get(cid):
                j = get(f"/cert/GetByCertNumber/{certs[cid]}")
                c = (j or {}).get("PSACert") or {}
                sid = c.get("SpecID")
                if sid: specs[cid] = {"specId": sid, "cert": certs[cid], "verified": True, "source": "manual-cert"}
            if not sid: missing.append({"id": cid, "name": v["name"], "rawMarket": v["rawMarket"]}); continue
            j = get(f"/pop/GetPSASpecPopulation/{sid}")
            if not isinstance(j, dict): continue
            p10, p9 = find(j, "Grade10", "PSA10", "Gem"), find(j, "Grade9", "PSA9")
            tot = find(j, "Total", "TotalPopulation", "PopTotal")
            cards[cid] = {"name": v["name"], "specId": sid, "psa10": p10, "psa9": p9, "total": tot,
                          "gemRate": round(p10 / tot, 4) if p10 is not None and tot else None, "asOf": TODAY,
                          "rawKeys": None if (p10 is not None and tot) else sorted(j.keys())[:40]}
    except Stop as e: stop = str(e)
    json.dump(specs, open("psa_specs.json", "w"), indent=1, sort_keys=True)
    json.dump({"generated": TODAY, "source": "PSA Public API (GetPSASpecPopulation)", "dailyCallBudget": DAILY, "callsUsed": used,
               "stopped": stop, "cards": cards, "missingSpecIds": missing,
               "note": "Add psa_specs.json {cardId: specId} or psa_certs.json {cardId: certNumber} for cards in missingSpecIds."},
              open("psa_pop.json", "w"), indent=1)
    print(f"cards with pop {sum(1 for c in cards.values() if c.get('total'))}, missing specIds {len(missing)}, calls {used}, stopped: {stop}")
if __name__ == "__main__": main()
