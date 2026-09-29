#!/usr/bin/env python3
"""On-demand / scheduled check of Burbank Cards' own online catalog
(burbankcards.com) against Gaz's Sealed Ledger ceilings — sealed product,
modern chase singles, and the Kanto 151 vintage want-list. He's local to
this shop and can visit a few times a week, so this replaces manually
pulling their sealed-product page and eyeballing prices each time.

Two data sources on their Shopify storefront:
  - Sealed product collection: paginated /collections/<handle>/products.json
    (a few hundred SKUs, cheap to pull in full each run).
  - Singles catalog: far too large to paginate in full, so we hit the
    Predictive Search API (/search/suggest.json) once per tracked item —
    same "one query per ceiling" pattern as scripts/scan_ebay_sealed.py.

Matching is deliberately conservative (name + card-number token match,
not fuzzy scoring) because a false "deal" flag sends Gaz on a wasted trip;
a missed match just means he still checks that one by eye. No network
egress from the eval/dev sandbox this was written in, so the first live
run should be a manual workflow_dispatch to confirm the storefront's
predictive-search endpoint behaves as expected before trusting the cron.

Stdlib only."""
import json, os, re, sys, time, datetime, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOP = "https://burbankcards.com"
UA = "sealed-ledger-shop-scout/1.0"
SEALED_HANDLE = "pokemon-sealed-product"
MAX_SEALED_PAGES = 10   # 250/page; plenty for one shop's sealed catalog
REQUEST_DELAY = 0.4     # be polite to their storefront


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except Exception as e:
        print("FAIL", url, e, file=sys.stderr)
        return None


def load(name):
    p = os.path.join(ROOT, name)
    return json.load(open(p)) if os.path.exists(p) else {}


def money(v):
    if v is None:
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def fetch_sealed_catalog():
    """Full pull of the shop's sealed-product collection."""
    items = []
    for page in range(1, MAX_SEALED_PAGES + 1):
        url = f"{SHOP}/collections/{SEALED_HANDLE}/products.json?limit=250&page={page}"
        d = get_json(url)
        time.sleep(REQUEST_DELAY)
        products = (d or {}).get("products", [])
        if not products:
            break
        for p in products:
            title = p.get("title", "")
            for v in p.get("variants", []):
                items.append({
                    "title": title,
                    "variantTitle": v.get("title"),
                    "price": money(v.get("price")),
                    "available": v.get("available"),
                    "url": f"{SHOP}/products/{p.get('handle')}",
                    "productId": p.get("id"),
                })
    return items


def search_singles(query, limit=10):
    """Predictive Search API — one query, up to `limit` product hits."""
    q = urllib.parse.quote(query)
    url = (f"{SHOP}/search/suggest.json?q={q}&resources[type]=product"
           f"&resources[limit]={limit}&resources[options][unavailable_products]=show")
    d = get_json(url)
    time.sleep(REQUEST_DELAY)
    if not d:
        return []
    hits = []
    for p in (d.get("resources", {}) or {}).get("results", {}).get("products", []):
        price = money((p.get("price") or {}).get("amount") if isinstance(p.get("price"), dict) else p.get("price"))
        hits.append({
            "title": p.get("title", ""),
            "price": price,
            "url": SHOP + p.get("url", ""),
        })
    return hits


def norm(s):
    return re.sub(r"[^a-z0-9/]+", " ", (s or "").lower()).strip()


def match_sealed(catalog, ceilings, item_sets):
    flags, misses = [], []
    for c in ceilings:
        set_name, title = c["set"], c["title"]
        needle = norm(f"{set_name} {title}")
        needle_words = set(needle.split())
        best = None
        for row in catalog:
            hay = norm(f"{row['title']} {row.get('variantTitle') or ''}")
            hay_words = set(hay.split())
            overlap = len(needle_words & hay_words)
            # require the set name's distinctive words AND the product-type words to show up
            if overlap >= max(2, len(needle_words) - 1) and row["price"] is not None:
                if best is None or row["price"] < best["price"]:
                    best = row
        if best is None:
            misses.append({"id": c["id"], "set": set_name, "title": title, "ceiling": c["ceiling"]})
            continue
        deal = best["price"] <= c["ceiling"]
        flags.append({
            "id": c["id"], "set": set_name, "title": title, "ceiling": c["ceiling"],
            "shopPrice": best["price"], "shopTitle": best["title"], "url": best["url"],
            "deal": deal, "overCeilingBy": None if deal else round(best["price"] - c["ceiling"], 2),
        })
    return flags, misses


def match_singles(entries, kind_label):
    flags, misses = [], []
    for c in entries:
        if "cardNum" in c:
            query = f"{c['name']} {c['cardNum']} {c['set']}"
        else:
            query = f"{c['name']} {c['set']}"
        hits = search_singles(query)
        num = c.get("cardNum", "").split("/")[0] if c.get("cardNum") else None
        name_l = c["name"].lower().split(" ")[0]  # first word, e.g. "mega" or the species name
        species_l = c["name"].lower()
        best = None
        for h in hits:
            hl = h["title"].lower()
            if species_l.split(" ")[-1] not in hl and name_l not in hl:
                continue
            if num and (f"{num}/" not in h["title"] and f"#{num}" not in h["title"]):
                continue
            if h["price"] is None:
                continue
            if best is None or h["price"] < best["price"]:
                best = h
        if best is None:
            misses.append({"id": c["id"], "kind": kind_label, "name": c["name"], "set": c["set"], "ceiling": c["ceiling"]})
            continue
        deal = best["price"] <= c["ceiling"]
        flags.append({
            "id": c["id"], "kind": kind_label, "name": c["name"], "set": c["set"], "ceiling": c["ceiling"],
            "shopPrice": best["price"], "shopTitle": best["title"], "url": best["url"],
            "deal": deal, "overCeilingBy": None if deal else round(best["price"] - c["ceiling"], 2),
        })
    return flags, misses


def main():
    ceilings = load("ceilings.json")
    item_sets = load("item_sets.json")
    now = datetime.datetime.now(datetime.timezone.utc)

    catalog = fetch_sealed_catalog()
    sealed_flags, sealed_misses = match_sealed(catalog, ceilings.get("sealed", []), item_sets)
    chase_flags, chase_misses = match_singles(ceilings.get("chaseSingles", []), "chase-single")
    kanto_flags, kanto_misses = match_singles(ceilings.get("kanto151", []), "kanto-151")

    all_flags = sealed_flags + chase_flags + kanto_flags
    deals = [f for f in all_flags if f["deal"]]
    all_misses = sealed_misses + chase_misses + kanto_misses

    out = {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "shop": SHOP,
        "sealedCatalogSize": len(catalog),
        "checked": len(all_flags) + len(all_misses),
        "matched": len(all_flags),
        "unmatched": len(all_misses),
        "deals": deals,
        "checkedNoDeal": [f for f in all_flags if not f["deal"]],
        "misses": all_misses,
    }
    json.dump(out, open(os.path.join(ROOT, "shop_burbankcards.json"), "w"), indent=1, ensure_ascii=False)
    print(f"checked {out['checked']} items ({len(deals)} deals, {len(all_misses)} not found on site) — "
          f"see shop_burbankcards.json")
    for d in deals:
        label = d.get("title") or d.get("name")
        print(f"  DEAL: {label} — ${d['shopPrice']} <= ceiling ${d['ceiling']} — {d['url']}")


if __name__ == "__main__":
    main()
