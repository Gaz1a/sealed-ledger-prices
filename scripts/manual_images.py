"""Manual image overrides from jumbo_image_links.csv (Gaz-sourced). One image per jumbo id: first row that downloads and validates,
sent with the row's source_url as Referer. Resized to 200px tall, webp <= 12KB, saved to images/<id>.webp; index entry gets
source 'manual' + manual true, so product_images.py / the weekly job never replaces or removes it. Report: images/manual_report.json"""
import csv, io, json, os, sys, urllib.request, urllib.parse, urllib.error, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from card_images import ld, IMG, ROOT
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MAXB = 12 * 1024
UA2 = "sealed-ledger-prices/1.0 (personal collection tracker; https://github.com/Gaz1a/sealed-ledger-prices)"
def q(u): return urllib.parse.quote(u, safe=":/?&=%#@+,;~!*'()[]-._")
def fetch(url, ref):
    last = None
    for ua, rf in ((UA, ref), (UA2, None), (UA2, ref), (UA, None)):
        h = {"User-Agent": ua, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
        if rf: h["Referer"] = q(rf)
        try:
            r = urllib.request.urlopen(urllib.request.Request(q(url), headers=h), timeout=40); return r.read(), None
        except urllib.error.HTTPError as e: last = f"HTTP {e.code}"
        except Exception as e: last = type(e).__name__ + ":" + str(e)[:60]
    return None, last
def webp(raw):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        if getattr(im, "n_frames", 1) > 1: im.seek(0)
        im = im.convert("RGBA"); bg = Image.new("RGB", im.size, "white"); bg.paste(im, mask=im.split()[3]); im = bg
    except Exception as e: return None, "undecodable"
    w, h = im.size
    if min(w, h) < 90: return None, "too small %dx%d" % (w, h)
    if not 0.25 <= w / h <= 4: return None, "odd shape %dx%d" % (w, h)
    th = 200; tw = max(1, round(w * th / h)); im = im.resize((tw, th))
    for scale in (1.0, 0.9, 0.8, 0.7, 0.6):
        for q in (85, 75, 65, 55, 45):
            b = io.BytesIO(); im.resize((max(1, int(tw * scale)), max(1, int(th * scale)))).save(b, "WEBP", quality=q, method=6)
            if b.tell() <= MAXB: return b.getvalue(), None
    return None, "cannot shrink under 12KB"
def main():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "jumbo_image_links.csv"), encoding="utf-8-sig")))
    by = collections.OrderedDict()
    for r in rows: by.setdefault(r["id"], []).append(r)
    idx = ld("images/index.json", {}); un = {u["id"]: u for u in ld("images/unmatched_products.json", [])}
    rep = {"ok": [], "failed": []}
    for jid, rs in by.items():
        cur = idx.get(jid) or {}
        if cur.get("manual") and cur.get("matched") and os.path.exists(os.path.join(IMG, jid + ".webp")):
            rep["ok"].append({"id": jid, "kept": True}); continue
        errs = []; done = False
        for r in rs:
            raw, err = fetch(r["image_url"], r["source_url"])
            host = urllib.parse.urlparse(r["image_url"]).netloc
            if raw is None: errs.append({"host": host, "error": err, "url": r["image_url"]}); continue
            data, bad = webp(raw)
            if data is None: errs.append({"host": host, "error": "rejected: " + bad, "url": r["image_url"]}); continue
            open(os.path.join(IMG, jid + ".webp"), "wb").write(data)
            kind = "jumbo-card" if r.get("image_type") == "jumbo_insert_scan" else "jumbo-box"
            idx[jid] = {"file": f"images/{jid}.webp", "tcgdexId": None, "matched": True, "source": "manual", "kind": kind, "manual": True,
                        "imageUrl": r["image_url"], "sourceUrl": r["source_url"], "variant": r.get("variant") or None, "variantsAvailable": len(rs)}
            un.pop(jid, None); rep["ok"].append({"id": jid, "host": host, "bytes": len(data), "rowUsed": rs.index(r) + 1, "rows": len(rs)}); done = True; break
        if not done: rep["failed"].append({"id": jid, "errors": errs})
    json.dump(dict(sorted(idx.items())), open(os.path.join(IMG, "index.json"), "w"), indent=1)
    json.dump(sorted(un.values(), key=lambda u: u["id"]), open(os.path.join(IMG, "unmatched_products.json"), "w"), indent=1)
    rep["summary"] = {"ids": len(by), "matched": len(rep["ok"]), "failed": len(rep["failed"]),
                      "blockedHosts": dict(collections.Counter(e["host"] for f in rep["failed"] for e in f["errors"]))}
    json.dump(rep, open(os.path.join(IMG, "manual_report.json"), "w"), indent=1)
    print(rep["summary"])
if __name__ == "__main__": main()
