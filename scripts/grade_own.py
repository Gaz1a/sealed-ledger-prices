#!/usr/bin/env python3
"""Grade Gaz's OWN cards from the photos he sends (stored in grading/submissions/<ledgerId>/<YYYY-MM-DD>/*.jpg|png).
Same measurements and PSA-trained grader as the eBay photo check (scripts/photo_check.py): card found and flattened,
back-edge whitening, front centering, grader P(PSA 8+) and estimated grade (worst photo counts), plus a contact sheet.
Writes grading/results.json {"<ledgerId>/<date>": {...}} and grading/sheets/<ledgerId>_<date>.jpg.
The photos are kept so each prediction can be compared with the grade PSA returns (grader accuracy)."""
import glob, json, os, re, sys, datetime
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import photo_check as pc

ROOT = pc.ROOT
SUB, OUTP, SHEETS = os.path.join(ROOT, "grading/submissions"), os.path.join(ROOT, "grading/results.json"), os.path.join(ROOT, "grading/sheets")
os.makedirs(SHEETS, exist_ok=True)
res = json.load(open(OUTP)) if os.path.exists(OUTP) else {}
G = pc.load_grader()
redo = "--redo" in sys.argv
for d in sorted(glob.glob(os.path.join(SUB, "*", "*"))):
    if not os.path.isdir(d): continue
    lid, date = d.split(os.sep)[-2:]
    key = f"{lid}/{date}"
    files = sorted(f for f in glob.glob(os.path.join(d, "*")) if re.search(r"\.(jpe?g|png|webp)$", f, re.I))
    if not files or (key in res and not redo and res[key].get("files") == [os.path.basename(f) for f in files]): continue
    info = {"ledgerId": lid, "date": date, "files": [os.path.basename(f) for f in files], "backs": [], "fronts": [], "flags": [], "grader": []}
    rows = []
    for n, f in enumerate(files):
        img = cv2.imread(f)
        if img is None: info["flags"].append(f"unreadable {os.path.basename(f)}"); continue
        if max(img.shape[:2]) > 3000:
            s = 3000 / max(img.shape[:2]); img = cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s)))
        if G is not None:
            try:
                gs = G.score(img)
                if gs: gs["photo"] = n + 1; info["grader"].append(gs)
            except Exception: pass
        card, px = pc.find_card(img)
        kind = pc.band_kind(card) if card is not None else None
        if kind is None:
            rows.append(pc.sheet_row(img, None, f"photo {n + 1}: card edges not measurable - judge by eye")); continue
        if kind == "back":
            sides, corners = pc.back_whitening(card)
            info["backs"].append({"photo": n + 1, "cardPx": px, "sides": sides, "corners": corners})
            lab = f"photo {n + 1} BACK {px}px whitening % " + " ".join(f"{k[0]}{v}" for k, v in sides.items())
        else:
            ce = pc.centering(card)
            info["fronts"].append({"photo": n + 1, "cardPx": px, "centering": ce})
            lab = f"photo {n + 1} FRONT {px}px centering " + (f"L/R {ce['lr']} T/B {ce['tb']}" if ce else "n/a")
        rows.append(pc.sheet_row(img, card, lab))
    if info["grader"]:
        worst = min(info["grader"], key=lambda x: x["p8"])
        info["graderP8"], info["graderGrade"] = worst["p8"], min(x["grade"] for x in info["grader"])
    for b in info["backs"]:
        if max(b["sides"].values()) > 4.0 or max(b["corners"].values()) > 20.0: info["flags"].append(f"back whitening (photo {b['photo']})")
    for f in info["fronts"]:
        if f["centering"] and f["centering"]["worst"] > 55: info["flags"].append(f"centering {f['centering']['lr']} / {f['centering']['tb']} (PSA 10 needs 55/45 or better)")
    if not info["backs"]: info["flags"].append("no measurable back photo")
    if rows:
        w = max(r.shape[1] for r in rows)
        rows = [np.hstack([r, np.full((r.shape[0], w - r.shape[1], 3), 255, np.uint8)]) if r.shape[1] < w else r for r in rows]
        fn = f"{lid}_{date}.jpg"
        cv2.imwrite(os.path.join(SHEETS, fn), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 82]); info["sheet"] = "grading/sheets/" + fn
    info["checked"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")
    info["graderError"] = pc.GRADER_ERR
    res[key] = info
    print(key, info.get("graderP8"), info.get("graderGrade"), info["flags"])
json.dump(res, open(OUTP, "w"), indent=1)
