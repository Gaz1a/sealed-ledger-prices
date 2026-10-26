#!/usr/bin/env python3
"""On-demand listing check: turn photo_check.py output into the issue comment and append to manual.json.
Usage: check_comment.py <photo_out_dir> <checks_branch_dir> <issue_number>  -> prints the comment markdown."""
import datetime, json, os, shutil, sys

src, dst, issue = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(os.path.join(src, "checks.json")))
RAW = "https://raw.githubusercontent.com/Gaz1a/sealed-ledger-prices/checks/"
if not d.get("listings"):
    print(f"Could not check that listing: {d.get('error', 'no photos found')}.\n\nPaste a full eBay listing link (ebay.com/itm/...) in a new issue.")
    sys.exit(0)
iid, x = next(iter(d["listings"].items()))
p8 = x.get("graderP8")
flags = [f for f in x.get("flags", []) if not f.startswith("grader:")]
if p8 is None:
    grade = "NOT SCORED: the card could not be picked out of the photos (toploader, glare, angle). Judge the sheet by eye."
elif p8 >= 0.7:
    grade = f"PASSES the grader bar: P(PSA 8+) {p8} (0.7 needed), est. PSA {x.get('graderGrade')}."
elif p8 >= 0.4:
    grade = f"BORDERLINE: P(PSA 8+) {p8} (0.7 needed for a buy), est. PSA {x.get('graderGrade')}. Watch, ask the seller for sharp back photos."
else:
    grade = f"VETO: P(PSA 8+) {p8}, est. PSA {x.get('graderGrade')}. Likely PSA 7 or lower; not Near Mint for our rule."
lines = [f"**{x.get('title') or iid}**", ""]
if x.get("price"):
    lines.append(f"Listed ${x['price']}" + (f" · {x['condition']}" if x.get("condition") else "") + (f" · seller {x['seller']}" if x.get("seller") else ""))
lines += ["", f"Grader: {grade}", ""]
lines += (["Measured flags:"] + [f"- {f}" for f in flags]) if flags else ["Measured flags: none (no back-edge whitening found, centering within 65/35 where measurable)."]
sheet = None
if x.get("sheet"):
    os.makedirs(os.path.join(dst, "manual"), exist_ok=True)
    fn = f"manual/{issue}_{os.path.basename(x['sheet'])}"
    shutil.copy(os.path.join(src, x["sheet"]), os.path.join(dst, fn))
    sheet = fn
    lines += ["", f"![photo sheet]({RAW}{fn})", "", "Sheet: front/back flattened with zoomed corners; check the back edges for white, the corners for fraying."]
lines += ["", "The final call is the eye check against the PSA 8 rubric (docs/nm_rubric.md); tomorrow's Buy Hunter email includes its verdict on this listing.",
          "", x.get("url") or ""]
log = os.path.join(dst, "manual.json")
try:
    m = json.load(open(log))
except Exception:
    m = {"checks": []}
m["checks"] = [c for c in m["checks"] if c.get("issue") != int(issue)] + [{
    "issue": int(issue), "checked": d["generated"], "itemId": iid, "url": x.get("url"), "title": x.get("title"), "price": x.get("price"),
    "graderP8": p8, "graderGrade": x.get("graderGrade"), "flags": x.get("flags", []), "sheet": sheet, "visualVerdict": None}]
m["checks"] = m["checks"][-200:]
json.dump(m, open(log, "w"), indent=1, ensure_ascii=False)
print("\n".join(lines))
