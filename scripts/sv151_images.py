"""Card thumbnails for English SV 151 (sv151_lines.json): one webp per unique productId -> images/sv151/<pid>.webp, index entries keyed by str(pid).
Sources: TCGplayer 437x610 product image; fallbacks: 437x437 variant, then tcgdex (sv03.5 + card number). Only missing ones are fetched, so it is safe to re-run."""
import json, os, io, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from card_images import get, ld, IMG, ROOT
from PIL import Image
W = 120; MAXB = 15 * 1024
D = os.path.join(IMG, "sv151"); os.makedirs(D, exist_ok=True)
def webp(raw):
    try: im = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception: return None
    w, h = im.size
    if w < 90 or not (0.55 <= w / h <= 0.85): return None      # card-shaped only
    im = im.resize((W, round(h * W / w)), Image.LANCZOS)
    for q in (80, 70, 60, 50): 
        b = io.BytesIO(); im.save(b, "WEBP", quality=q, method=6)
        if b.tell() <= MAXB: return b.getvalue()
def tcgdex(num):
    n = num.split("/")[0].lstrip("0") or "0"
    j = get(f"https://api.tcgdex.net/v2/en/sets/sv03.5/{n.zfill(3)}")
    if isinstance(j, dict) and j.get("image"): return get(j["image"] + "/low.webp", raw=True, tries=2)
lines = ld("sv151_lines.json", []); idx = ld("images/index.json", {}); miss = {}
uniq = {}
for l in lines: uniq.setdefault(l["productId"], l)
saved = 0; new = 0
for pid, l in sorted(uniq.items()):
    k = str(pid); fp = os.path.join(D, f"{pid}.webp")
    if os.path.exists(fp) and (idx.get(k) or {}).get("matched"): saved += 1; continue
    data = src = None
    for u, s in ((f"https://product-images.tcgplayer.com/fit-in/437x610/{pid}.jpg", "tcgplayer"), (f"https://product-images.tcgplayer.com/fit-in/437x437/{pid}.jpg", "tcgplayer-437x437")):
        raw = get(u, raw=True, tries=2)
        if raw: data = webp(raw)
        if data: src = s; break
    if not data and l.get("number"):
        raw = tcgdex(l["number"])
        if raw: data = webp(raw); src = "tcgdex"
    if data:
        open(fp, "wb").write(data); saved += 1; new += 1
        idx[k] = {"file": f"images/sv151/{pid}.webp", "tcgdexId": None, "matched": True, "source": src, "kind": "sv151", "name": l.get("name")}
    else: miss[k] = {"id": k, "name": l.get("name"), "number": l.get("number"), "reason": "no usable image from tcgplayer or tcgdex"}
json.dump(idx, open(os.path.join(IMG, "index.json"), "w"), indent=1, ensure_ascii=False)
json.dump(list(miss.values()), open(os.path.join(IMG, "sv151_missing.json"), "w"), indent=1)
print("unique", len(uniq), "saved", saved, "new", new, "missing", sorted(miss))
