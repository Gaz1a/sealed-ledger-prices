#!/usr/bin/env python3
"""Goldin auction scan (twice a week, free: Goldin's public lot search + tcgcsv + PriceCharting API).

Reads every live Pokemon lot on Goldin and writes goldin.json with:
  wants   - lots matching the ledger want list (wants_auto.json): sealed wants and GRADED single wants
            (raw single cards are never listed: Gaz only buys raw cards he can see graded).
  sealed  - multi-unit sealed lots (cases, case pairs, lots of 2+ boxes/ETBs/bundles) that are undervalued
            or overlooked, plus single sealed lots that are badly overlooked.
Each pick carries a value, the source of that value, Goldin's buyer premium, an estimated all-in cost at
the current bid, and maxBid: the highest hammer bid that still lands all-in at <= 85% of value.

--sold DAYS: also writes goldin_sold.json (sealed lots sold in the last DAYS days with what they would
have been flagged as), used as Goldin comps and as a check of the rules. Stdlib only; never prints secrets."""
import json, os, re, sys, time, datetime, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_market as sm
from concurrent.futures import ThreadPoolExecutor
try:
    from scan_ebay_wants import variant_ok
except Exception:
    variant_ok = lambda w, l: True

ROOT = sm.ROOT
API = "https://d1wu47wucybvr3.cloudfront.net/api/lots_v2"
HDR = {"User-Agent": "Mozilla/5.0 (sealed-ledger goldin scan)", "Origin": "https://goldin.co",
       "Referer": "https://goldin.co/", "Content-Type": "application/json"}
PCT = os.environ.get("PRICECHARTING_TOKEN", "")
NOW = datetime.datetime.now(datetime.timezone.utc)
DEAL = 0.85            # all-in target: at most 85% of value
SHIP = {"card": 15.0, "box": 25.0, "multi": 45.0}   # Goldin shipping estimates (labelled est.)

def post(search, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(API, data=json.dumps({"search": search}).encode(), headers=HDR)
            with urllib.request.urlopen(req, timeout=60) as r:
                return (json.load(r).get("searchalgolia") or {})
        except Exception as e:
            if i == tries - 1:
                print("goldin FAIL", e, file=sys.stderr); return {}
            time.sleep(3 * (i + 1))

def all_lots(extra, cap=6000):
    out, frm, total = [], 0, None
    while total is None or frm < min(total, cap):
        s = post(dict({"queryType": "Featured", "keyword": "pokemon", "from": frm, "size": 500}, **extra))
        lots = s.get("lots") or []
        total = s.get("total") or 0
        if not lots: break
        out += lots; frm += len(lots); time.sleep(1)
    return out

# ---------- titles ----------
SPECIAL_LOT = re.compile(r"signed|autograph|sketch|error|test print|misprint|off-center|miscut|proof|stamp|prerelease|staff", re.I)
PC_CACHE = {}
GRADE = re.compile(r"\b(PSA|CGC|BGS|Beckett|TAG|SGC)\b[^0-9]{0,30}?(\d{1,2}(?:\.5)?)\b", re.I)
JP = re.compile(r"japanese", re.I)
OTHER_LANG = re.compile(r"korean|chinese|french|german|italian|spanish|portuguese|thai|indonesian", re.I)
TYPES = [  # (key, regex in Goldin title, regex in TCGplayer product name)
    ("etb_pc", r"pok[eé]mon center elite trainer", r"pokemon center elite trainer"),
    ("etb", r"elite trainer box|\betb\b", r"elite trainer box"),
    ("bundle", r"booster bundle", r"booster bundle"),
    ("upc", r"ultra[- ]premium collection", r"ultra[- ]premium collection"),
    ("spc", r"super[- ]premium collection", r"super[- ]premium collection"),
    ("box", r"booster box|booster display", r"booster box(?! case)|booster display"),
    ("tin", r"\btin\b", r"\btin\b"),
    ("blister", r"blister", r"blister"),
    ("collection", r"premium collection|special collection|collection box|\bcollection\b", r"collection"),
    ("pack", r"booster pack|\bpack\b", r"booster pack"),
]
STOP = set("pokemon pokémon tcg factory sealed factory-sealed unopened the and of with a an english new box boxes "
           "booster boxes pack packs case cases pair lot display elite trainer bundle collection premium "
           "special ultra super tin tins blister set edition unlimited".split())
NUMWORD = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8, "ten": 10, "twelve": 12}

def toks(s):
    s = re.sub(r"[^a-z0-9& ]", " ", (s or "").lower().replace("é", "e"))
    return [t for t in s.split() if t and t not in STOP and not re.fullmatch(r"(19|20)\d\d", t) and t != "&"]

def head(title):
    t = re.split(r"\s+-\s+(?:possible|pop|includes|featuring|with)\b|\s+-\s+", title, 1, flags=re.I)[0]
    return t

def lot_type(title):
    for k, g, _ in TYPES:
        if re.search(g, title, re.I): return k
    return None

def quantity(title):
    """(units, is_case). Units = sealed units of lot_type; None if the lot does not say."""
    t = title.lower()
    for w, n in NUMWORD.items(): t = re.sub(rf"\b{w}\b", str(n), t)
    case = bool(re.search(r"\bcase\b", t))
    m = re.search(r"\((\d+)\s*(?:cases?\s*/\s*)?(\d+)?\s*(boxes|booster boxes|elite trainer boxes|etbs|bundles|booster bundles|tins|collections|displays)\)", t)
    if m: return (int(m.group(2) or m.group(1)), case)
    m = re.search(r"\b(\d+)\s*(?:x\s*)?(?:factory[- ]sealed\s+)?(?:booster boxes|boxes|elite trainer boxes|etbs|booster bundles|bundles|tins|collections)\b", t)
    if m: return (int(m.group(1)), case)
    m = re.search(r"lot of\s*\(?(\d+)\)?", t) or re.search(r"(?:\(|^)\s*\(?(\d+)\)?\s*(?:x\s)?\s*(?:19|20)\d\d", t)
    if m and int(m.group(1)) < 50: return (int(m.group(1)), case)
    m = re.search(r"\bx\s?(\d+)\b|\b(\d+)\s?x\b", t)
    if m: return (int(m.group(1) or m.group(2)), case)
    if case: return (None, True)
    return (1, False)

# ---------- catalog ----------
def catalog():
    jobs = []
    for cat in (3, 85):
        d = sm.get(f"{sm.BASE}/{cat}/groups")
        jobs += [(cat, g) for g in (d or {}).get("results", [])]
    rows = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for res in ex.map(sm.fetch_group, jobs): rows += res
    for r in rows:
        r["typ"] = next((k for k, _, p in TYPES if re.search(p, r["name"], re.I)), None)
        r["case"] = bool(re.search(r"\bcase\b", r["name"], re.I))
        r["tk"] = set(toks(r["name"])) | set(toks(re.sub(r"^[A-Za-z0-9\-\.]+:\s*", "", r["set"])))
        r["ptk"] = set(toks(r["name"]))
        r["year"] = int((r.get("pub") or "0")[:4] or 0)
    print(f"catalog {len(rows)} sealed products", file=sys.stderr)
    return rows

ERA = {"sword", "shield", "scarlet", "violet", "sun", "moon", "xy", "mega", "evolution", "black", "white", "sv", "swsh", "sm"}

def base_name(n):
    return re.sub(r"\s*\[.*?\]", "", n).strip().lower()

def bracket_toks(n):
    m = re.search(r"\[(.*?)\]", n)
    return set(toks(m.group(1))) if m else set()

def match_sealed(title, cat_rows):
    """Best TCGplayer sealed product for a Goldin sealed title -> (row with conservative 'value', None) or (None, reason).
    Conservative value = min(market, lowest listing) per unit. Variant products ([Koraidon], [Mew]...) must be named in
    the title, or all variants must price within 1.5x of each other (then the cheapest is used)."""
    if OTHER_LANG.search(title): return None, "non-English/Japanese language (no price feed)"
    typ = lot_type(title)
    if not typ: return None, "product type not recognised"
    cat = 85 if JP.search(title) else 3
    h = head(title)
    tl = set(toks(title))
    want = set(toks(re.sub(r"\(.*?\)", " ", h))) - {"japanese"}
    if not want: return None, "no set name in title"
    ym = re.match(r"\s*\(?\d*\)?\s*((?:19|20)\d\d)", h)
    year = int(ym.group(1)) if ym else None
    disp = bool(re.search(r"display", title, re.I))
    def cands(w):
        out = []
        for r in cat_rows:
            if r["cat"] != cat or r["case"] or r["typ"] != typ: continue
            if bool(re.search(r"display", r["name"], re.I)) != disp: continue
            if year and r["year"] and abs(r["year"] - year) > 1: continue
            if not w <= r["tk"]: continue
            extra = r["ptk"] - w - bracket_toks(r["name"])
            if extra: continue                      # product names something the title does not (e.g. 151)
            out.append(r)
        return out
    c = cands(want)
    if not c and want & ERA and want - ERA:
        c = cands(want - ERA)
    if not c: return None, "no confident TCGplayer match"
    named = [r for r in c if bracket_toks(r["name"]) and bracket_toks(r["name"]) <= tl]
    if named: c = named
    elif re.search(r"\([A-Za-z][A-Za-z '&-]*\)", h):     # title names a variant, e.g. "(Arceus)", that no product carries
        c = [r for r in c if not bracket_toks(r["name"])]
        if not c: return None, "named variant not on TCGplayer"
    groups = {}
    for r in c: groups.setdefault((r["gid"], base_name(r["name"])), []).append(r)
    if len(groups) > 1:
        if year:
            same = {k: v for k, v in groups.items() if v[0]["year"] == year}
            if len(same) == 1: groups = same
        if len(groups) > 1: return None, "ambiguous TCGplayer match"
    vs = list(groups.values())[0]
    vals = [min(r["market"], r["low"]) if r.get("low") else r["market"] for r in vs]
    if max(vals) > 1.5 * min(vals): return None, "variant not named and variants price differently"
    r = dict(vs[vals.index(min(vals))]); r["value"] = min(vals)
    if len(vs) > 1: r["name"] = base_name(r["name"]).title() + " (cheapest variant)"
    return r, None

# ---------- wants ----------
def wants():
    try: items = json.load(open(os.path.join(ROOT, "wants_auto.json"))).get("items", {})
    except Exception: return []
    out = []
    for wid, w in items.items():
        if (w.get("status") or "want") not in ("want",): continue
        t = w.get("title") or ""
        m = re.search(r"(\d+)\s*/\s*(\d+)", t)
        name = re.split(r"\s+\d+\s*/|\s*\(|\s+—|\s+-\s", re.sub(r"^\[JP\]\s*", "", t))[0].strip()
        out.append({"id": wid, "title": t, "set": w.get("set") or "", "kind": w.get("kind"), "num": m.group(1).lstrip("0") if m else None,
                    "name": name, "pid": str(w.get("tcgProductId") or ""), "market": w.get("market"), "target": w.get("target")})
    return out

def match_single_want(title, ws):
    tl = title.lower()
    for w in ws:
        if w["kind"] not in ("singles", "kanto") or not w["num"]: continue
        if not all(x in toks(tl) or x in tl for x in toks(w["name"])) or not toks(w["name"]): continue
        if not re.search(rf"#\s*0*{w['num']}\b|\b0*{w['num']}\s*/", title): continue
        st = [x for x in toks(w["set"]) if x not in ("base",)] or toks(w["set"])
        if st and not all(x in tl for x in st): continue
        if not variant_ok(w["title"], title): continue
        return w
    return None

def pc_graded(w, title, grade_co, grade):
    """PriceCharting price for this card at this grade, matched by TCGplayer id. (value, field) or (None, reason)."""
    if not PCT: return None, "no PriceCharting token"
    q = f"pokemon {w['name']} {w['set']} {w['num']}"
    if q not in PC_CACHE:
        prods = None
        for i in range(3):
            try:
                time.sleep(1.2)
                u = "https://www.pricecharting.com/api/products?" + urllib.parse.urlencode({"t": PCT, "q": q})
                with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "sealed-ledger/1.0"}), timeout=30) as r:
                    prods = json.load(r).get("products") or []; break
            except Exception as e:
                time.sleep(5 * (i + 1))
        PC_CACHE[q] = prods
    prods = PC_CACHE[q]
    if prods is None: return None, "PriceCharting unavailable"
    p = next((x for x in prods if str(x.get("tcg-id") or "") == w["pid"]), None)
    if not p: return None, "PriceCharting product not matched by TCGplayer id"
    g = float(grade)
    field = {10: "manual-only-price", 9.5: "box-only-price", 9: "graded-price", 8: "new-price", 7: "cib-price"}.get(g)
    if grade_co.upper() in ("BGS", "BECKETT") and g == 10: field = "bgs-10-price"
    if not field or not p.get(field): return None, f"no PriceCharting price for grade {grade}"
    note = "" if grade_co.upper() == "PSA" else f" (PSA {grade} price used for {grade_co} {grade}, unverified)"
    return p[field] / 100.0, f"PriceCharting {field}{note}"

# ---------- pricing ----------
def money(lot, value, kind):
    bp = (lot.get("buyer_premium") or 22.0) / 100.0
    ship = SHIP[kind]
    cur = float(lot.get("current_price") or 0)
    nxt = max(cur, float(lot.get("min_bid_price") or 0))
    allin = round(nxt * (1 + bp) + ship, 2)
    maxbid = int(max(0, (value * DEAL - ship) / (1 + bp)))
    return {"currentBid": cur, "bids": lot.get("number_of_bids") or 0, "buyerPremiumPct": round(bp * 100, 1),
            "shipEst": ship, "allInNow": allin, "value": round(value, 2), "maxBid": maxbid,
            "pctOfValueNow": round(allin / value, 2) if value else None}

def end_pt(ts):
    try:
        d = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if d.tzinfo is None: d = d.replace(tzinfo=datetime.timezone.utc)
        pt = d - datetime.timedelta(hours=8 if d.month in (11, 12, 1, 2) or (d.month == 3 and d.day < 9) else 7)
        return pt.strftime("%a %b %-d, %-I:%M%p PT")
    except Exception:
        return ts

def evaluate(lot, cat_rows, ws):
    """Return (bucket, pick) or (None, None)."""
    title = lot.get("title") or ""
    if "pokemon" not in title.lower() and "pokémon" not in title.lower(): return None, None
    base = {"lot": lot.get("lot_number"), "title": title.strip(), "url": f"https://goldin.co/item/{lot.get('meta_slug')}",
            "ends": lot.get("end_timestamp"), "endsPT": end_pt(lot.get("end_timestamp") or ""), "auctionType": lot.get("auction_type"),
            "status": lot.get("status")}
    gm = GRADE.search(title)
    sealed_t = lot_type(title) and re.search(r"sealed|unopened|booster|elite trainer|collection|\btin\b|blister", title, re.I) and not re.search(r"#\s?\d", title)
    if sealed_t and not gm:
        units, case = quantity(title)
        prod, why = match_sealed(title, cat_rows)
        if not prod: return None, None
        if units is None: return None, None       # a case that does not say how many boxes: value unknown
        value = prod["value"] * units
        if value < 40: return None, None
        kind = "multi" if units > 1 else "box"
        m = money(lot, value, kind)
        want = next((w for w in ws if w["kind"] not in ("singles", "kanto") and w["pid"] == str(prod["pid"])), None)
        pick = dict(base, kind="sealed", units=units, product=prod["name"], set=prod["set"], tcgProductId=prod["pid"],
                    unitValue=prod["value"], valueSource=f"TCGplayer min(market, lowest listing) x {units} (tcgcsv)", **m,
                    tcgUrl=f"https://www.tcgplayer.com/product/{prod['pid']}")
        if want: return "wants", dict(pick, wantId=want["id"])
        if m["pctOfValueNow"] is None or m["pctOfValueNow"] > 1.0: return None, None
        over = m["bids"] <= 2 and m["pctOfValueNow"] <= 0.5
        under = m["pctOfValueNow"] <= DEAL
        if units > 1 and (over or under):
            return "sealed", dict(pick, flag="overlooked" if over else "undervalued")
        if units == 1 and over and value >= 75:
            return "sealed", dict(pick, flag="overlooked")
        return None, None
    if gm:
        if SPECIAL_LOT.search(title): return None, None
        co, gr = gm.group(1), gm.group(2)
        if float(gr) < 8: return None, None
        w = match_single_want(title, ws)
        if not w: return None, None
        value, src = pc_graded(w, title, co, gr)
        if not value: return None, None
        raw = float(w.get("market") or 0)
        if raw and value > max(3 * raw, raw + 150): return None, None     # gem-tier slab, not what the want is for
        pick = dict(base, kind="graded", wantId=w["id"], grade=f"{co.upper()} {gr}", rawMarket=raw or None)
        pick.update(money(lot, value, "card"), valueSource=src)
        if pick["pctOfValueNow"] and pick["pctOfValueNow"] > 1.0: return None, None
        return "wants", pick
    return None, None

def main():
    days_sold = int(sys.argv[sys.argv.index("--sold") + 1]) if "--sold" in sys.argv else 0
    cat_rows = catalog()
    if len(cat_rows) < 300: sys.exit("tcgcsv catalog too small; keeping previous goldin.json")
    ws = wants()
    live = all_lots({})
    print(f"{len(live)} live Goldin Pokemon lots, {len(ws)} wants", file=sys.stderr)
    out = {"generated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "Goldin public lot search; values TCGplayer (tcgcsv) and PriceCharting",
           "rules": f"maxBid = highest hammer bid so that bid x (1 + buyer premium) + est. shipping <= {int(DEAL*100)}% of value. "
                    "Raw single cards never listed. Sealed values are TCGplayer market x units; graded values PriceCharting.",
           "lotsScanned": len(live), "auctions": {}, "wants": [], "sealed": []}
    for l in live:
        out["auctions"].setdefault(l.get("auction_id", "")[:60], {"type": l.get("auction_type"), "ends": l.get("end_timestamp"), "lots": 0})["lots"] += 1
        b, p = evaluate(l, cat_rows, ws)
        if b: out[b].append(p)
    for k in ("wants", "sealed"):
        out[k].sort(key=lambda p: (p.get("ends") or "", p.get("pctOfValueNow") or 9))
    json.dump(out, open(os.path.join(ROOT, "goldin.json"), "w"), indent=1, ensure_ascii=False)
    print(f"wants {len(out['wants'])}, sealed {len(out['sealed'])}", file=sys.stderr)
    if days_sold:
        sold = all_lots({"show_only": "Sold", "item_type": ["Cases/Boxes/Packs"]}, cap=4000)
        cut = (NOW - datetime.timedelta(days=days_sold)).isoformat()
        recent = [l for l in sold if (l.get("end_timestamp") or "") >= cut[:19]]
        rows = []
        for l in recent:
            title = l.get("title") or ""
            prod, why = match_sealed(title, cat_rows)
            units, case = quantity(title)
            bp = (l.get("buyer_premium") or 22.0) / 100
            r = {"title": title.strip(), "url": f"https://goldin.co/item/{l.get('meta_slug')}", "ended": l.get("end_timestamp"),
                 "hammer": l.get("current_price"), "bids": l.get("number_of_bids"), "allIn": round(float(l.get("current_price") or 0) * (1 + bp), 2)}
            if prod and units:
                v = prod["value"] * units
                r.update(product=prod["name"], units=units, value=round(v, 2), pctOfValue=round(r["allIn"] / v, 2) if v else None)
            rows.append(r)
        rows.sort(key=lambda r: r.get("pctOfValue") or 9)
        json.dump({"generated": out["generated"], "days": days_sold, "soldScanned": len(sold), "recent": len(recent), "lots": rows},
                  open(os.path.join(ROOT, "goldin_sold.json"), "w"), indent=1, ensure_ascii=False)
        print(f"sold: {len(sold)} scanned, {len(recent)} in last {days_sold} days", file=sys.stderr)

if __name__ == "__main__":
    main()
