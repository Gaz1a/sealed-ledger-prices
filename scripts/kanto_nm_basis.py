#!/usr/bin/env python3
"""READ-ONLY audit data: Near Mint basis for wanted Kanto cards from PokemonPriceTracker per-condition prices -> kanto_nm_basis.json. Changes no ledger value."""
import json, os, time, datetime, urllib.request, urllib.error
K = os.environ["PPT_KEY"]
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
ceil = load("ceilings.json", {}).get("kanto151", []); tr = load("tracked.json", {}); tcg = load("prices.json", {}).get("prices", {})
pc = load("pricecharting.json", {}).get("cards", {}); gr = load("graded.json", {}).get("cards", {})
def fetch(pid):
    url = f"https://www.pokemonpricetracker.com/api/v2/cards?tcgPlayerId={pid}&limit=1"
    for a in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": f"Bearer {K}"}), timeout=40) as r:
                d = json.load(r).get("data"); return d[0] if isinstance(d, list) and d else d
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(20 * (a + 1)); continue
            return None
        except Exception: time.sleep(3)
out = {}
for e in ceil:
    k = e["id"]; t = tr.get(k, {}); pid = t.get("productId")
    d = fetch(pid) or {}; time.sleep(1.2)
    pr = d.get("prices") or {}; var = pr.get("variants") or {}
    want = (t.get("variant") or "").lower()
    # choose the ledger's printing: variant name equal to ledger variant (e.g. "Unlimited Holofoil" / "Holofoil")
    vname = next((v for v in var if v.lower() == want), None) or next((v for v in var if "1st" not in v.lower() and "shadowless" not in v.lower()), None)
    conds = var.get(vname) or {}
    nm = next((c["price"] for n, c in conds.items() if n.lower().startswith("near mint")), None)
    lp = next((c["price"] for n, c in conds.items() if n.lower().startswith("lightly")), None)
    gu = ((gr.get(k) or {}).get("grades") or {}).get("ungraded") or {}
    out[k] = {"name": e["name"], "cardNum": e["cardNum"], "productId": pid, "oldTarget": e["ceiling"], "variantUsed": vname, "variantsAvailable": list(var),
              "nmPrice": nm, "lpPrice": lp, "tcgcsvMarket": (tcg.get(k) or {}).get("market"), "tcgcsvLowAllConditions": (tcg.get(k) or {}).get("low"),
              "cardLevelListings": pr.get("listings"), "cardLevelSellers": pr.get("sellers"), "recentSales30d": pr.get("recentSales"),
              "ebaySoldUngradedMedian": gu.get("median"), "ebaySoldUngradedN": gu.get("n"), "note_ebay": "eBay ungraded sales are NOT condition-matched",
              "pcUngraded": (pc.get(k) or {}).get("ungraded")}
json.dump({"generated": datetime.date.today().isoformat(), "purpose": "audit only - nothing applied", "cards": out}, open("kanto_nm_basis.json", "w"), indent=1)
print(len(out), "cards")
