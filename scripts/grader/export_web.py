#!/usr/bin/env python3
"""Export the PSA grader (dinov2-small + head) to one ONNX graph for the ledger page (grades photos in the browser).
Input: crops float32 [8,3,280,280] (ImageNet-normalised RGB, the 8 edge/corner crops of the flattened card), side int64 [1]
(0 front, 1 back). Output: p8 [1] (P(PSA 8+)), grade [1]. Writes models/web/grader.int8.onnx split into <=12 MB parts plus
models/web/check.json (torch vs onnx-int8 on real photos, so drift is visible)."""
import glob, json, os, sys
import numpy as np, torch, cv2
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from score import Grader
from collect import crops, find_card_any, side
from embed_train import RES
OUT = os.path.join(HERE, "..", "..", "models", "web"); os.makedirs(OUT, exist_ok=True)
G = Grader()
class Web(torch.nn.Module):
    def __init__(s):
        super().__init__(); s.vit, s.head = G.vit, G.head
        s.register_buffer("mu", torch.as_tensor(G.mu).float().reshape(1, -1)); s.register_buffer("sd", torch.as_tensor(G.sd).float().reshape(1, -1))
    def forward(s, x, sd):
        # x: 8 edge/corner crops + 1 whole card (all 280x280). The whole card's CLS vector (L2-normalised) is used by the
        # ledger page to recognise which ledger card the photo shows, by comparing with the ledger's own card pictures.
        tok = s.vit.forward_features(x)
        t8 = tok[:8]
        f = torch.cat([t8[:, 0], t8[:, 1:].mean(1), t8[:, 1:].max(1).values], 1)
        f = ((f - s.mu) / s.sd)[None]
        r, c = s.head(f, sd)
        e = tok[8:, 0]; e = e / e.norm(dim=1, keepdim=True)
        return torch.sigmoid(c), r, e
m = Web().eval()
x = torch.randn(9, 3, RES, RES); sd = torch.tensor([0])
fp = os.path.join(OUT, "grader.fp32.onnx")
torch.onnx.export(m, (x, sd), fp, input_names=["crops", "side"], output_names=["p8", "grade", "emb"], opset_version=17, dynamo=False)
from onnxruntime.quantization import quantize_dynamic, QuantType
q = os.path.join(OUT, "grader.int8.onnx")
quantize_dynamic(fp, q, weight_type=QuantType.QInt8, per_channel=True)
import onnxruntime as ort
sf, sq = ort.InferenceSession(fp), ort.InferenceSession(q)
rows = []
for f in sorted(glob.glob(os.path.join(HERE, "..", "..", "grading", "submissions", "*", "*", "*")))[:12]:
    img = cv2.imread(f)
    if img is None: continue
    card, px = find_card_any(img)
    if card is None or px < 450: continue
    cs = [cv2.cvtColor(cv2.resize(c, (RES, RES)), cv2.COLOR_BGR2RGB) for c in crops(card)]
    cs.append(cv2.cvtColor(cv2.resize(card, (RES, RES), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB))
    xx = ((np.stack(cs).astype(np.float32) / 255 - G.mean) / G.std).transpose(0, 3, 1, 2).astype(np.float32)
    s_ = np.array([1 if side(card) == "back" else 0], np.int64)
    t = G.score(img); a = sf.run(None, {"crops": xx, "side": s_}); b = sq.run(None, {"crops": xx, "side": s_})
    rows.append({"file": os.path.relpath(f, os.path.join(HERE, "..", "..")), "torch": t, "fp32": [round(float(a[0][0]), 3), round(float(a[1][0]), 2)], "int8": [round(float(b[0][0]), 3), round(float(b[1][0]), 2)]})
    if len(rows) == 1: np.save(os.path.join(OUT, "check_input.npy"), xx)
json.dump({"res": RES, "rows": rows}, open(os.path.join(OUT, "check.json"), "w"), indent=1)
drift = max([abs(r["int8"][0] - r["fp32"][0]) for r in rows] or [1])
pick = q if drift <= 0.03 else fp          # int8 only if it agrees with the full model to within 0.03
for f in glob.glob(os.path.join(OUT, "grader.int8.part*")): os.remove(f)
refs = {}; Rd = os.path.join(HERE, "..", "..", "grading", "ref_thumbs")
z = np.zeros((8, 3, RES, RES), np.float32)
for f in sorted(glob.glob(os.path.join(Rd, "*.webp"))):
    im = cv2.imread(f)
    if im is None: continue
    a1 = cv2.cvtColor(cv2.resize(im, (RES, RES), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    xx = np.concatenate([z, (((a1.astype(np.float32) / 255 - G.mean) / G.std).transpose(2, 0, 1)[None]).astype(np.float32)])
    refs[os.path.basename(f)[:-5]] = sf.run(None, {"crops": xx, "side": np.array([0], np.int64)})[2][0]
import base64
keys = sorted(refs); M = np.stack([refs[k] for k in keys]).astype(np.float16) if keys else np.zeros((0, 384), np.float16)
json.dump({"dim": int(M.shape[1]) if len(keys) else 384, "keys": keys, "f16": base64.b64encode(M.tobytes()).decode()}, open(os.path.join(OUT, "refs.json"), "w"))
print("refs", len(keys))
data = open(pick, "rb").read(); n = 0
for i in range(0, len(data), 12 * 1024 * 1024):
    open(os.path.join(OUT, f"grader.int8.part{n}"), "wb").write(data[i:i + 12 * 1024 * 1024]); n += 1
json.dump({"parts": n, "bytes": len(data), "kind": "int8" if pick == q else "fp32", "int8Drift": round(drift, 3)}, open(os.path.join(OUT, "parts.json"), "w"))
os.remove(fp); os.remove(q)
print(json.dumps(rows, indent=1))
