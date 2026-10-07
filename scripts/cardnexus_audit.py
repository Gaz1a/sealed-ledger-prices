#!/usr/bin/env python3
"""One-off audit: CardNexus marketplace listings + 30-day sales for the 30 highest-value tracked items.
Rate limits: listings 120/h, sales 60/h. Writes cardnexus_audit.json (no tokens, no URLs)."""
import datetime, json, os, sys, time, urllib.error, urllib.request

BASE = "https://public-api.cardnexus.com/v1"
TOKEN = os.environ.get("CARDNEXUS_TOKEN", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLEEP = 1.2
TOP = 30
SALES_BUDGET, LIST_BUDGET = 55, 110   # stay under 60/h and 120/h
MAX_PAGES = 5


class Stop(Exception):
    pass


def load(n):
    return json.load(open(os.path.join(ROOT, n)))


def get(path):
    req = urllib.request.Request(BASE + path)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise Stop("429")
        return e.code, None
    except Exception:
        return 0, None


def main():
    if not TOKEN:
        sys.exit("CARDNEXUS_TOKEN is not set")
    tracked, prices, ids = load("tracked.json"), load("prices.json")["prices"], load("cardnexus_ids.json")
    ranked = sorted(((prices.get(l, {}).get("market") or 0, l) for l in tracked), reverse=True)[:TOP]
    state = {}      # cnId -> {"listings": [...], "sales": [...], "lnext": cursor, "snext": cursor, "lpages": n, "spages": n, "err": []}
    used = {"listings": 0, "sales": 0}
    stopped = None

    def fetch(cn, kind, st):
        cur = st["lnext" if kind == "listings" else "snext"]
        q = "?limit=100" + (f"&cursor={cur}" if cur else "")
        s, j = get(f"/products/{cn}/{kind}{q}")
        time.sleep(SLEEP)
        used[kind] += 1
        pages = "lpages" if kind == "listings" else "spages"
        st[pages] += 1
        if s != 200 or not isinstance(j, dict):
            st["err"].append(f"{kind} HTTP {s}")
            st["lnext" if kind == "listings" else "snext"] = None
            return
        st[kind].extend(j.get("data", []))
        st["lnext" if kind == "listings" else "snext"] = (j.get("pagination") or {}).get("nextCursor")

    cns = []
    for _, l in ranked:
        cn = ids.get(l)
        if cn and cn not in state:
            state[cn] = {"listings": [], "sales": [], "lnext": None, "snext": None, "lpages": 0, "spages": 0, "err": []}
            cns.append(cn)
    try:
        for cn in cns:                      # round 1: first page of each
            fetch(cn, "listings", state[cn])
            fetch(cn, "sales", state[cn])
        for _ in range(MAX_PAGES - 1):      # later rounds: follow cursors while budget lasts
            for cn in cns:
                st = state[cn]
                if st["lnext"] and used["listings"] < LIST_BUDGET:
                    fetch(cn, "listings", st)
                if st["snext"] and used["sales"] < SALES_BUDGET:
                    fetch(cn, "sales", st)
    except Stop as e:
        stopped = str(e)

    items = []
    for mkt, l in ranked:
        cn = ids.get(l)
        row = {"ledgerId": l, "title": tracked[l].get("title"), "market": mkt, "cnId": cn}
        if not cn:
            row["note"] = "no CardNexus id"
            items.append(row)
            continue
        st = state[cn]
        L, S = st["listings"], st["sales"]
        row["listingsCount"] = len(L)
        row["listingsQuantity"] = sum(x.get("quantity") or 0 for x in L)
        row["listingsComplete"] = st["lnext"] is None and not stopped
        if L:
            low = L[0]
            row["lowestListing"] = {"amount": (low.get("price") or {}).get("amount"),
                                    "currency": (low.get("price") or {}).get("currency"),
                                    "sellerCountry": (low.get("seller") or {}).get("country"),
                                    "condition": low.get("condition"), "graded": bool(low.get("graded"))}
        row["salesCount"] = len(S)
        row["salesQuantity"] = sum(x.get("quantity") or 0 for x in S)
        row["salesComplete"] = st["snext"] is None and not stopped
        if S:
            last = S[0]
            row["mostRecentSale"] = {"soldAt": last.get("soldAt"), "price": last.get("price"),
                                     "priceEur": last.get("priceEur"), "region": last.get("region"),
                                     "condition": last.get("condition"), "graded": bool(last.get("graded"))}
        if st["err"]:
            row["errors"] = st["err"]
        items.append(row)

    out = {"generated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
           "window": "sales = last 30 days (CardNexus marketplace)", "requests": used,
           "stopped": stopped, "items": items}
    json.dump(out, open(os.path.join(ROOT, "cardnexus_audit.json"), "w"), indent=1)
    priced = [i for i in items if i.get("cnId")]
    print(f"audit: {len(items)} items, {len(priced)} with CardNexus id, "
          f"{sum(1 for i in priced if i['listingsCount'])} with listings, "
          f"{sum(1 for i in priced if i['salesCount'])} with sales, requests {used}"
          + (f", stopped on {stopped}" if stopped else ""))


if __name__ == "__main__":
    main()
