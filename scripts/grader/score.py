"""Ledger card grader v2: score one photo.

Trained on ~18,000 photos of PSA-graded Pokemon cards (PSA 1-10), tested on 1,888 listings it
never saw (models/grader_v2_report.json): AUC 0.85 for "PSA 8+ vs 7 or lower" per listing; a
confident score (p8 >= 0.8) was PSA 8+ 81% of the time, p8 >= 0.9 87%. Learned from slabbed cards,
so on raw-card photos treat it as one signal next to the visual check, never as the only one.

    g = Grader();  g.score(bgr_image) -> {"p8": 0.0-1.0, "grade": est. PSA grade, "side": "front"|"back", "px": card px} or None
"""
import os, sys

import cv2
import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from collect import crops, find_card_any, side  # noqa: E402
from embed_train import Head, RES  # noqa: E402

MODEL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "models", "grader_v2.pt")


class Grader:
    def __init__(self, path=MODEL):
        import timm
        ck = torch.load(path, map_location="cpu")
        self.head = Head(); self.head.load_state_dict(ck["state"]); self.head.eval()
        self.mu, self.sd = ck["mu"], ck["sd"]
        self.vit = timm.create_model("vit_small_patch14_dinov2.lvd142m", pretrained=True, num_classes=0, img_size=RES).eval()
        self.mean = np.array([0.485, 0.456, 0.406], np.float32); self.std = np.array([0.229, 0.224, 0.225], np.float32)

    def score(self, img):
        card, px = find_card_any(img)
        if card is None or px < 450:
            return None
        cs = [cv2.cvtColor(cv2.resize(c, (RES, RES)), cv2.COLOR_BGR2RGB) for c in crops(card)]
        x = (np.stack(cs).astype(np.float32) / 255 - self.mean) / self.std
        with torch.no_grad():
            tok = self.vit.forward_features(torch.from_numpy(x.transpose(0, 3, 1, 2)))
            f = torch.cat([tok[:, 0], tok[:, 1:].mean(1), tok[:, 1:].max(1).values], 1)
            f = ((f - self.mu) / self.sd)[None]
            sd_ = side(card)
            r, c = self.head(f, torch.tensor([1 if sd_ == "back" else 0]))
        return {"p8": round(float(torch.sigmoid(c)[0]), 3), "grade": round(float(r[0]), 1), "side": sd_, "px": int(px)}
