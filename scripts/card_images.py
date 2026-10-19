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

CARD_RATIO = (0.66, 0.78)
def to_webp(raw):
    """any image bytes -> webp <= MAXB at card size, or (None, reason). Rejects non-card aspect ratios / tiny images."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception: return None, "undecodable image"
    w, h = im.size
    if w < 120 or h < 160: return None, "image too small (%dx%d)" % (w, h)
    if not (CARD_RATIO[0] <= w / h <= CARD_RATIO[1]): return None, "not card-shaped (%dx%d)" % (w, h)
    if w > 245: im = im.resize((245, round(h * 245 / w)))
    w, h = im.size
    for scale in (1.0, 0.9, 0.8, 0.7):
        for q in (80, 70, 60, 50, 40):
            b = io.BytesIO(); im.resize((int(w * scale), int(h * scale))).save(b, "WEBP", quality=q, method=6)
            if b.tell() <= MAXB: return b.getvalue(), None
    return None, "cannot shrink under 15KB"

def code_of(gname):
    m = re.match(r"\s*([A-Za-z0-9\-]{2,8}):", gname or ""); return m.group(1).lower() if m else None
def tcgdex_loose(lang, gname, name, num, den):
    """code-based set match (e.g. 'S7R: ...' -> set id s7r) and name-only search + number check."""
    if not num: return None, "no card number"
    code = code_of(gname); d = int(re.sub(r"\D", "", den)) if den and re.sub(r"\D", "", den) else None
    for lg in ([lang] + (["en"] if lang == "ja" else []) + (["ja"] if lang == "en" else [])):
        if code:
            for s in sets(lg):
                if s["id"].lower() == code:
                    for c in detail(lg, s["id"]).get("cards", []):
                        if numkey(c.get("localId")) == numkey(num) and (lg == "ja" or names_match(c.get("name"), name)) and c.get("image"):
                            if d and (s.get("cardCount") or {}).get("official") not in (d, None): continue
                            return (c, s["id"], lg), None
        if lg == "en" and name:
            r = get(f"{API}/en/cards?name={urllib.parse.quote(name)}") or []
            hits = [c for c in r if numkey(c.get("localId")) == numkey(num) and names_match(c.get("name"), name) and c.get("image")]
            if d:
                f = []
                for c in hits:
                    sid = c["id"].rsplit("-", 1)[0]; sd = next((x for x in sets("en") if x["id"] == sid), None)
                    if sd and (sd.get("cardCount") or {}).get("official") == d: f.append(c)
                hits = f
            if len(hits) == 1: return (hits[0], hits[0]["id"].rsplit("-", 1)[0], "en"), None
    return None, "tcgdex loose: no unique match"

def ptcg(gname, name, num, den, bracket):
    if not (name and num): return None, "pokemontcg: need name+number"
    q = f'name:"{name.replace(chr(34), "")}" number:"{numkey(num)}"'
    j = get("https://api.pokemontcg.io/v2/cards?" + urllib.parse.urlencode({"q": q, "pageSize": 25}))
    if not j: return None, "pokemontcg: no response"
    keys = {setkey(gname), setkey(bracket)} - {""}
    for k in list(keys): keys |= {setkey(x) for x in []}
    d = int(re.sub(r"\D", "", den)) if den and re.sub(r"\D", "", den) else None
    hits = []
    for c in j.get("data", []):
        st = c.get("set") or {}
        if numkey(c.get("number")) != numkey(num) or not names_match(c.get("name"), name): continue
        okset = setkey(st.get("name")) in keys or (d and st.get("printedTotal") == d) or (d is None and any(k and k in setkey(st.get("name")) for k in keys))
        if okset and (c.get("images") or {}).get("small"): hits.append(c)
    if len(hits) == 1: return hits[0], None
    return None, "pokemontcg: %d candidates" % len(hits)

_ph = {}
def tcgplayer(pid):
    raw = get(f"https://product-images.tcgplayer.com/fit-in/437x437/{pid}.jpg", raw=True, tries=2)
    if not raw: return None, "tcgplayer: no image"
    if "ph" not in _ph:
        _ph["ph"] = {hash(x) for x in [get("https://product-images.tcgplayer.com/fit-in/437x437/1.jpg", raw=True, tries=1)] if x}
    if hash(raw) in _ph["ph"]: return None, "tcgplayer: placeholder"
    return raw, None

def save(k, data, idx, un, tcgdex_id, source, extra=None):
    open(os.path.join(IMG, k + ".webp"), "wb").write(data)
    idx[k] = {"file": f"images/{k}.webp", "tcgdexId": tcgdex_id, "matched": True, "source": source, **(extra or {})}; un.pop(k, None)

def main():
    tr = ld("tracked.json", {}); gm = ld("group-map.json", {})
    idx = ld("images/index.json", {}); un = {u["id"]: u for u in ld("images/unmatched.json", [])}
    for v in idx.values():
        if v.get("matched") and not v.get("source"): v["source"] = "tcgdex"
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
        reasons = []
        # 1. tcgdex strict, then loose
        card, why = find_card(lang, gname or "", name, num, den, br)
        if lang == "ja" and not card: card, why = find_card("en", gname or "", name, num, den, br)
        if card and card.get("image"):
            raw = get(card["image"] + "/low.webp", raw=True); data = shrink(raw) if raw else None
            if data: save(k, data, idx, un, card["id"], "tcgdex"); continue
            reasons.append("tcgdex image download/shrink failed")
        else: reasons.append(why if not card else "tcgdex has no image")
        hit, why = tcgdex_loose(lang, gname, name, num, den)
        if hit:
            c, sid, lg = hit; raw = get(c["image"] + "/low.webp", raw=True); data = shrink(raw) if raw else None
            if data: save(k, data, idx, un, c["id"], "tcgdex"); continue
        reasons.append(why or "tcgdex loose: download failed")
        # 2. pokemontcg.io (English-language cards only)
        c, why = ptcg(gname, name, num, den, br)
        if c:
            raw = get(c["images"]["small"], raw=True); data, bad = to_webp(raw) if raw else (None, "download failed")
            if data: save(k, data, idx, un, None, "pokemontcg", {"pokemontcgId": c["id"]}); continue
            reasons.append("pokemontcg image rejected: " + str(bad))
        else: reasons.append(why)
        # 3. TCGplayer product image
        raw, why = tcgplayer(e["productId"])
        if raw:
            data, bad = to_webp(raw)
            if data: save(k, data, idx, un, None, "tcgplayer", {"tcgProductId": e["productId"]}); continue
            reasons.append("tcgplayer image rejected: " + str(bad))
        else: reasons.append(why)
        idx[k] = {"file": None, "tcgdexId": None, "matched": False, "source": None}
        un[k] = {"id": k, "title": title, "group": gname, "reason": " | ".join(reasons)}
    for k in list(un):
        if k not in tr: un.pop(k)
    json.dump(dict(sorted(idx.items())), open(os.path.join(IMG, "index.json"), "w"), indent=1)
    json.dump(sorted(un.values(), key=lambda u: u["id"]), open(os.path.join(IMG, "unmatched.json"), "w"), indent=1)
    import collections
    print("by source", dict(collections.Counter(v.get("source") for v in idx.values() if v["matched"])), "unmatched", len(un))
if __name__ == "__main__": main()
