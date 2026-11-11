#!/usr/bin/env python3
"""Grade-by-photo issues (Gaz, Nov 11: 'a grader tab'): download every image attached to a GitHub issue into
grading/submissions/issue-<n>-<slug>/<date>/ so grade_own.py grades it and the photos are KEPT for the record and for
retraining the grader (each photo set is later matched with the PSA grade when one comes back).
Usage: issue_photos.py <issue number> <title> <body file>  -> prints the submission key, or nothing if no photos."""
import os, re, sys, datetime, urllib.request
n, title, body = sys.argv[1], sys.argv[2], open(sys.argv[3]).read()
urls = re.findall(r'!\[[^\]]*\]\((https://[^)\s]+)\)', body) + re.findall(r'<img[^>]+src="(https://[^"]+)"', body)
urls += re.findall(r'(https://github\.com/user-attachments/assets/[0-9a-f-]+)', body)
seen, out = set(), []
for u in urls:
    if u not in seen: seen.add(u); out.append(u)
if not out: sys.exit(0)
slug = re.sub(r'[^a-z0-9]+', '-', re.sub(r'^\s*grade\s*:?\s*', '', title, flags=re.I).lower()).strip('-')[:40] or 'card'
date = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
key = f"issue-{n}-{slug}/{date}"
d = os.path.join('grading/submissions', key); os.makedirs(d, exist_ok=True)
tok = os.environ.get('GH_TOKEN', '')
for i, u in enumerate(out[:8], 1):
    h = {'User-Agent': 'ledger-grader'}
    if tok and 'github' in u: h['Authorization'] = 'token ' + tok
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=60) as r:
            data, ct = r.read(), r.headers.get('Content-Type', '')
    except Exception as e:
        print(f"skip {u}: {e}", file=sys.stderr); continue
    ext = 'png' if 'png' in ct else 'webp' if 'webp' in ct else 'jpg'
    open(os.path.join(d, f'photo{i}.{ext}'), 'wb').write(data)
print(key)
