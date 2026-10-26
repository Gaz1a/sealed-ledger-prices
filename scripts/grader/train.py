#!/usr/bin/env python3
"""Ledger card grader, v1: learns what PSA-graded corners and edges look like, from eBay photos.

Data (free, labelled by PSA itself): eBay listings of PSA-slabbed Pokemon cards. The grade in the
title is the label; the photos show the card through the slab. For every photo where the card can be
isolated (scripts/photo_check.find_card), we take 8 crops (4 corners + 4 edge midpoints), embed each
with a pretrained vision model (DINOv2-small, frozen) and train a small classifier:
    "looks PSA 8 or better" vs "looks PSA 6 or worse"  (PSA 7 is held out as the grey zone)
Evaluation is on listings the model never saw (split by listing, not by crop).

Outputs (committed to main, small): models/grader.npz (classifier weights + normaliser),
models/grader_report.json (data counts, holdout accuracy, AUC, per-grade scores).
Usage: python scripts/grader/train.py  (needs EBAY_CLIENT_ID/SECRET; torch, timm, opencv, scikit-learn)"""
import io, json, os, random, re, sys, time, urllib.parse, urllib.request

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from scan_ebay_wants import get, token  # noqa: E402
from photo_check import find_card, band_kind, W, H, big  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
GRADES = [10, 9, 8, 7, 6, 5, 4, 3]
QUERIES = ["PSA {g} pokemon card", "PSA {g} pokemon holo", "PSA {g} pokemon vintage", "PSA {g} pokemon base set", "PSA {g} pokemon japanese"]
PER_GRADE = int(os.environ.get("PER_GRADE", "260"))      # listings per grade
GRADED = "2750"                                            # eBay condition id: Graded
random.seed(7)


def collect(Hd):
    os.makedirs(os.path.join(ROOT, "models"), exist_ok=True)
    for f in ("grader_progress.txt", "grader_error.txt"):
        try:
            os.remove(os.path.join(ROOT, "models", f))
        except OSError:
            pass
    lst = {}
    for g in GRADES:
        got = {}
        for q in QUERIES:
            for off in (0, 200):
                url = ("https://api.ebay.com/buy/browse/v1/item_summary/search?q=" + urllib.parse.quote(q.format(g=g)) +
                       "&filter=" + urllib.parse.quote(f"conditionIds:{{{GRADED}}}") + f"&limit=200&offset={off}")
                for it in (get(url, Hd) or {}).get("itemSummaries", []):
                    t = it.get("title", "")
                    m = re.findall(r"\bPSA\s*(10|[1-9](?:\.5)?)\b", t, re.I)
                    if len(set(m)) != 1 or float(m[0]) != g or re.search(r"\b(lot|bundle|set of|x\d|\d+\s*cards)\b", t, re.I):
                        continue
                    ph = [(it.get("image") or {}).get("imageUrl")] + [a.get("imageUrl") for a in (it.get("additionalImages") or [])]
                    ph = [p for p in ph if p][:4]
                    if ph:
                        got[it["itemId"]] = {"grade": g, "title": t, "photos": ph}
                time.sleep(0.2)
                if len(got) >= PER_GRADE:
                    break
            if len(got) >= PER_GRADE:
                break
        print(f"PSA {g}: {len(got)} listings", flush=True)
        open(os.path.join(ROOT, "models", "grader_progress.txt"), "a").write(f"PSA {g}: {len(got)} listings\n")
        lst.update(dict(list(got.items())[:PER_GRADE]))
    return lst


def fetch(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(big(url), headers={"User-Agent": "ledger-grader/1.0"}), timeout=25) as r:
            return cv2.imdecode(np.frombuffer(r.read(), np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None


def crops(card):
    c = int(0.14 * W)
    pts = [(0, 0), (W - c, 0), (0, H - c), (W - c, H - c),                       # corners
           ((W - c) // 2, 0), ((W - c) // 2, H - c), (0, (H - c) // 2), (W - c, (H - c) // 2)]  # edge midpoints
    return [cv2.cvtColor(cv2.resize(card[y:y + c, x:x + c], (224, 224), interpolation=cv2.INTER_CUBIC), cv2.COLOR_BGR2RGB) for x, y in pts]


class Embedder:
    def __init__(self):
        import torch, timm
        self.torch = torch
        self.m = timm.create_model("vit_small_patch14_dinov2.lvd142m", pretrained=True, num_classes=0, img_size=224).eval()
        self.mean = np.array([0.485, 0.456, 0.406], np.float32)
        self.std = np.array([0.229, 0.224, 0.225], np.float32)

    def __call__(self, imgs):
        x = (np.stack(imgs).astype(np.float32) / 255 - self.mean) / self.std
        with self.torch.no_grad():
            return self.m(self.torch.from_numpy(x.transpose(0, 3, 1, 2))).numpy()


def featurise(card, emb):
    e = emb(crops(card))                       # 8 x 384
    return np.concatenate([e.mean(0), e.min(0), e.max(0)])   # 1152-d per photo; min/max keep the worst corner visible


def main():
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    Hd = {"Authorization": "Bearer " + token(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    data = collect(Hd)
    emb = Embedder()
    rows = []   # (itemId, grade, side, feature)
    for n, (iid, d) in enumerate(data.items()):
        for u in d["photos"]:
            img = fetch(u)
            if img is None:
                continue
            card, px = find_card(img)
            if card is None or (px or 0) < 500:
                continue
            side = band_kind(card) or "front"
            rows.append((iid, d["grade"], side, featurise(card, emb)))
        if n % 100 == 0:
            print(n, "listings processed,", len(rows), "usable photos", flush=True)
    ids = sorted({r[0] for r in rows}); random.shuffle(ids)
    test_ids = set(ids[: len(ids) // 5])
    def xy(keep):
        R = [r for r in rows if keep(r) and r[1] != 7]
        return np.array([r[3] for r in R]), np.array([1 if r[1] >= 8 else 0 for r in R]), R
    Xtr, ytr, _ = xy(lambda r: r[0] not in test_ids)
    Xte, yte, Rte = xy(lambda r: r[0] in test_ids)
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    clf = LogisticRegression(C=0.5, max_iter=3000, class_weight="balanced").fit((Xtr - mu) / sd, ytr)
    p = clf.predict_proba((Xte - mu) / sd)[:, 1]
    acc = float(((p >= 0.5) == yte).mean()); auc = float(roc_auc_score(yte, p))
    # per-listing: worst photo decides (a buyer cares about the worst side)
    by = {}
    for r, pp in zip(Rte, p):
        by.setdefault(r[0], (r[1], []))[1].append(pp)
    L = [(g, min(ps)) for g, ps in by.values()]
    lacc = float(np.mean([(s >= 0.5) == (g >= 8) for g, s in L]))
    pg = {}
    for r in rows:
        if r[0] in test_ids:
            pg.setdefault(r[1], []).append(float(clf.predict_proba(((r[3] - mu) / sd)[None])[0, 1]))
    os.makedirs(os.path.join(ROOT, "models"), exist_ok=True)
    np.savez_compressed(os.path.join(ROOT, "models", "grader.npz"), coef=clf.coef_, intercept=clf.intercept_, mu=mu, sd=sd)
    rep = {"trained": time.strftime("%Y-%m-%d"), "listings": len(data), "usablePhotos": len(rows),
           "photosByGrade": {g: sum(1 for r in rows if r[1] == g) for g in GRADES},
           "trainPhotos": int(len(ytr)), "testPhotos": int(len(yte)), "testListings": len(by),
           "photoAccuracy": round(acc, 3), "photoAUC": round(auc, 3), "listingAccuracy": round(lacc, 3),
           "meanScoreByGrade(test)": {g: round(float(np.mean(v)), 3) for g, v in sorted(pg.items())},
           "task": "P(looks PSA 8+) from 4 corner + 4 edge crops; PSA 7 held out", "embedder": "DINOv2-small (frozen)"}
    json.dump(rep, open(os.path.join(ROOT, "models", "grader_report.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        os.makedirs(os.path.join(ROOT, "models"), exist_ok=True)
        open(os.path.join(ROOT, "models", "grader_error.txt"), "w").write(traceback.format_exc())
        raise
