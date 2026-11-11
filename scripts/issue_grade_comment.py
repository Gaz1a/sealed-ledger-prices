#!/usr/bin/env python3
"""Turn grading/results.json[key] into the issue reply. Usage: issue_grade_comment.py <key>"""
import json, sys
key = sys.argv[1]; x = json.load(open('grading/results.json')).get(key)
RAW = 'https://raw.githubusercontent.com/Gaz1a/sealed-ledger-prices/main/'
if not x:
    print("I couldn't grade those photos. Attach a clear front and back photo (card flat, good light, out of the sleeve) in a new issue."); sys.exit()
p8, g = x.get('graderP8'), x.get('graderGrade')
if p8 is None: v = 'NOT SCORED: the card could not be picked out of the photos. Try flat, straight-on, out of the sleeve, on a plain light background.'
elif p8 >= 0.7: v = f'PASSES: chance of PSA 8+ {p8} (0.7 needed), est. PSA {g}.'
elif p8 >= 0.4: v = f'BORDERLINE: chance of PSA 8+ {p8} (0.7 needed), est. PSA {g}. Get sharper back and corner photos.'
else: v = f'VETO: chance of PSA 8+ {p8}, est. PSA {g}. Likely PSA 7 or lower.'
fl = [f for f in x.get('flags', [])]
lines = [f"Grader: {v}", "", "Per photo: " + ", ".join(f"photo {s['photo']} {s['side']} {s['p8']} (PSA {s['grade']})" for s in x.get('grader', [])), ""]
lines += (["Measured flags:"] + [f"- {f}" for f in fl]) if fl else ["Measured flags: none."]
if x.get('sheet'): lines += ["", f"![sheet]({RAW}{x['sheet']})"]
lines += ["", f"Saved as `{key}` with the photos, so this check is on record and can be matched with the real PSA grade later."]
print("\n".join(lines))
