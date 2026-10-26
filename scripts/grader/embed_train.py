#!/usr/bin/env python3
"""Grader v2, step 2: embed every crop with DINOv2 (local patch detail kept) and train a
multi-crop grading head.

Features per crop (DINOv2-small at 336px, frozen): CLS token, mean of patch tokens, max of patch
tokens -> 1152 numbers. Per photo the 8 crops go through a shared small network; the crops are then
pooled (max + mean, so one bad corner can drag the grade down) and the head predicts
(a) the PSA grade (regression) and (b) P(PSA 8 or better).
Split by listing: 70% train, 10% validation (early stopping), 20% test (never seen).
Writes models/grader_v2.pt, models/grader_v2_report.json; caches features in <data>/feats.npz.
Usage: python scripts/grader/embed_train.py <data_dir>"""
import json, os, random, sys, time

import cv2
import numpy as np
import torch
import torch.nn as nn

DATA = sys.argv[1] if len(sys.argv) > 1 else "."
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
torch.manual_seed(7); random.seed(7); np.random.seed(7)
torch.set_num_threads(os.cpu_count() or 4)


RES = int(os.environ.get("EMBED_RES", "280"))


def embed_rows(rows, idx, out):
    import timm
    m = timm.create_model("vit_small_patch14_dinov2.lvd142m", pretrained=True, num_classes=0, img_size=RES).eval()
    mean = np.array([0.485, 0.456, 0.406], np.float32); std = np.array([0.229, 0.224, 0.225], np.float32)
    X = np.zeros((len(idx), 8, 1152), np.float16)
    t0 = time.time()
    for j, i in enumerate(idx):
        r = rows[i]
        imgs = [cv2.cvtColor(cv2.resize(cv2.imread(os.path.join(DATA, "crops", f)), (RES, RES)), cv2.COLOR_BGR2RGB) for f in r["files"]]
        x = (np.stack(imgs).astype(np.float32) / 255 - mean) / std
        with torch.no_grad():
            tok = m.forward_features(torch.from_numpy(x.transpose(0, 3, 1, 2)))
        cls, pt = tok[:, 0], tok[:, 1:]
        X[j] = torch.cat([cls, pt.mean(1), pt.max(1).values], 1).numpy().astype(np.float16)
        if j % 300 == 0:
            print(f"embedded {j}/{len(idx)} photos, {time.time() - t0:.0f}s", flush=True)
    np.savez_compressed(out, X=X, idx=np.array(idx))


def embed_all(rows):
    """Merge shard files feats_*.npz (from parallel jobs) or embed everything here."""
    import glob
    parts = sorted(glob.glob(os.path.join(DATA, "**", "feats_*.npz"), recursive=True))
    if parts:
        X = np.zeros((len(rows), 8, 1152), np.float16); got = np.zeros(len(rows), bool)
        for f in parts:
            z = np.load(f); X[z["idx"]] = z["X"]; got[z["idx"]] = True
        print(f"merged {len(parts)} shards, {got.sum()}/{len(rows)} photos", flush=True)
        return X, got
    out = os.path.join(DATA, "feats_all.npz")
    embed_rows(rows, list(range(len(rows))), out)
    return np.load(out)["X"], np.ones(len(rows), bool)


class Head(nn.Module):
    def __init__(self, d=1152):
        super().__init__()
        self.enc = nn.Sequential(nn.Dropout(0.2), nn.Linear(d, 256), nn.GELU(), nn.Dropout(0.3), nn.Linear(256, 64), nn.GELU())
        self.side = nn.Embedding(2, 64)
        self.reg = nn.Linear(128, 1)
        self.cls = nn.Linear(128, 1)

    def forward(self, x, s):
        h = self.enc(x)                                # B x 8 x 64
        p = torch.cat([h.max(1).values, h.mean(1)], 1) + torch.cat([self.side(s), self.side(s)], 1)
        return self.reg(p).squeeze(1), self.cls(p).squeeze(1)


def auc(y, p):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p)) if len(set(y)) == 2 else float("nan")


def main():
    meta = json.load(open(os.path.join(DATA, "meta.json")))
    rows = meta["rows"]
    sh = os.environ.get("EMBED_SHARD")
    if sh:
        i, n = map(int, sh.split("/"))
        embed_rows(rows, list(range(i, len(rows), n)), os.path.join(DATA, f"feats_{i}.npz"))
        return
    X, got = embed_all(rows)
    rows = [r for r, k in zip(rows, got) if k]; X = X[got].astype(np.float32)
    g = np.array([r["grade"] for r in rows], np.float32)
    s = np.array([1 if r["side"] == "back" else 0 for r in rows])
    ids = sorted({r["iid"] for r in rows}); random.shuffle(ids)
    n = len(ids); te = set(ids[:n // 5]); va = set(ids[n // 5: n // 5 + n // 10])
    split = np.array([2 if r["iid"] in te else 1 if r["iid"] in va else 0 for r in rows])
    mu = X[split == 0].reshape(-1, X.shape[2]).mean(0); sd = X[split == 0].reshape(-1, X.shape[2]).std(0) + 1e-5
    Xn = (X - mu) / sd
    T = lambda m: (torch.from_numpy(Xn[m]), torch.from_numpy(s[m]), torch.from_numpy(g[m]))
    tr, vl, ts = T(split == 0), T(split == 1), T(split == 2)
    model = Head()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=0.05)
    best, best_state, bad = -1, None, 0
    for ep in range(200):
        model.train()
        perm = torch.randperm(len(tr[0]))
        for b in range(0, len(perm), 64):
            i = perm[b:b + 64]
            xb = tr[0][i]
            xb = xb[:, torch.randperm(8)] + 0.05 * torch.randn_like(xb)      # crop order shuffle + noise
            r_, c_ = model(xb, tr[1][i])
            loss = nn.functional.smooth_l1_loss(r_, tr[2][i]) + nn.functional.binary_cross_entropy_with_logits(c_, (tr[2][i] >= 8).float())
            opt.zero_grad(); loss.backward(); opt.step()
        model.eval()
        with torch.no_grad():
            _, c_ = model(vl[0], vl[1])
        a = auc((vl[2] >= 8).numpy(), torch.sigmoid(c_).numpy())
        if a > best + 1e-4:
            best, best_state, bad = a, {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 15:
                break
    model.load_state_dict(best_state); model.eval()
    with torch.no_grad():
        r_, c_ = model(ts[0], ts[1])
    pg, pc, yg = r_.numpy(), torch.sigmoid(c_).numpy(), ts[2].numpy()
    # listing level: worst photo decides
    tid = [rows[i]["iid"] for i in np.where(split == 2)[0]]
    L = {}
    for k, a1, b1, y1 in zip(tid, pc, pg, yg):
        L.setdefault(k, [y1, [], []]); L[k][1].append(a1); L[k][2].append(b1)
    ly = np.array([v[0] for v in L.values()]); lp = np.array([min(v[1]) for v in L.values()]); lg = np.array([min(v[2]) for v in L.values()])
    rep = {"trained": time.strftime("%Y-%m-%d"), "listings": meta["listings"], "photos": meta["photos"], "usablePhotos": len(rows),
           "byGrade": {int(k): int((g == k).sum()) for k in range(1, 11)},
           "testPhotos": int(len(yg)), "testListings": len(L), "valAUC": round(best, 3),
           "photo": {"AUC_8plus_vs_7minus": round(auc(yg >= 8, pc), 3),
                     "AUC_8plus_vs_6minus": round(auc(yg[(yg >= 8) | (yg <= 6)] >= 8, pc[(yg >= 8) | (yg <= 6)]), 3),
                     "acc_at_0.5": round(float(((pc >= 0.5) == (yg >= 8)).mean()), 3),
                     "gradeMAE": round(float(np.abs(pg - yg).mean()), 2)},
           "listing": {"AUC_8plus_vs_7minus": round(auc(ly >= 8, lp), 3), "acc_at_0.5": round(float(((lp >= 0.5) == (ly >= 8)).mean()), 3),
                       "gradeMAE": round(float(np.abs(lg - ly).mean()), 2)},
           "meanPredictedGradeByTrueGrade": {int(k): round(float(pg[yg == k].mean()), 2) for k in range(1, 11) if (yg == k).any()},
           "meanP8plusByTrueGrade": {int(k): round(float(pc[yg == k].mean()), 3) for k in range(1, 11) if (yg == k).any()}}
    # high-confidence operating points: how often a confident 'yes' is really 8+
    for th in (0.6, 0.7, 0.8, 0.9):
        sel = pc >= th
        rep["photo"][f"precision_at_{th}"] = round(float((yg[sel] >= 8).mean()), 3) if sel.any() else None
        rep["photo"][f"coverage_at_{th}"] = round(float(sel.mean()), 3)
    os.makedirs(os.path.join(ROOT, "models"), exist_ok=True)
    torch.save({"state": model.state_dict(), "mu": torch.from_numpy(mu), "sd": torch.from_numpy(sd)}, os.path.join(ROOT, "models", "grader_v2.pt"))
    json.dump(rep, open(os.path.join(ROOT, "models", "grader_v2_report.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        os.makedirs(os.path.join(ROOT, "models"), exist_ok=True)
        open(os.path.join(ROOT, "models", "grader_error.txt"), "w").write(traceback.format_exc())
        raise
