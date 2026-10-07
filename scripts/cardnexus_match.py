#!/usr/bin/env python3
"""One-off: match tracked items that failed the tcgplayerId link, by name + expansion + number.
Writes cardnexus_match.json (candidates) and, for unambiguous matches only, a manual mapping in cardnexus_ids.json."""
import json, os, re, sys, time, urllib.error, urllib.request

BASE = "https://public-api.cardnexus.com/v1"
TOKEN = os.environ.get("CARDNEXUS_TOKEN", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLEEP = 1.2
SEALED = {"op": "or", "values": ["sealed"]}
CARD = {"op": "or", "values": ["card"]}
# ledgerId -> (search name, printNumber, exact expansion name, kind)
TARGETS = {
    "k-006": ("Charizard", "4", "Base Set", "card"),
    "k-107": ("Hitmonchan", "7", "Base Set", "card"),
    "k-130": ("Gyarados", "6", "Base Set", "card"),
    "k-143": ("Snorlax", "11", "Jungle", "card"),
    "h-lumiose": ("Lumiose City Mini Tin", None, None, "sealed"),
    "h-tsc": ("Tech Sticker Collection", None, None, "sealed"),
}


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("429 - stopping")
            sys.exit(0)
        j = None
        print("HTTP", e.code, path)
    except Exception as e:
        j = None
        print("ERR", repr(e)[:80])
    time.sleep(SLEEP)
    return j


def items_of(j):
    if isinstance(j, dict):
        for k in ("data", "items", "results"):
            if isinstance(j.get(k), list):
                return j[k]
    return j if isinstance(j, list) else []


def norm_num(x):
    return re.sub(r"^0+", "", str(x or "").split("/")[0].strip()).lower()


def norm_name(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def summarize(p):
    ext = p.get("externalIds") or {}
    return {"id": p.get("id"), "name": p.get("name"),
            "expansion": (p.get("expansion") or {}).get("name"), "expansionCode": (p.get("expansion") or {}).get("code"),
            "printNumber": p.get("printNumber"), "variant": p.get("variant"), "finishes": p.get("finishes"),
            "productType": p.get("productType"), "game": (p.get("game") or {}).get("id"),
            "tcgplayerIds": ext.get("tcgplayer"), "cardmarketIds": ext.get("cardmarket")}


def main():
    if not TOKEN:
        sys.exit("CARDNEXUS_TOKEN is not set")
    tracked = json.load(open(os.path.join(ROOT, "tracked.json")))
    ids_path = os.path.join(ROOT, "cardnexus_ids.json")
    ids = json.load(open(ids_path))
    # expansions of the Pokemon game
    exps, off = [], 0
    while True:
        j = call("GET", f"/games/pokemon/expansions?limit=100&offset={off}")
        page = items_of(j)
        exps += page
        if len(page) < 100:
            break
        off += 100
    print("pokemon expansions:", len(exps))
    out, added = {}, []
    for lid, (name, num, exp_hint, kind) in TARGETS.items():
        our_tcg = tracked[lid]["productId"]
        cands = {}
        searches = []
        if kind == "card":
            hint_ids = [e["id"] for e in exps if exp_hint.lower() in (e.get("name") or "").lower()]
            searches.append({"name": name, "productType": CARD, "expansionId": hint_ids[:200], "limit": 100} if hint_ids else None)
            searches.append({"name": name, "printNumber": num, "productType": CARD, "limit": 100})
        else:
            searches.append({"name": name, "productType": SEALED, "limit": 100})
        for body in filter(None, searches):
            j = call("POST", "/products/search", body)
            for p in items_of(j):
                if (p.get("game") or {}).get("id", "pokemon") not in ("pokemon", "pokemon-japan"):
                    continue
                cands[p["id"]] = p
        rows = [summarize(p) for p in cands.values()]
        if kind == "card":
            rel = [r for r in rows if norm_name(name) in norm_name(r["name"]) and norm_num(r["printNumber"]) == num
                   and "base set" in (r["expansion"] or "").lower() + " jungle" * (exp_hint == "Jungle")
                   or (norm_name(r["name"]) == norm_name(name) and norm_num(r["printNumber"]) == num
                       and exp_hint.lower() in (r["expansion"] or "").lower())]
            exact = [r for r in rel if (r["expansion"] or "").strip().lower() == exp_hint.lower()]
        else:
            rel = [r for r in rows if norm_name(name) in norm_name(r["name"])]
            exact = [r for r in rows if norm_name(r["name"]) == norm_name(tracked[lid]["title"])]
        verdict = "ambiguous / not found - candidates listed"
        if len(exact) == 1 and not (exact[0]["tcgplayerIds"] or []):
            ids[lid] = exact[0]["id"]
            ids.setdefault("_manual", {})[lid] = {"cn": exact[0]["id"], "manual": True,
                                                  "finish": (exact[0]["finishes"] or [None])[0],
                                                  "note": f'{exact[0]["name"]} / {exact[0]["expansion"]} #{exact[0]["printNumber"]}'}
            added.append(lid)
            verdict = "MANUAL MAPPING ADDED"
        elif len(exact) == 1:
            verdict = "one name/expansion/number match, but it carries other TCGplayer ids (different print?) - not added"
        out[lid] = {"tracked": tracked[lid]["title"], "ourTcgplayerId": our_tcg, "variant": tracked[lid].get("variant"),
                    "verdict": verdict, "relevant": rel, "otherCandidates": [r for r in rows if r not in rel][:15]}
        print(f"\n=== {lid} {tracked[lid]['title']} (our TCGplayer id {our_tcg}, {tracked[lid].get('variant')}) -> {verdict}")
        for r in rel or rows[:10]:
            print("  ", json.dumps(r, ensure_ascii=False))
    json.dump(out, open(os.path.join(ROOT, "cardnexus_match.json"), "w"), indent=1, ensure_ascii=False)
    if added:
        json.dump(ids, open(ids_path, "w"), indent=1, sort_keys=True)
    print("\nadded:", added)


if __name__ == "__main__":
    main()
