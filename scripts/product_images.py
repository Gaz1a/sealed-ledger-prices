"""Thumbnails for sealed products (tracked.json non-single entries) and jumbos (jumbo_ids.json / jumbo_catalogue.json).
Sources in order: TCGplayer product image by product id (sealedId first for jumbos, cardId only when no sealed id),
then Bulbapedia (exact page-title match only), else unmatched with a reason.
Output: images/<id>.webp (<=12KB, long side ~200px), images/index.json (+source, kind), images/unmatched_products.json."""
import json, os, re, io, sys, hashlib, collections, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_images as ci
from card_images import get, norm, ld, IMG, ROOT

MAXB = 12 * 1024; LONG = 200
def to_webp(raw):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception: return None, "undecodable image"
    w, h = im.size
    if min(w, h) < 90: return None, "image too small (%dx%d)" % (w, h)
    if not (0.3 <= w / h <= 3.2): return None, "odd shape (%dx%d)" % (w, h)
    f = LONG / max(w, h)
    if f < 1: im = im.resize((max(1, round(w * f)), max(1, round(h * f))))
    w, h = im.size
    for scale in (1.0, 0.9, 0.8, 0.7):
        for q in (80, 70, 60, 50, 40):
            b = io.BytesIO(); im.resize((max(1, int(w * scale)), max(1, int(h * scale)))).save(b, "WEBP", quality=q, method=6)
            if b.tell() <= MAXB: return b.getvalue(), None
    return None, "cannot shrink under 12KB"

def tcgp(pid):
    raw = get(f"https://product-images.tcgplayer.com/fit-in/437x437/{pid}.jpg", raw=True, tries=2)
    return raw

def bulba(title):
    """Exact page-title match only (title normalised, a trailing '(TCG)' style suffix ignored)."""
    api = "https://bulbapedia.bulbagarden.net/w/api.php?"
    j = get(api + urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": title, "srlimit": 5, "format": "json"}))
    want = norm(re.sub(r"\s*\([^)]*\)", "", title))
    for r in ((j or {}).get("query") or {}).get("search", []):
        if norm(re.sub(r"\s*\([^)]*\)", "", r["title"])) == want:
            p = get(api + urllib.parse.urlencode({"action": "query", "titles": r["title"], "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": 400, "format": "json"}))
            for pg in ((p or {}).get("query") or {}).get("pages", {}).values():
                u = (pg.get("thumbnail") or {}).get("source")
                if u: return get(u, raw=True), r["title"]
    return None, None

def main():
    tr = ld("tracked.json", {}); ji = ld("jumbo_ids.json", {}); cat = {c["id"]: c for c in ld("jumbo_catalogue.json", [])}
    idx = ld("images/index.json", {}); un = {u["id"]: u for u in ld("images/unmatched_products.json", [])}
    singles = {k for k in tr if k.startswith("k-") or ci.is_single(k, tr[k].get("title", ""))}
    jobs = []                                  # (id, kind, title, [(pid, label)])
    for k, e in tr.items():
        if k not in singles: jobs.append((k, "sealed", e.get("title", ""), [(e["productId"], "product")]))
    for jid in cat:
        v = ji.get(jid, {}); c = cat[jid]; title = v.get("title") or c.get("title") or jid
        sid = v.get("sealedId"); cid = v.get("cardId"); why = None
        if not sid and v.get("sealedIds"):
            if v.get("sealedMode") == "range": sid = v["sealedIds"][0]
            else: why = "multi-product entry (%s): no single sealed image" % v.get("sealedMode")
        if not sid and not cid and v.get("cardIds") and v.get("cardMode") == "range": cid = v["cardIds"][0]
        pids = [(sid, "jumbo-box")] if sid else ([(cid, "jumbo-card")] if cid else [])
        jobs.append((jid, "jumbo-box" if sid else "jumbo-card", title, pids, why))
    jobs = [j if len(j) == 5 else j + (None,) for j in jobs]
    todo = [j for j in jobs if not (idx.get(j[0]) or {}).get("matched") or not os.path.exists(os.path.join(IMG, j[0] + ".webp"))]
    print("jobs", len(jobs), "todo", len(todo))
    raws = {}
    for jid, kind, title, pids, why in todo:
        reasons = [why] if why else []; done = False
        for pid, label in pids:
            raw = tcgp(pid)
            if not raw: reasons.append(f"tcgplayer {pid}: no image"); continue
            raws[jid] = (pid, hashlib.md5(raw).hexdigest(), raw)
            data, bad = to_webp(raw)
            if not data: reasons.append(f"tcgplayer {pid}: {bad}"); continue
            open(os.path.join(IMG, jid + ".webp"), "wb").write(data)
            idx[jid] = {"file": f"images/{jid}.webp", "tcgdexId": None, "matched": True, "source": "tcgplayer", "kind": kind, "tcgProductId": pid}; un.pop(jid, None); done = True; break
        if done: continue
        if kind != "sealed" or True:
            raw, page = bulba(title) if title else (None, None)
            if raw:
                data, bad = to_webp(raw)
                if data:
                    open(os.path.join(IMG, jid + ".webp"), "wb").write(data)
                    idx[jid] = {"file": f"images/{jid}.webp", "tcgdexId": None, "matched": True, "source": "bulbapedia", "kind": kind, "bulbapediaPage": page}; un.pop(jid, None); continue
                reasons.append("bulbapedia image rejected: " + str(bad))
            else: reasons.append("bulbapedia: no exact page match")
        idx[jid] = {"file": None, "tcgdexId": None, "matched": False, "source": None, "kind": kind}
        un[jid] = {"id": jid, "kind": kind, "title": title, "reason": " | ".join(reasons)}
    # identical bytes for different products = placeholder: drop them
    byh = collections.defaultdict(set)
    for jid, (pid, h, raw) in raws.items(): byh[h].add(pid)
    for h, pids in byh.items():
        if len(pids) > 1:
            for jid, (pid, hh, raw) in raws.items():
                if hh == h and (idx.get(jid) or {}).get("source") == "tcgplayer":
                    try: os.remove(os.path.join(IMG, jid + ".webp"))
                    except OSError: pass
                    j = next(x for x in jobs if x[0] == jid)
                    idx[jid] = {"file": None, "tcgdexId": None, "matched": False, "source": None, "kind": idx[jid]["kind"]}
                    un[jid] = {"id": jid, "kind": idx[jid]["kind"], "title": j[2], "reason": "identical image shared by %d different products (placeholder)" % len(pids)}
    valid = {j[0] for j in jobs}
    for k in list(un):
        if k not in valid: un.pop(k)
    json.dump(dict(sorted(idx.items())), open(os.path.join(IMG, "index.json"), "w"), indent=1)
    json.dump(sorted(un.values(), key=lambda u: u["id"]), open(os.path.join(IMG, "unmatched_products.json"), "w"), indent=1)
    for kind in ("sealed", "jumbo-box", "jumbo-card"):
        m = sum(1 for v in idx.values() if v.get("kind") == kind and v["matched"]); u = sum(1 for v in un.values() if v["kind"] == kind)
        by = collections.Counter(v.get("source") for v in idx.values() if v.get("kind") == kind and v["matched"])
        print(kind, "matched", m, "unmatched", u, dict(by))
if __name__ == "__main__": main()
