#!/usr/bin/env python3
"""Photo check for raw-card eBay candidates (flash hits, want-list singles, lots).

Seller-stated "Near Mint" is often wrong, and the ledger tasks cannot download eBay
images themselves, so this job (GitHub has open internet) does the image work:

  1. collects every photo of each candidate listing (full size, s-l1600)
  2. finds the card in each photo and flattens it (OpenCV perspective warp)
  3. measures what can be measured:
       back:  whitening in the blue border band, per side and per corner
       front: centering from the border widths (left/right, top/bottom)
       both:  resolution of the card in the photo
  4. builds one contact sheet per listing: each flattened photo plus 3x corner zooms
  5. force-pushes sheets/<itemId>.jpg and checks.json to the `photos` branch (no history)

The morning Buy Hunter reads checks.json and LOOKS at each sheet against
docs/nm_rubric.md (PSA / CGC / TCGplayer criteria). The numbers here are aids, not
verdicts; thresholds are uncalibrated until enough rejected/accepted cards are logged.
Usage: python scripts/photo_check.py <out_dir>"""
import datetime, json, os, re, sys, time, urllib.parse, urllib.request

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_ebay_wants import get, token  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_photos")
NOW = datetime.datetime.now(datetime.timezone.utc)
UA = {"User-Agent": "sealed-ledger-photo-check/1.0"}
W, H = 630, 880          # flattened card size (standard 63 x 88 mm)
MAX_LISTINGS = 40
MAX_PHOTOS = 6


def load(n, d):
    try:
        return json.load(open(os.path.join(ROOT, n)))
    except Exception:
        return d


def big(u):
    return re.sub(r"/s-l\d+\.", "/s-l1600.", u or "")


def fetch_img(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(big(url), headers=UA), timeout=30) as r:
                a = np.frombuffer(r.read(), np.uint8)
            return cv2.imdecode(a, cv2.IMREAD_COLOR)
        except Exception:
            time.sleep(2)
    return None


def candidates():
    out = {}
    fl = load("flash.json", {}).get("hits", [])
    for h in fl:
        if h.get("cond") != "nm":
            continue
        try:
            age = (NOW - datetime.datetime.fromisoformat(h["found"])).total_seconds() / 3600
        except Exception:
            age = 99
        if age <= 40:
            out[h["itemId"]] = {"src": "flash", "wantId": h.get("wantId"), "title": h.get("listing"), "url": h.get("url"), "photos": []}
    ew = load("ebay_wants.json", {})
    for s in ew.get("singles", []):
        if s.get("nmVerified") is False or not s.get("allIn") or not s.get("target"):
            continue
        if s["allIn"] > s["target"] * 1.10:
            continue
        iid = re.search(r"/itm/(\d+)", s.get("url") or "")
        if iid:
            key = "v1|" + iid.group(1) + "|0"
            out.setdefault(key, {"src": "wants", "wantId": s.get("wantId"), "title": s.get("title"), "url": s.get("url"), "photos": []})
    for l in ew.get("lots", [])[:10]:
        out.setdefault(l["itemId"], {"src": "lot", "wantId": ",".join(l.get("matchedIds") or [])[:80], "title": l.get("title"),
                                      "url": l.get("url"), "photos": l.get("photos") or []})
    return dict(list(out.items())[:MAX_LISTINGS])


def photos_for(iid, H):
    d = get("https://api.ebay.com/buy/browse/v1/item/" + urllib.parse.quote(iid, safe=""), H) or {}
    ph = [(d.get("image") or {}).get("imageUrl")] + [i.get("imageUrl") for i in (d.get("additionalImages") or [])]
    return [p for p in ph if p][:MAX_PHOTOS], d


def find_card(img):
    """Largest 4-sided contour with a card-like aspect ratio -> flattened card, or None."""
    h0, w0 = img.shape[:2]
    scale = 1000 / max(h0, w0)
    small = cv2.resize(img, (int(w0 * scale), int(h0 * scale)))
    g = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    best = None
    for lo, hi in ((30, 100), (50, 150), (10, 60)):
        e = cv2.dilate(cv2.Canny(g, lo, hi), np.ones((3, 3), np.uint8), iterations=2)
        cs, _ = cv2.findContours(e, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(cs, key=cv2.contourArea, reverse=True)[:5]:
            a = cv2.contourArea(c)
            if a < 0.12 * small.shape[0] * small.shape[1]:
                break
            p = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
            if len(p) != 4:
                continue
            pts = p.reshape(4, 2).astype("float32") / scale
            s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
            q = np.array([pts[s.argmin()], pts[d.argmin()], pts[s.argmax()], pts[d.argmax()]], dtype="float32")
            wq = (np.linalg.norm(q[0] - q[1]) + np.linalg.norm(q[3] - q[2])) / 2
            hq = (np.linalg.norm(q[0] - q[3]) + np.linalg.norm(q[1] - q[2])) / 2
            if hq <= 0:
                continue
            ar = wq / hq
            if 0.64 <= ar <= 0.79:
                best = (q, hq)
                break
        if best:
            break
    if not best:
        return None, None
    q, hq = best
    M = cv2.getPerspectiveTransform(q, np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], dtype="float32"))
    return cv2.warpPerspective(img, M, (W, H)), int(hq)


_R = int(0.05 * W)   # card corner radius (~3 mm of 63 mm)


def _masks():
    m = np.zeros((H, W), np.uint8)
    cv2.rectangle(m, (_R, 0), (W - 1 - _R, H - 1), 255, -1)
    cv2.rectangle(m, (0, _R), (W - 1, H - 1 - _R), 255, -1)
    for cx, cy in ((_R, _R), (W - 1 - _R, _R), (_R, H - 1 - _R), (W - 1 - _R, H - 1 - _R)):
        cv2.circle(m, (cx, cy), _R, 255, -1)
    dist = cv2.distanceTransform(cv2.copyMakeBorder(m, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0), cv2.DIST_L2, 3)[1:-1, 1:-1]
    band = (dist > 4) & (dist < 0.035 * W)          # border band, skipping the outermost pixels
    c = int(0.09 * W)
    reg = {"top": np.zeros((H, W), bool), "bottom": np.zeros((H, W), bool), "left": np.zeros((H, W), bool), "right": np.zeros((H, W), bool)}
    reg["top"][:c, c:W - c] = True; reg["bottom"][H - c:, c:W - c] = True
    reg["left"][c:H - c, :c] = True; reg["right"][c:H - c, W - c:] = True
    cor = {}
    for k, (ys, xs) in {"tl": (slice(0, c), slice(0, c)), "tr": (slice(0, c), slice(W - c, W)),
                        "bl": (slice(H - c, H), slice(0, c)), "br": (slice(H - c, H), slice(W - c, W))}.items():
        z = np.zeros((H, W), bool); z[ys, xs] = True; cor[k] = z
    return band, reg, cor


BAND, SIDES, CORNERS = _masks()


def band_kind(card):
    """Classify a flattened photo by its border band: 'back' (blue border), 'front' (yellow/silver) or None (bad crop)."""
    hsv = cv2.cvtColor(card, cv2.COLOR_BGR2HSV)
    h, s_, v = hsv[..., 0][BAND], hsv[..., 1][BAND], hsv[..., 2][BAND]
    blue = ((h >= 95) & (h <= 130) & (s_ > 60)).mean()
    white = ((v > 185) & (s_ < 60)).mean()
    yellow = ((h >= 15) & (h <= 40) & (s_ > 70)).mean()
    silver = ((s_ < 40) & (v > 110)).mean()
    if blue >= 0.7 and white < 0.12 and blue + white >= 0.85:   # a solid blue border; the white swirl inside is not a border
        # and the back's own design: yellow 'Pokemon' logo in the top band, red Poke Ball top half in the middle
        top = hsv[int(0.06 * H):int(0.30 * H), int(0.12 * W):int(0.88 * W)]
        mid = hsv[int(0.36 * H):int(0.52 * H), int(0.30 * W):int(0.70 * W)]
        ylw = ((top[..., 0] >= 15) & (top[..., 0] <= 40) & (top[..., 1] > 90)).mean()
        red = (((mid[..., 0] <= 8) | (mid[..., 0] >= 170)) & (mid[..., 1] > 90)).mean()
        if ylw > 0.12 and red > 0.04:
            return "back"
        return None
    if yellow >= 0.6 or silver >= 0.75:
        return "front"
    return None


def back_whitening(card):
    """Share of white among border-band pixels per side and per corner (a clean blue back is ~0%)."""
    hsv = cv2.cvtColor(card, cv2.COLOR_BGR2HSV)
    white = (hsv[..., 2] > 185) & (hsv[..., 1] < 60)
    f = lambda m: round(float(white[m & BAND].mean()) * 100, 2) if (m & BAND).any() else 0.0
    return {k: f(m) for k, m in SIDES.items()}, {k: f(m) for k, m in CORNERS.items()}


def centering(card):
    """Border widths from the outer edge inward along the middle row/column (yellow/silver bordered fronts)."""
    lab = cv2.cvtColor(cv2.GaussianBlur(card, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)

    def run(line):
        ref = line[6:12].mean(0)
        for i in range(12, len(line) // 3):
            if np.linalg.norm(line[i:i + 4].mean(0) - ref) > 28:
                return i
        return None
    out = {}
    for name, line in (("left", lab[H // 2, :]), ("right", lab[H // 2, ::-1]), ("top", lab[:, W // 2]), ("bottom", lab[::-1, W // 2])):
        out[name] = run(line)
    if None in out.values() or min(out.values()) < 8:
        return None
    lr = max(out["left"], out["right"]) / (out["left"] + out["right"]) * 100
    tb = max(out["top"], out["bottom"]) / (out["top"] + out["bottom"]) * 100
    return {"lr": f"{round(lr)}/{round(100 - lr)}", "tb": f"{round(tb)}/{round(100 - tb)}", "worst": round(max(lr, tb))}


def zooms(card):
    c = int(0.10 * W)
    tiles = [card[0:c, 0:c], card[0:c, W - c:W], card[H - c:H, 0:c], card[H - c:H, W - c:W]]
    tiles = [cv2.resize(t, (210, 210), interpolation=cv2.INTER_CUBIC) for t in tiles]
    return np.vstack([np.hstack(tiles[:2]), np.hstack(tiles[2:])])


def sheet_row(img, card, label):
    hrow = 440
    if card is not None:
        left = cv2.resize(card, (int(W * hrow / H), hrow))
        z = cv2.resize(zooms(card), (hrow, hrow))
        row = np.hstack([left, z])
    else:   # no reliable crop: whole photo plus its four quadrants at 2x, so the eye can check corners and edges
        h0, w0 = img.shape[:2]
        whole = cv2.resize(img, (int(w0 * hrow / h0), hrow))
        q = [img[:h0 // 2, :w0 // 2], img[:h0 // 2, w0 // 2:], img[h0 // 2:, :w0 // 2], img[h0 // 2:, w0 // 2:]]
        qs = [cv2.resize(x, (hrow // 2 * w0 // h0 or 1, hrow // 2)) for x in q]
        quad = np.vstack([np.hstack(qs[:2]), np.hstack(qs[2:])])
        quad = cv2.resize(quad, (int(quad.shape[1] * 2), hrow * 2))
        row = whole if quad is None else None
        canvas_w = max(whole.shape[1] + 10, quad.shape[1])
        out = np.full((hrow + 10 + quad.shape[0], canvas_w, 3), 255, np.uint8)
        out[:hrow, :whole.shape[1]] = whole
        out[hrow + 10:, :quad.shape[1]] = quad
        row = out
    canvas = np.full((row.shape[0] + 30, max(row.shape[1], 900), 3), 255, np.uint8)
    canvas[30:30 + row.shape[0], :row.shape[1]] = row
    cv2.putText(canvas, label[:110], (6, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
    return canvas


def load_grader():
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "grader"))
        from score import Grader
        return Grader()
    except Exception as e:   # grader is an extra signal; the photo check still runs without it
        import traceback
        global GRADER_ERR
        GRADER_ERR = traceback.format_exc()[-1500:]
        print("grader unavailable:", e)
        return None


GRADER_ERR = None


def main():
    os.makedirs(os.path.join(OUT, "sheets"), exist_ok=True)
    G = load_grader()
    H_ = {"Authorization": "Bearer " + token(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    res = {}
    for iid, c in candidates().items():
        photos = c["photos"]
        if len(photos) < 2:
            photos, _ = photos_for(iid, H_)
        rows, info = [], {"src": c["src"], "wantId": c["wantId"], "title": c["title"], "url": c["url"], "photos": len(photos),
                          "backs": [], "fronts": [], "flags": []}
        for n, u in enumerate(photos):
            img = fetch_img(u)
            if img is None:
                continue
            if G is not None:
                try:
                    gs = G.score(img)
                except Exception:
                    gs = None
                if gs:
                    gs["photo"] = n + 1
                    info.setdefault("grader", []).append(gs)
            card, px = find_card(img)
            kind = band_kind(card) if card is not None else None
            if kind is None:
                rows.append(sheet_row(img, None, f"photo {n + 1}: card edges not measurable (toploader, glare or background) - judge by eye in the 2x quadrants"))
                if card is None or True:
                    info.setdefault("unmeasured", []).append(n + 1)
                continue
            if kind == "back":
                sides, corners = back_whitening(card)
                if max(sides.values()) > 30:   # a whole side "white" means the crop missed the border: do not trust it
                    rows.append(sheet_row(img, None, f"photo {n + 1}: back found but border crop unreliable - judge by eye"))
                    info.setdefault("unmeasured", []).append(n + 1)
                    continue
                info["backs"].append({"photo": n + 1, "cardPx": px, "sides": sides, "corners": corners})
                lab = f"photo {n + 1} BACK {px}px  whitening % sides " + " ".join(f"{k[0]}{v}" for k, v in sides.items()) + "  corners " + " ".join(f"{k}{v}" for k, v in corners.items())
            else:
                ce = centering(card)
                info["fronts"].append({"photo": n + 1, "cardPx": px, "centering": ce})
                lab = f"photo {n + 1} FRONT {px}px  centering " + (f"L/R {ce['lr']}  T/B {ce['tb']}" if ce else "n/a (full art or no border found)")
            rows.append(sheet_row(img, card, lab))
        if not info["backs"]:
            info["flags"].append("no measurable back photo (check by eye; none at all = fail)")
        gr = info.get("grader") or []
        if gr:
            worst = min(gr, key=lambda x: x["p8"])
            info["graderP8"] = worst["p8"]; info["graderGrade"] = min(x["grade"] for x in gr)
            if worst["p8"] < 0.4:
                info["flags"].append(f"grader: likely PSA 7 or lower (P8+ {worst['p8']}, est. PSA {worst['grade']}, photo {worst['photo']})")
            rows.insert(0, np.full((34, 900, 3), 255, np.uint8))
            cv2.putText(rows[0], f"GRADER (PSA-trained): worst photo P(PSA 8+) {worst['p8']}, est. PSA {info['graderGrade']}", (6, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 160) if worst["p8"] < 0.4 else (0, 110, 0) if worst["p8"] >= 0.8 else (0, 0, 0), 1, cv2.LINE_AA)
        for b in info["backs"]:
            if max(b["sides"].values()) > 4.0 or max(b["corners"].values()) > 20.0:
                info["flags"].append(f"back whitening (photo {b['photo']})")
            if b["cardPx"] < 700:
                info["flags"].append(f"low resolution back (photo {b['photo']}, {b['cardPx']}px)")
        for f in info["fronts"]:
            if f["centering"] and f["centering"]["worst"] > 65:
                info["flags"].append(f"front off-centre {f['centering']['lr']} / {f['centering']['tb']} (PSA 8 needs 65/35)")
        if rows:
            w = max(r.shape[1] for r in rows)
            rows = [np.hstack([r, np.full((r.shape[0], w - r.shape[1], 3), 255, np.uint8)]) if r.shape[1] < w else r for r in rows]
            fn = re.sub(r"[^0-9A-Za-z_-]", "_", iid) + ".jpg"
            cv2.imwrite(os.path.join(OUT, "sheets", fn), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 82])
            info["sheet"] = "sheets/" + fn
        res[iid] = info
        time.sleep(0.3)
    json.dump({"generated": NOW.isoformat(timespec="minutes"), "graderError": GRADER_ERR, "rubric": "docs/nm_rubric.md on main", "listings": res},
              open(os.path.join(OUT, "checks.json"), "w"), indent=1, ensure_ascii=False)
    print(len(res), "listings checked;", sum(1 for v in res.values() if v["flags"]), "with flags")


if __name__ == "__main__":
    main()
