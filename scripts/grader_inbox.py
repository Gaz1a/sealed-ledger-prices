#!/usr/bin/env python3
"""Card Grader inbox (Gaz, Nov 11: 'I just want to give it a link', 'a proper way to do my own photos').
Gaz submits the Jotform 'Card Grader' form (link from the ledger's Grader tab): an eBay link and/or photos.
  poll  -> finds new submissions, downloads photos into grading/submissions/jf-<sub>-<slug>/<date>/ (kept for good),
           writes $OUT/jobs.json [{sub, kind: 'photos'|'link', key|url, title}]; prints the job count.
  post  -> writes each job's result back to Jotform (edits the submission's 'Grader result' answer; if the API key is
           read-only, posts a result-only submission through the public form instead) and records the sub as done.
State: grading/inbox_state.json {done: [submission ids]}. Stdlib only. Secrets: JOTFORM_API_KEY."""
import json, os, re, sys, datetime, urllib.request, urllib.parse
FORM = os.environ.get("GRADER_FORM_ID", "263147084103046")
KEY = os.environ.get("JOTFORM_API_KEY", "")
API = "https://api.jotform.com"
STATE = "grading/inbox_state.json"
OUT = os.environ.get("OUT", "/tmp/inbox")
def api(path, **q):
    q["apiKey"] = KEY
    with urllib.request.urlopen(f"{API}{path}?{urllib.parse.urlencode(q)}", timeout=40) as r: return json.load(r)["content"]
def questions():
    qs = api(f"/form/{FORM}/questions")
    def find(*words, typ=None):
        for qid, q in qs.items():
            t = (q.get("text") or "").lower()
            if (typ is None or q.get("type") == typ) and all(w in t for w in words): return qid, q
        return None, None
    return {"link": find("ebay"), "card": find("card"), "photos": find("photo", typ="control_fileupload") if find("photo", typ="control_fileupload")[0] else find("photo"),
            "result": find("result")}
def state():
    try: return json.load(open(STATE))
    except Exception: return {"done": []}
def ans(sub, qid):
    a = (sub.get("answers") or {}).get(qid, {}).get("answer") if qid else None
    return a
def poll():
    os.makedirs(OUT, exist_ok=True)
    Q, st = questions(), state()
    subs = api(f"/form/{FORM}/submissions", limit=30, orderby="created_at", direction="DESC")
    jobs = []
    for s in subs:
        sid = s["id"]
        if sid in st["done"] or s.get("status") == "DELETED": continue
        if st.get("tries", {}).get(sid, 0) >= 4: continue
        if (ans(s, Q["result"][0]) or "").strip(): st["done"].append(sid); continue   # a result-only row
        link = (ans(s, Q["link"][0]) or "").strip()
        card = (ans(s, Q["card"][0]) or "").strip()
        photos = ans(s, Q["photos"][0]) or []
        if isinstance(photos, str): photos = [p for p in re.split(r"[\s,]+", photos) if p.startswith("http")]
        if photos:
            slug = re.sub(r"[^a-z0-9]+", "-", card.lower()).strip("-")[:40] or "card"
            date = s.get("created_at", "")[:10] or datetime.date.today().isoformat()
            key = f"jf-{sid}-{slug}/{date}"; d = os.path.join("grading/submissions", key); os.makedirs(d, exist_ok=True)
            n = 0
            for i, u in enumerate(photos[:8], 1):
                for url in (u, u + ("&" if "?" in u else "?") + "apiKey=" + KEY):
                    try:
                        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ledger-grader"}), timeout=60) as r:
                            data, ct = r.read(), r.headers.get("Content-Type", "")
                        if "html" in ct: continue
                        ext = os.path.splitext(urllib.parse.urlparse(u).path)[1].lower() or ".jpg"
                        open(os.path.join(d, f"photo{i}{ext}"), "wb").write(data); n += 1; break
                    except Exception as e: print("photo fetch failed", i, e, file=sys.stderr)
            if n: jobs.append({"sub": sid, "kind": "photos", "key": key, "title": card or "photos"})
        if link: jobs.append({"sub": sid, "kind": "link", "url": link, "title": card or link})
        if not photos and not link: st["done"].append(sid)
    json.dump(st, open(STATE, "w"), indent=1)
    json.dump(jobs, open(os.path.join(OUT, "jobs.json"), "w"))
    print(len(jobs))
def post():
    Q, st = questions(), state()
    jobs = json.load(open(os.path.join(OUT, "jobs.json")))
    rq, rname = Q["result"][0], (Q["result"][1] or {}).get("name", "graderResult")
    for j in jobs:
        txt = open(os.path.join(OUT, f"result_{j['sub']}_{j['kind']}.txt")).read().strip() if os.path.exists(os.path.join(OUT, f"result_{j['sub']}_{j['kind']}.txt")) else "Could not grade this one."
        txt = re.sub(r"!\[[^\]]*\]\(([^)]+)\)", r"Photo sheet: \1", txt)[:3500]
        tries = st.setdefault("tries", {}); tries[j["sub"]] = tries.get(j["sub"], 0) + 1
        if txt.startswith("Could not") and tries[j["sub"]] < 4:
            if j["sub"] in st["done"]: st["done"].remove(j["sub"])
            print("will retry", j["sub"]); continue          # eBay throttling etc: try again next run
        try:   # keep the answer on Gaz's own row too
            body = urllib.parse.urlencode({f"submission[{rq}]": txt}).encode()
            urllib.request.urlopen(urllib.request.Request(f"{API}/submission/{j['sub']}?apiKey={KEY}", data=body), timeout=40).read()
        except Exception as e: print("edit failed:", e, file=sys.stderr)
        # a result row (fires the 'Grader result' email to Gaz)
        lq, lname = Q["card"][0], (Q["card"][1] or {}).get("name", "card")
        ukq, ukname = Q["link"][0], (Q["link"][1] or {}).get("name", "link")
        body = urllib.parse.urlencode({f"q{rq}_{rname}": txt, f"q{lq}_{lname}": f"{j['title']}"[:200],
                                       f"q{ukq}_{ukname}": j.get("url", "")}).encode()
        urllib.request.urlopen(urllib.request.Request(f"https://submit.jotform.com/submit/{FORM}/", data=body, headers={"User-Agent": "ledger-grader"}), timeout=40).read()
        if j["sub"] not in st["done"]: st["done"].append(j["sub"])
    st["done"] = st["done"][-500:]
    json.dump(st, open(STATE, "w"), indent=1)
    print("posted", len(jobs))
if __name__ == "__main__":
    {"poll": poll, "post": post}[sys.argv[1]]()
