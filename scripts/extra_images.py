"""Pictures for ledger rows the regular image jobs cannot match (new rows, Japanese freebies, foreign sealed, the 151 binder).
data/extra_images.json maps ledger id -> {pid} (TCGplayer product image) | {jp: set code, number} (Japanese card via tcgcsv cat 85)
| {en_group, name} (English sealed by group + name) | {url, ref}. Saved like manual images (manual true, never replaced)."""
import json, os, sys, re, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manual_images import fetch, webp
from card_images import ROOT, IMG
def tj(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sealed-ledger/1.0"}), timeout=60) as r: return json.load(r)
def group_products(cat, test):
    for g in tj(f"https://tcgcsv.com/tcgplayer/{cat}/groups")["results"]:
        if test(g["name"]): yield g, tj(f"https://tcgcsv.com/tcgplayer/{cat}/{g['groupId']}/products")["results"]
def num(p): return next((e.get("value") for e in p.get("extendedData", []) if e.get("name") == "Number"), "")
spec = json.load(open(os.path.join(ROOT, "data/extra_images.json")))
idxp = os.path.join(IMG, "index.json"); idx = json.load(open(idxp))
report = {}
for lid, s in spec.items():
    if idx.get(lid, {}).get("matched") and not s.get("redo"): report[lid] = "already has a picture"; continue
    url, ref, src = None, None, None
    try:
        if "pid" in s:
            url, src = f"https://tcgplayer-cdn.tcgplayer.com/product/{s['pid']}_in_400x400.jpg", f"tcgplayer {s['pid']}"
        elif "jp" in s:
            for g, ps in group_products(85, lambda n: n.upper().startswith(s["jp"].upper() + ":")):
                p = next((p for p in ps if num(p).split("/")[0].lstrip("0") == s["number"].split("/")[0].lstrip("0")), None)
                if p: url, src = p.get("imageUrl", "").replace("_200w", "_in_400x400"), f"tcgplayer {p['productId']} ({g['name']})"; break
        elif "en_group" in s:
            for g, ps in group_products(3, lambda n: n.endswith(s["en_group"]) or n.split(": ", 1)[-1] == s["en_group"]):
                for nm in (s["name"], s.get("fallback_name")):
                    p = next((p for p in ps if nm and nm.lower() in p["name"].lower() and not (s.get("exclude") and s["exclude"].lower() in p["name"].lower())), None)
                    if p: url, src = p.get("imageUrl", "").replace("_200w", "_in_400x400"), f"tcgplayer {p['productId']} {p['name']}"; break
                if url: break
        else:
            url, ref, src = s["url"], s.get("ref"), "manual url"
        if not url: report[lid] = "no image found"; continue
        raw, err = fetch(url, ref)
        if not raw: report[lid] = f"download failed {err}"; continue
        b, err = webp(raw)
        if not b: report[lid] = f"bad image {err}"; continue
        open(os.path.join(IMG, f"{lid}.webp"), "wb").write(b)
        idx[lid] = {"file": f"images/{lid}.webp", "matched": True, "source": src, "manual": True, "kind": "card" if lid.startswith("s-") else "sealed", "url": url}
        report[lid] = f"ok ({src})"
    except Exception as e:
        report[lid] = f"error {type(e).__name__}: {str(e)[:80]}"
json.dump(idx, open(idxp, "w"), indent=1, ensure_ascii=False)
json.dump(report, open(os.path.join(IMG, "extra_report.json"), "w"), indent=1)
print(json.dumps(report, indent=1))
