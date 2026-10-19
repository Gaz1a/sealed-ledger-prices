#!/usr/bin/env python3
"""Weekly scan of eBay's Browse API for active Base Set / Jungle / Fossil
common-uncommon and holo lot listings, for Gaz's Kanto 151 vintage project.
Pure mechanical collection: price/keyword/seller filtering only. No authenticity
or "is this a good buy" judgment — that happens in the Claude task that reads
this file, which can actually look at the listing photos.

Auth: eBay's client_credentials app token (no user login needed; Browse API
search/getItem are public-data endpoints under this grant). Requires repo
secrets EBAY_CLIENT_ID / EBAY_CLIENT_SECRET (Production keys, not Sandbox).
Stdlib only."""
import json, os, re, sys, time, base64, datetime, urllib.request, urllib.parse

ROOT = "."
TODAY = datetime.date.today()
UA = "sealed-ledger-ebay-scout/1.0"
CLIENT_ID = os.environ.get("EBAY_CLIENT_ID")
CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET")

COMMON_QUERIES = [
    "pokemon base set lot common uncommon",
    "pokemon jungle set lot common uncommon",
    "pokemon fossil set lot common uncommon",
    "pokemon wotc common uncommon lot",
]
HOLO_LOT_QUERIES = [
    "pokemon base set holo lot",
    "pokemon jungle set holo lot",
    "pokemon fossil set holo lot",
    "pokemon wotc holo rare lot",
]
MIN_COMMONS_FOR_COMMON_QUERIES = 5     # run the common/uncommon lot queries only while >= this many wanted commons/uncommons remain
SPECIES_MIN_PRICE, SPECIES_MAX_DEFAULT = 5.0, 600.0
MAX_DETAIL_CALLS_SPECIES = 3
SETS = {"102": "Base Set", "64": "Jungle", "62": "Fossil"}
MIN_PRICE, MAX_PRICE = 30.0, 90.0
MIN_FEEDBACK_SCORE = 50
MIN_FEEDBACK_PCT = 97.0
MAX_DETAIL_CALLS_PER_QUERY = 8   # only fetch full photos/returns for the best few per query

# listings where the buyer picks one card from a dropdown / list: never a real lot
PICK_ONE = re.compile(r"multiple choice|multi[- ]?choice|choose your|choose a card|choose (?:the )?card|pick your|pick a card|pick one|you pick|you choose|select card|select your|select a card|\bchoose\b.*\bcard|\bselect\b.*\bcard", re.I)

BAD_WORDS = re.compile(
    r"\bpsa\b|\bcgc\b|\bbgs\b|\bgraded\b|\breprint\b|\bcustom\b|\bproxy\b|\bfake\b|"
    r"\bdigital\b|\bonline\b|\bcode card\b|\bsingle card\b|\b1st edition\b|\bfirst edition\b",
    re.I)


def load_wants():
    """Kanto want list = every k-001..k-151 in tracked.json that the ledger export (owned_rows.csv) does not show as owned.
    Re-read on every run so it follows the ledger."""
    import csv
    tr = json.load(open(f"{ROOT}/tracked.json"))
    try: rows = list(csv.DictReader(open(f"{ROOT}/owned_rows.csv", encoding="utf-8-sig")))
    except Exception: rows = []
    owned = {r["id"] for r in rows if r.get("id", "").startswith("k-") and float(r.get("owned") or 0) > 0}
    try: basis = json.load(open(f"{ROOT}/kanto_nm_basis.json")).get("cards", {})
    except Exception: basis = {}
    wants = []
    for k, e in tr.items():
        if not k.startswith("k-") or k in owned: continue
        t = e.get("title", ""); m = re.match(r"(.+?)\s+(?:(\d+)/(\d+)|Black Star Promo #(\d+))", t)
        name = (m.group(1) if m else t.split(" ")[0]).strip(); num, den = (m.group(2), m.group(3)) if m and m.group(2) else (m.group(4) if m else None, None)
        holo = "holo" in t.lower() or "promo" in t.lower()
        mk = (basis.get(k) or {}).get("nmPrice") or (basis.get(k) or {}).get("tcgcsvMarket")
        wants.append({"id": k, "name": name, "num": num, "den": den, "set": SETS.get(den, "Black Star Promo" if "Promo" in t else ""),
                      "holo": holo, "first": "1st edition" in t.lower(), "market": mk})
    return wants, len(rows)

def species_query(w):
    if w["set"] == "Black Star Promo": return f"pokemon {w['name']} black star promo 8 wotc holo"
    return f"pokemon {w['name']} {w['set']} {w['num']}/{w['den']} holo"

def species_ok(title, w):
    t = re.sub(r"[^a-z0-9 ]", " ", title.lower()); nm = re.sub(r"[^a-z0-9 ]", " ", w["name"].lower())
    if not all(tok in t.split() for tok in nm.split()): return False
    setword = {"Base Set": r"\bbase\b", "Jungle": r"jungle", "Fossil": r"fossil", "Black Star Promo": r"black star|\bwotc\b"}.get(w["set"], r"wotc")
    return bool(re.search(setword + r"|\b%s ?/ ?%s\b" % (w["num"] or "x", w["den"] or "x"), t))

def get(url, headers=None, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception as e:
            if i == tries - 1:
                print("FAIL", url, e, file=sys.stderr)
                return None
            time.sleep(2 * (i + 1))

def get_token():
    if not CLIENT_ID or not CLIENT_SECRET:
        sys.exit("EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set")
    auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }).encode()
    req = urllib.request.Request(
        "https://api.ebay.com/identity/v1/oauth2/token", data=body,
        headers={"Authorization": f"Basic {auth}",
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)["access_token"]

def search(query, token, lo=MIN_PRICE, hi=MAX_PRICE):
    q = urllib.parse.quote(query)
    filt = urllib.parse.quote(f"price:[{lo}..{hi}],priceCurrency:USD,buyingOptions:{{FIXED_PRICE}}")
    url = (f"https://api.ebay.com/buy/browse/v1/item_summary/search"
           f"?q={q}&filter={filt}&limit=30&sort=price")
    d = get(url, headers={"Authorization": f"Bearer {token}",
                           "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"})
    return (d or {}).get("itemSummaries", [])

def get_item_detail(item_id, token):
    iid = urllib.parse.quote(item_id, safe="")
    url = f"https://api.ebay.com/buy/browse/v1/item/{iid}"
    return get(url, headers={"Authorization": f"Bearer {token}",
                              "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"})

def main():
    token = get_token()
    wants, nrows = load_wants()
    commons = [w for w in wants if not w["holo"]]
    run_commons = len(commons) >= MIN_COMMONS_FOR_COMMON_QUERIES
    seen_ids, candidates, stats = set(), [], {"pickOne": 0, "variations": 0, "badWords": 0}
    jobs = [(q, "lot", None) for q in (COMMON_QUERIES if run_commons else [])] + [(q, "lot", None) for q in HOLO_LOT_QUERIES] \
         + [(species_query(w), "species", w) for w in wants if w["holo"]]
    queries = [j[0] for j in jobs]

    for q, mode, w in jobs:
        if mode == "species":
            hi = round(max(60, (w["market"] or 0) * 1.5), 2) if w["market"] else SPECIES_MAX_DEFAULT
            hits = search(q, token, SPECIES_MIN_PRICE, hi)
        else: hits = search(q, token)
        if not hits:
            continue
        filtered = []
        for h in hits:
            title = h.get("title", "")
            if PICK_ONE.search(title): stats["pickOne"] += 1; continue
            if h.get("itemGroupType") or h.get("itemGroupHref") or h.get("variationOptions"): stats["variations"] += 1; continue   # multi-variation / dropdown listing
            bw = BAD_WORDS
            if mode == "species":
                if w["first"]: bw = re.compile(bw.pattern.replace(r"\b1st edition\b|\bfirst edition\b", r"\bnomatch1st\b"), re.I)
                if re.search(r"\bsingle card\b", title, re.I) and not species_ok(title, w): continue
                bw = re.compile(bw.pattern.replace(r"\bsingle card\b|", ""), re.I)
                if not species_ok(title, w): continue
            elif "lot" not in title.lower():
                continue
            if bw.search(title): stats["badWords"] += 1; continue
            seller = h.get("seller", {}) or {}
            score = seller.get("feedbackScore", 0) or 0
            pct = float(seller.get("feedbackPercentage", 0) or 0)
            if score < MIN_FEEDBACK_SCORE or pct < MIN_FEEDBACK_PCT:
                continue
            iid = h.get("itemId")
            if not iid or iid in seen_ids:
                continue
            price = float((h.get("price") or {}).get("value", 0) or 0)
            ship = h.get("shippingOptions", [{}])
            ship_cost = 0.0
            if ship:
                sc = (ship[0].get("shippingCost") or {}).get("value")
                ship_cost = float(sc) if sc else 0.0
            filtered.append({
                "itemId": iid, "title": title, "price": price, "shipping": ship_cost,
                "total": round(price + ship_cost, 2), "condition": h.get("condition"),
                "seller": seller.get("username"), "feedbackScore": score, "feedbackPct": pct,
                "url": h.get("itemWebUrl"), "image": (h.get("image") or {}).get("imageUrl"),
                "query": q, "kind": "single" if mode == "species" and not re.search(r"\blot\b", title, re.I) else "lot",
                "wantId": w["id"] if w else None,
            })
        filtered.sort(key=lambda x: x["total"])
        top = filtered[:(MAX_DETAIL_CALLS_SPECIES if mode == "species" else MAX_DETAIL_CALLS_PER_QUERY)]
        for c in top:
            seen_ids.add(c["itemId"])
            detail = get_item_detail(c["itemId"], token)
            time.sleep(0.3)
            if detail:
                if detail.get("itemGroupType") or detail.get("variationOptions") or detail.get("primaryItemGroup"): stats["variations"] += 1; continue
                imgs = [detail.get("image", {}).get("imageUrl")] if detail.get("image") else []
                imgs += [i.get("imageUrl") for i in (detail.get("additionalImages") or [])]
                c["images"] = [i for i in imgs if i][:6]
                terms = detail.get("returnTerms") or {}
                c["returnsAccepted"] = terms.get("returnsAccepted", False)
                c["description"] = (detail.get("shortDescription") or "")[:500]
            else:
                c["images"] = [c["image"]] if c.get("image") else []
                c["returnsAccepted"] = None
                c["description"] = ""
            candidates.append(c)

    candidates.sort(key=lambda x: x["total"])
    out = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "wantList": {"source": "tracked.json k-* minus owned in owned_rows.csv", "ledgerRows": nrows, "wanted": len(wants),
                        "holoOrPromo": len(wants) - len(commons), "commonsUncommons": len(commons),
                        "commonQueriesRun": run_commons, "commonThreshold": MIN_COMMONS_FOR_COMMON_QUERIES,
                        "ids": [w["id"] for w in wants]},
           "filtered": stats, "queries": queries, "candidates": candidates}
    json.dump(out, open(f"{ROOT}/ebay_kanto.json", "w"), indent=1, ensure_ascii=False)
    print(f"wants {len(wants)} (commons {len(commons)}, common queries {'on' if run_commons else 'off'}), "
          f"{len(queries)} queries, {len(candidates)} candidates written, filtered {stats}")

if __name__ == "__main__":
    main()
