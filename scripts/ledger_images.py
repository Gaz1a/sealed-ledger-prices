"""Fills every ledger id that still has no image, and reports what is still missing.
Id universe = tracked.json + jumbo_catalogue.json + booklet rows + ledger_image_map.json + ledger_ids.json (optional export of the ledger's ids, list or {id:..}).
Missing = id not matched in images/index.json. Sources per ledger_image_map.json (alias / tcgplayer / tcgdexBase / tcgcsv / booklet).
Booklets: Open Library cover by ISBN, then the photo of a live/seen sealed Portuguese eBay listing for that row (needs EBAY_* env).
Manual overrides and existing matched entries are never overwritten. Output: images/<id>.webp, images/index.json, images/missing_report.json."""
import json, os, io, re, sys, base64, shutil, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_images as ci
from card_images import get, ld, norm, IMG, ROOT
import product_images as pi
idx = ld("images/index.json", {}); spec = ld("ledger_image_map.json", {}); spec.pop("_note", None)
ids = set(ld("tracked.json", {})) | {c["id"] for c in ld("jumbo_catalogue.json", [])} | set(spec) | set(ld("booklet_refs.json", {"items": {}})["items"])
extra = ld("ledger_ids.json", [])
ids |= set(extra if isinstance(extra, list) else extra.keys() if isinstance(extra, dict) else [])
def have(i): return bool((idx.get(i) or {}).get("matched")) and os.path.exists(os.path.join(IMG, i + ".webp"))
def put(i, data, **meta):
    open(os.path.join(IMG, i + ".webp"), "wb").write(data)
    idx[i] = {"file": f"images/{i}.webp", "tcgdexId": meta.pop("tcgdexId", None), "matched": True, **meta}
reasons = {}
def card_or_box(raw, kind):
    d, why = (ci.to_webp(raw) if kind in ("base-set-card", "slab-card", "sv-card") else pi.to_webp(raw))
    if not d and kind == "slab-card": d, why = pi.to_webp(raw)       # slabs/odd shapes: product-style thumbnail
    return d, why
_base = {}
def base_cards():
    if not _base:
        j = get("https://api.tcgdex.net/v2/en/sets/base1") or {}
        for c in j.get("cards", []): _base[norm(c["name"])] = c
    return _base
tok = None
if os.environ.get("EBAY_CLIENT_ID"):
    r = get("https://api.ebay.com/identity/v1/oauth2/token") if False else None
    import urllib.request
    try:
        rq = urllib.request.Request("https://api.ebay.com/identity/v1/oauth2/token", data=urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode(),
              headers={"Authorization": "Basic " + base64.b64encode(f"{os.environ['EBAY_CLIENT_ID']}:{os.environ['EBAY_CLIENT_SECRET']}".encode()).decode(), "Content-Type": "application/x-www-form-urlencoded"})
        tok = json.load(urllib.request.urlopen(rq, timeout=40)).get("access_token")
    except Exception as e: print("ebay token failed", type(e).__name__)
def ebay_img(item_id):
    if not tok: return None
    import urllib.request
    try:
        rq = urllib.request.Request(f"https://api.ebay.com/buy/browse/v1/item/v1%7C{item_id}%7C0", headers={"Authorization": "Bearer " + tok, "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"})
        j = json.load(urllib.request.urlopen(rq, timeout=40))
        return (j.get("image") or {}).get("imageUrl")
    except Exception: return None
isbns = ld("devir_retail_urls.json", {}).get("isbn", {})
lst = ld("booklet_listings.json", {"listings": {}})["listings"]
def fill(i, s):
    kind = s.get("kind") or "sealed"
    if "alias" in s:
        a = s["alias"]
        if have(a): shutil.copyfile(os.path.join(IMG, a + ".webp"), os.path.join(IMG, i + ".webp")); idx[i] = {**idx[a], "file": f"images/{i}.webp", "source": "alias:" + a}; return True
        reasons[i] = f"alias {a} has no image yet"; return False
    if "tcgplayer" in s:
        pid = s["tcgplayer"]; raw = get(f"https://product-images.tcgplayer.com/fit-in/437x437/{pid}.jpg", raw=True, tries=2)
        if not raw: reasons[i] = f"tcgplayer {pid}: no image"; return False
        d, why = card_or_box(raw, kind)
        if not d: reasons[i] = f"tcgplayer {pid}: {why}"; return False
        put(i, d, source="tcgplayer", kind=kind, tcgProductId=pid); return True
    if "tcgdexBase" in s:
        c = base_cards().get(norm(s["tcgdexBase"]))
        if not c or not c.get("image"): reasons[i] = f"base1 has no card named {s['tcgdexBase']}"; return False
        raw = get(c["image"] + "/low.webp", raw=True)
        d, why = ci.to_webp(raw) if raw else (None, "download failed")
        if not d: reasons[i] = f"tcgdex {c['id']}: {why}"; return False
        put(i, d, tcgdexId=c["id"], source="tcgdex", kind=kind); return True
    if "tcgcsv" in s:
        q = s["tcgcsv"]; ps = (get(f"https://tcgcsv.com/tcgplayer/3/{q['group']}/products") or {}).get("results") or []
        if not ps: reasons[i] = f"group {q['group']} not listed on tcgcsv yet"; return False
        hit = []
        for p in ps:
            n = p["name"].lower(); num = next((e.get("value") for e in p.get("extendedData", []) if e.get("name") == "Number"), "") or ""
            if q.get("number") and num.replace(" ", "") != q["number"]: continue
            if q.get("include") and q["include"] not in n: continue
            if any(x in n for x in q.get("exclude", [])): continue
            hit.append(p)
        if len(hit) != 1: reasons[i] = f"{len(hit)} candidates in group {q['group']} (need exactly 1)"; return False
        pid = hit[0]["productId"]; raw = get(f"https://product-images.tcgplayer.com/fit-in/437x437/{pid}.jpg", raw=True, tries=2)
        d, why = card_or_box(raw, kind) if raw else (None, "no image")
        if not d: reasons[i] = f"tcgplayer {pid}: {why}"; return False
        put(i, d, source="tcgplayer", kind=kind, tcgProductId=pid); return True
    if s.get("booklet"):
        tried = []
        isbn = isbns.get(i)
        if isbn:
            raw = get(f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false", raw=True, tries=1)
            if raw:
                d, why = pi.to_webp(raw)
                if d: put(i, d, source="openlibrary", kind="booklet", isbn=isbn); return True
                tried.append("openlibrary: " + str(why))
            else: tried.append("openlibrary: no cover")
        for iid, l in sorted(((k, v) for k, v in lst.items() if v["row"] == i), key=lambda kv: (not kv[1].get("sealed"), kv[1].get("lastSeen") or ""), reverse=False):
            if not l.get("sealed"): continue
            u = ebay_img(iid)
            if not u: continue
            raw = get(u, raw=True, tries=2); d, why = pi.to_webp(raw) if raw else (None, "download failed")
            if d: put(i, d, source="ebay-listing", kind="booklet", sourceUrl=l.get("url")); return True
            tried.append(f"ebay {iid}: {why}")
        reasons[i] = "; ".join(tried) or ("no sealed listing photo available yet" if tok else "no cover found; no eBay credentials in this run")
        return False
    reasons[i] = "no source configured in ledger_image_map.json"; return False
for i in sorted(ids):
    if have(i): continue
    if i in spec:
        try: fill(i, spec[i])
        except Exception as e: reasons[i] = f"error {type(e).__name__}"
json.dump(idx, open(os.path.join(IMG, "index.json"), "w"), indent=1, ensure_ascii=False)
missing = sorted(i for i in ids if not have(i))
for i in missing: reasons.setdefault(i, "no source configured in ledger_image_map.json" if i not in spec else "unresolved")
rep = {"idsChecked": len(ids), "missing": [{"id": i, "reason": reasons[i]} for i in missing]}
json.dump(rep, open(os.path.join(IMG, "missing_report.json"), "w"), indent=1)
print("checked", len(ids), "missing", len(missing)); [print(" ", i, "-", reasons[i]) for i in missing]
