"""Card thumbnails from tcgdex. For every single-card entry in tracked.json (Kanto 151 'k-*' first, then the rest)
find the card on tcgdex by set + number (+ name), download <image>/low.webp, keep it <= ~15KB, save images/<ledgerId>.webp.
Writes images/index.json {ledgerId: {file, tcgdexId, matched}} and images/unmatched.json (id, title, reason).
Weekly: only entries missing from the index (or previously unmatched) are processed."""
import json, os, re, io, sys, time, urllib.request, urllib.parse

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
IMG = os.path.join(ROOT, "images"); os.makedirs(IMG, exist_ok=True)
API = "https://api.tcgdex.net/v2"
MAXB = 15 * 1024
UA = {"User-Agent": "sealed-ledger-prices/1.0"}
def ld(n, d):
    try: return json.load(open(os.path.join(ROOT, n)))
    except Exception: return d
def get(url, raw=False, tries=3):
    for i in range(tries):
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()
            return b if raw else json.loads(b)
        except Exception as e:
            if i == tries - 1: return None
            time.sleep(1.5)

def norm(s): return re.sub(r"[^a-z0-9]+", " ", (s or "").lower().replace("é", "e")).strip()
def setkey(n):
    n = re.sub(r"^[A-Za-z0-9\- ]{1,12}:\s*", "", n or "")          # "SV: ", "SWSH12: ", "ME01: "
    n = re.sub(r"^(SM|XY|BW|HGSS|DP|SV|SWSH|ME)\s*-\s*", "", n)
    n = re.sub(r"\((shadowless|1st edition|unlimited)[^)]*\)", "", n, flags=re.I)
    return norm(n)
def numkey(x):
    x = (x or "").strip().lower().replace(" ", "")
    return x.lstrip("0") or "0" if x.isdigit() else x
def parse(title):
    """-> name, number, denominator, bracket"""
    br = re.search(r"\[([^\]]+)\]", title); bracket = br.group(1) if br else None
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", title)
    num = den = None; cut = len(t)
    m = re.search(r"\b([A-Za-z]{0,6}-?\d{1,3}[A-Za-z]?)\s*/\s*([A-Za-z0-9-]+)", t)
    if m: num, den, cut = m.group(1), m.group(2), m.start()
    else:
        m = re.search(r"\b(MEP|XY|SM|SWSH|SVP|BW|HGSS|DP|TG)\s?-?(\d{1,3})\b", t)
        if m: num, cut = m.group(1) + m.group(2), m.start()
    name = t[:cut]
    name = re.split(r"\s[-—–]\s", name)[0].strip(" -—–")
    if not name: name = re.split(r"\s[-—–]\s", t)[0].strip()
    return name, num, den, bracket
def names_match(a, b):
    stop = {"ex", "gx", "v", "vmax", "vstar", "the", "of", "and", "s", "star", "holo"}
    wa = {w for w in norm(a).split() if w not in stop}; wb = {w for w in norm(b).split() if w not in stop}
    return bool(wa and wb and (wa & wb))

_sets = {}; _detail = {}; _groups = {}
def groups(cat):
    if cat not in _groups:
        j = get(f"https://tcgcsv.com/tcgplayer/{cat}/groups") or {}
        _groups[cat] = {g["groupId"]: g["name"] for g in j.get("results", [])}
    return _groups[cat]
def sets(lang):
    if lang not in _sets: _sets[lang] = get(f"{API}/{lang}/sets") or []
    return _sets[lang]
def detail(lang, sid):
    k = (lang, sid)
    if k not in _detail: _detail[k] = get(f"{API}/{lang}/sets/{sid}") or {}
    return _detail[k]

ALIAS = {"xy promos": ["xyp"], "sm promos": ["smp"], "wotc promo": ["basep"], "scarlet violet 151": ["sv03.5"], "swsh promos": ["swshp"], "sword shield promos": ["swshp"], "celebrations classic collection": ["cel25c"], "sv promos": ["svp"], "scarlet violet promos": ["svp"], "nintendo promos": ["np"], "hgss promos": ["hgssp"], "dp promos": ["dpp"], "bw promos": ["bwp"]}
def find_card(lang, gname, name, num, den, bracket):
    keys = [setkey(gname)] + ([setkey(bracket)] if bracket else [])
    cands = []
    for s in sets(lang):
        sk = setkey(s.get("name"))
        if any(k and (k == sk or (len(k) > 4 and (k in sk or sk in k) and len(sk) > 4)) for k in keys): cands.append(s)
    for k in keys:
        for sid in ALIAS.get(k, []):
            c0 = next((x for x in sets(lang) if x["id"] == sid), None)
            if c0: cands.insert(0, c0)
    exact = [x for x in cands if setkey(x["name"]) in keys]
    if exact: cands = exact + [x for x in cands if x not in exact and x["id"] in sum(ALIAS.values(), [])]
    cands = list(dict.fromkeys(x["id"] for x in cands)) and [next(y for y in cands if y["id"] == i) for i in dict.fromkeys(x["id"] for x in cands)]
    cands.sort(key=lambda s: (setkey(s["name"]) not in keys and s["id"] not in sum(ALIAS.values(), []), abs((s.get("cardCount", {}).get("official") or 0) - int(re.sub(r"\D", "", den) or 0)) if den else 0))
    if not cands and den and re.sub(r"\D", "", den):                       # fall back to sets whose official count equals the denominator
        d = int(re.sub(r"\D", "", den))
        cands = [s for s in sets(lang) if (s.get("cardCount") or {}).get("official") == d][:8]
    for s in cands[:6]:
        for c in detail(lang, s["id"]).get("cards", []):
            if num and numkey(c.get("localId")) == numkey(num) and (not name or names_match(c.get("name"), name)): return c, s["id"]
            if not num and name and norm(c.get("name")) == norm(name): return c, s["id"]
    return None, ("no set match for '%s'" % gname if not cands else "number %s not in %s" % (num, ",".join(s["id"] for s in cands[:3])))

def shrink(raw):
    if len(raw) <= MAXB: return raw
    try:
        from PIL import Image
    except Exception: return None
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = im.size
    for scale in (1.0, 0.9, 0.8, 0.7):
        for q in (80, 70, 60, 50, 40):
            b = io.BytesIO(); im.resize((int(w * scale), int(h * scale))).save(b, "WEBP", quality=q, method=6)
            if b.tell() <= MAXB: return b.getvalue()
    return None

def is_single(k, title):
    if re.search(r"booster|box|bundle|collection|tin\b|pack\b|display|elite trainer|etb|case|blister|deck|binder", title, re.I) and not re.search(r"\d+\s*/\s*[\w-]+|\b(MEP|XY|SM|SWSH|SVP|TG)\s?-?\d+", title): return False
    return bool(re.search(r"\d+\s*/\s*[\w-]+|\b(MEP|XY|SM|SWSH|SVP|TG)\s?-?\d+|\[", title)) or k.startswith("bs-")

def main():
    tr = ld("tracked.json", {}); gm = ld("group-map.json", {})
    idx = ld("images/index.json", {}); un = {u["id"]: u for u in ld("images/unmatched.json", [])}
    ids = sorted([k for k in tr if k.startswith("k-")]) + [k for k in tr if not k.startswith("k-") and is_single(k, tr[k].get("title", ""))]
    todo = [k for k in ids if not (idx.get(k) or {}).get("matched") or not os.path.exists(os.path.join(IMG, k + ".webp"))]
    print("singles", len(ids), "todo", len(todo))
    for k in todo:
        e = tr[k]; title = e.get("title", "")
        cat, gid = (gm.get(str(e["productId"])) or [3, None])
        lang = "ja" if cat == 85 or "japanese" in title.lower() else "en"
        gname = groups(cat).get(gid) if gid else None
        name, num, den, br = parse(title)
        if k.startswith("s-") and not num: name = title.split(" — ")[0]
        card, why = find_card(lang, gname or "", name, num, den, br)
        if lang == "ja" and not card: card, why = find_card("en", gname or "", name, num, den, br)
        if not card or not card.get("image"):
            idx[k] = {"file": None, "tcgdexId": card["id"] if card else None, "matched": False}
            un[k] = {"id": k, "title": title, "group": gname, "reason": why if not card else "tcgdex has no image"}; continue
        raw = get(card["image"] + "/low.webp", raw=True); data = shrink(raw) if raw else None
        if not data:
            idx[k] = {"file": None, "tcgdexId": card["id"], "matched": False}; un[k] = {"id": k, "title": title, "group": gname, "reason": "image download/shrink failed"}; continue
        open(os.path.join(IMG, k + ".webp"), "wb").write(data)
        idx[k] = {"file": f"images/{k}.webp", "tcgdexId": card["id"], "matched": True}; un.pop(k, None)
    for k in list(un):
        if k not in tr: un.pop(k)
    json.dump(dict(sorted(idx.items())), open(os.path.join(IMG, "index.json"), "w"), indent=1)
    json.dump(sorted(un.values(), key=lambda u: u["id"]), open(os.path.join(IMG, "unmatched.json"), "w"), indent=1)
    m = sum(1 for v in idx.values() if v["matched"]); km = sum(1 for k, v in idx.items() if k.startswith("k-") and v["matched"])
    print(f"matched {m}/{len(idx)}  (kanto {km}/151)  unmatched {len(un)}")
if __name__ == "__main__": main()
