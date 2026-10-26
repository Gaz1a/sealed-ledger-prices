#!/usr/bin/env python3
"""Grader v2, step 1: build a labelled crop dataset from PSA-slabbed Pokemon cards on eBay.

For each PSA grade 1-10, many searches across eras and sets (the grade in the title is the label).
Each photo: find the slab, then the card inside it (or the card directly), flatten it at its native
resolution, cut 8 crops (4 corners + 4 edge midpoints, 12% of card width) and save them at 320px.
Output: <out>/crops/*.jpg and <out>/meta.json  [{iid, grade, photo, side, px, files:[8]}]
Usage: python scripts/grader/collect.py <out_dir>   (EBAY_CLIENT_ID/SECRET; TARGET per grade, default 900)"""
import json, os, re, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from scan_ebay_wants import get, token  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
TARGET = int(os.environ.get("TARGET", "900"))
GRADED = "2750"
SETS = ["", "holo", "base set", "jungle", "fossil", "team rocket", "neo", "gym heroes", "gym challenge", "legendary collection",
        "expedition", "aquapolis", "skyridge", "ex", "diamond pearl", "platinum", "heartgold", "black white", "xy", "evolutions",
        "sun moon", "hidden fates", "sword shield", "celebrations", "crown zenith", "scarlet violet", "151", "paldea",
        "japanese", "promo", "full art", "reverse holo", "trainer", "1st edition", "shadowless", "charizard", "pikachu",
        "gyarados", "mewtwo", "eevee"]
CARD_AR = 63 / 88


def search(q, H):
    out = []
    for off in (0, 200, 400):
        url = ("https://api.ebay.com/buy/browse/v1/item_summary/search?q=" + urllib.parse.quote(q) +
               "&filter=" + urllib.parse.quote(f"conditionIds:{{{GRADED}}}") + f"&limit=200&offset={off}")
        items = (get(url, H) or {}).get("itemSummaries", [])
        out += items
        if len(items) < 200:
            break
        time.sleep(0.15)
    return out


def collect(H):
    data, seen_img = {}, set()
    for g in range(1, 11):
        n = 0
        for s in SETS:
            for it in search(f"PSA {g} pokemon {s}".strip(), H):
                t = it.get("title", "")
                m = set(re.findall(r"\bPSA\s*(10|[1-9])(?:\.5)?\b", t, re.I))
                if m != {str(g)} or re.search(r"\b(lot|bundle|set of|cards)\b|x\s?\d\b|\bbgs\b|\bcgc\b|\bsgc\b|\bpsa\s*\d\.5", t, re.I):
                    continue
                if it["itemId"] in data:
                    continue
                ph = [(it.get("image") or {}).get("imageUrl")] + [a.get("imageUrl") for a in (it.get("additionalImages") or [])]
                ph = [p for p in ph if p and p not in seen_img][:4]
                if not ph:
                    continue
                seen_img.update(ph)
                data[it["itemId"]] = {"grade": g, "title": t, "photos": ph}
                n += 1
            if n >= TARGET:
                break
        print(f"PSA {g}: {n} listings", flush=True)
    return data


def quads(img, ar_lo, ar_hi, min_frac):
    h0, w0 = img.shape[:2]
    sc = 1000 / max(h0, w0)
    small = cv2.resize(img, (int(w0 * sc), int(h0 * sc)))
    g = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    for lo, hi in ((30, 100), (50, 150), (10, 60), (80, 200)):
        e = cv2.dilate(cv2.Canny(g, lo, hi), np.ones((3, 3), np.uint8), iterations=1)
        cs, _ = cv2.findContours(e, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(cs, key=cv2.contourArea, reverse=True)[:12]:
            if cv2.contourArea(c) < min_frac * small.shape[0] * small.shape[1]:
                break
            p = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
            if len(p) != 4:
                continue
            pts = p.reshape(4, 2).astype("float32") / sc
            s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
            q = np.array([pts[s.argmin()], pts[d.argmin()], pts[s.argmax()], pts[d.argmax()]], dtype="float32")
            wq = (np.linalg.norm(q[0] - q[1]) + np.linalg.norm(q[3] - q[2])) / 2
            hq = (np.linalg.norm(q[0] - q[3]) + np.linalg.norm(q[1] - q[2])) / 2
            if hq > 0 and ar_lo <= wq / hq <= ar_hi:
                return q, hq
    return None, None


def warp(img, q, hq, maxh=1400):
    hh = int(min(maxh, hq)); ww = int(hh * CARD_AR)
    M = cv2.getPerspectiveTransform(q, np.array([[0, 0], [ww - 1, 0], [ww - 1, hh - 1], [0, hh - 1]], dtype="float32"))
    return cv2.warpPerspective(img, M, (ww, hh))


def find_card_any(img):
    """Card directly (raw photos) or inside a PSA slab (slab first, then the card in its lower part)."""
    q, hq = quads(img, 0.66, 0.77, 0.10)
    if q is not None:
        return warp(img, q, hq), int(hq)
    sq, sh = quads(img, 0.53, 0.66, 0.12)            # PSA slab ~ 3.3 x 5.35 in
    if sq is None:
        return None, None
    sw = int(sh * 0.62)
    M = cv2.getPerspectiveTransform(sq, np.array([[0, 0], [sw - 1, 0], [sw - 1, int(sh) - 1], [0, int(sh) - 1]], dtype="float32"))
    slab = cv2.warpPerspective(img, M, (sw, int(sh)))
    roi = slab[int(0.22 * sh):, :]
    q, hq = quads(roi, 0.66, 0.77, 0.30)
    if q is None:
        return None, None
    return warp(roi, q, hq), int(hq)


def crops(card):
    hh, ww = card.shape[:2]
    c = int(0.12 * ww)
    pts = [(0, 0), (ww - c, 0), (0, hh - c), (ww - c, hh - c), ((ww - c) // 2, 0), ((ww - c) // 2, hh - c), (0, (hh - c) // 2), (ww - c, (hh - c) // 2)]
    return [cv2.resize(card[y:y + c, x:x + c], (320, 320), interpolation=cv2.INTER_CUBIC) for x, y in pts]


def side(card):
    hsv = cv2.cvtColor(cv2.resize(card, (126, 176)), cv2.COLOR_BGR2HSV)
    top = hsv[10:52, 15:111]; mid = hsv[63:92, 38:88]
    blue = ((hsv[..., 0] >= 95) & (hsv[..., 0] <= 130) & (hsv[..., 1] > 60)).mean()
    ylw = ((top[..., 0] >= 15) & (top[..., 0] <= 40) & (top[..., 1] > 90)).mean()
    red = (((mid[..., 0] <= 8) | (mid[..., 0] >= 170)) & (mid[..., 1] > 90)).mean()
    return "back" if blue > 0.35 and ylw > 0.10 and red > 0.03 else "front"


def big(u):
    return re.sub(r"/s-l\d+\.", "/s-l1600.", u)


def work(args):
    iid, g, k, url = args
    try:
        with urllib.request.urlopen(urllib.request.Request(big(url), headers={"User-Agent": "ledger-grader/2.0"}), timeout=25) as r:
            img = cv2.imdecode(np.frombuffer(r.read(), np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None
    if img is None:
        return None
    card, px = find_card_any(img)
    if card is None or px < 450:
        return None
    base = re.sub(r"[^0-9A-Za-z]", "_", iid) + f"_{k}"
    files = []
    for j, c in enumerate(crops(card)):
        fn = f"{base}_{j}.jpg"
        cv2.imwrite(os.path.join(OUT, "crops", fn), c, [cv2.IMWRITE_JPEG_QUALITY, 92])
        files.append(fn)
    return {"iid": iid, "grade": g, "photo": k, "side": side(card), "px": px, "files": files}


def main():
    os.makedirs(os.path.join(OUT, "crops"), exist_ok=True)
    H = {"Authorization": "Bearer " + token(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    data = collect(H)
    jobs = [(iid, d["grade"], k, u) for iid, d in data.items() for k, u in enumerate(d["photos"])]
    print(len(data), "listings,", len(jobs), "photos to fetch", flush=True)
    meta = []
    with ThreadPoolExecutor(16) as ex:
        for n, r in enumerate(ex.map(work, jobs)):
            if r:
                meta.append(r)
            if n % 2000 == 0:
                print(n, "photos done,", len(meta), "usable", flush=True)
    json.dump({"listings": len(data), "photos": len(jobs), "usable": len(meta), "rows": meta}, open(os.path.join(OUT, "meta.json"), "w"))
    from collections import Counter
    print("usable by grade", dict(sorted(Counter(m["grade"] for m in meta).items())), "sides", dict(Counter(m["side"] for m in meta)))


if __name__ == "__main__":
    main()
