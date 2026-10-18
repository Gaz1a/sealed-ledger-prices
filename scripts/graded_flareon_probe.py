"""Read-only: how does PokemonPriceTracker v2 serve the Japanese Flareon 065/SV-P (TCGplayer 587823)? Tries id/search variants, records status + what came back. Never prints the key."""
import json, os, urllib.request, urllib.parse, urllib.error, time
K = os.environ["PPT_KEY"]; B = "https://www.pokemonpricetracker.com/api/v2/cards?"
V = {"id": "tcgPlayerId=587823&includeEbay=true&limit=1",
     "id+lang": "tcgPlayerId=587823&includeEbay=true&limit=1&language=japanese",
     "search+lang": "search=Flareon&language=japanese&includeEbay=true&limit=20",
     "search-number+lang": "search=" + urllib.parse.quote("Flareon 065/SV-P") + "&language=japanese&includeEbay=true&limit=20",
     "search-nagaba+lang": "search=" + urllib.parse.quote("Flareon Nagaba") + "&language=japanese&includeEbay=true&limit=20",
     "search-nagaba": "search=" + urllib.parse.quote("Flareon Nagaba") + "&includeEbay=true&limit=20",
     "set-search": "search=Flareon&set=" + urllib.parse.quote("SV-P Promotional Cards") + "&includeEbay=true&limit=20"}
out = {}
for n, q in V.items():
    time.sleep(1.3)
    try:
        r = urllib.request.urlopen(urllib.request.Request(B + q, headers={"Authorization": "Bearer " + K}), timeout=60); st = r.status; j = json.load(r)
    except urllib.error.HTTPError as e: st = e.code; j = {"body": e.read().decode("utf-8", "replace")[:300]}
    except Exception as e: st = type(e).__name__; j = {}
    d = j.get("data", j); d = d if isinstance(d, list) else [d] if isinstance(d, dict) and d else []
    out[n] = {"status": st, "n": len(d), "meta": {k: v for k, v in j.items() if k != "data"} if isinstance(j, dict) else None,
              "cards": [{"name": c.get("name"), "set": c.get("setName"), "number": c.get("cardNumber"), "tcgPlayerId": c.get("tcgPlayerId"), "language": c.get("language"), "rarity": c.get("rarity"),
                         "ebayGrades": list(((c.get("ebay") or {}).get("salesByGrade") or {}).keys())} for c in d[:20]]}
    sel = [c for c in d if str(c.get("tcgPlayerId")) == "587823" or "065" in str(c.get("cardNumber")) and "flareon" in str(c.get("name")).lower()]
    if sel: out[n]["match"] = sel[0].get("ebay")
json.dump(out, open("graded_flareon_probe.json", "w"), indent=1)
print({k: (v["status"], v["n"], bool(v.get("match"))) for k, v in out.items()})
