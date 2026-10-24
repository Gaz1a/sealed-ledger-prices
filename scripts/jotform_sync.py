#!/usr/bin/env python3
"""Daily bridge from the Claude ledger tasks to this repo.

Scheduled Claude tasks cannot push to GitHub, so the Tracker posts the CHANGES to
the want list (and new rows for the price feed) to a private Jotform form
("Ledger sync"). Long answers do not survive the Jotform connector, so each post
is a small delta (under ~700 characters) and a big change is split into parts.

Payload v3, one per submission:
  {"v":3, "date":"YYYY-MM-DD", "batch":"YYYYMMDD-HHMM", "part":"i/k",
   "base":"<md5[:8] of the sorted want ids the Tracker diffed against>",
   "chk":"<md5[:8] of the sorted want ids after applying the whole batch>", "n": <want count>,
   "add": {id: [cond 's'|'n', title, set, target]},   # new or changed wants
   "del": [id, ...],                                  # no longer wanted
   "tr":  {id: [productId, title, variant]}}          # new w-/rp- rows for tracked.json

This job takes the newest batch with every part present, checks that its base
matches the repo, applies it, and writes the files only if the result matches chk.
Every run writes sync_status.json (Actions logs are not readable by the tasks).
Secrets: JOTFORM_API_KEY (read-only is enough). Stdlib only."""
import datetime, hashlib, json, os, re, sys, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORM_ID = os.environ.get("JOTFORM_FORM_ID", "262965110035047")
KEY = os.environ.get("JOTFORM_API_KEY", "")
API = os.environ.get("JOTFORM_API", "https://api.jotform.com")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,90}$")
NEW_TRACKED_RE = re.compile(r"^(w|rp)-\d{3,8}$")


def ids_hash(ids):
    return hashlib.md5(",".join(sorted(ids)).encode()).hexdigest()[:8]


def load(name, default):
    try:
        return json.load(open(os.path.join(ROOT, name)))
    except Exception:
        return default


def status(**kw):
    kw["ran"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    json.dump(kw, open(os.path.join(ROOT, "sync_status.json"), "w"), indent=1)
    print(json.dumps(kw))


def payloads():
    q = urllib.parse.urlencode({"apiKey": KEY, "limit": 200, "orderby": "created_at", "direction": "DESC"})
    with urllib.request.urlopen(f"{API}/form/{FORM_ID}/submissions?{q}", timeout=40) as r:
        subs = json.load(r).get("content") or []
    out = []
    for s in subs:
        if s.get("status") == "DELETED":
            continue
        for a in (s.get("answers") or {}).values():
            ans = a.get("answer")
            if isinstance(ans, str) and ans.lstrip().startswith("{"):
                try:
                    p = json.loads(ans)
                except Exception:
                    continue
                if isinstance(p, dict) and p.get("v") == 3 and re.match(r"^\d+/\d+$", str(p.get("part", ""))) \
                        and re.match(r"^\d{8}-\d{4}$", str(p.get("batch", ""))):
                    out.append(p)
    return out


def main():
    if not KEY:
        sys.exit("JOTFORM_API_KEY not set")
    batches = {}
    for p in payloads():
        batches.setdefault(str(p.get("batch")), []).append(p)
    complete = []
    for b, parts in batches.items():
        k = int(parts[0]["part"].split("/")[1])
        got = {int(p["part"].split("/")[0]): p for p in parts}
        if k >= 1 and set(got) == set(range(1, k + 1)):
            complete.append((b, [got[i] for i in range(1, k + 1)]))
    if not complete:
        status(ok=False, reason="no complete v3 batch found")
        sys.exit(1)
    complete.sort(key=lambda t: t[0], reverse=True)
    batch, parts = complete[0]
    head = parts[0]
    try:
        age = (datetime.date.today() - datetime.date.fromisoformat(str(head.get("date"))[:10])).days
    except Exception:
        age = 99

    wa = load("wants_auto.json", {})
    old = wa.get("items", {})
    tracked = load("tracked.json", {})
    info = dict(batch=batch, parts=len(parts), payloadDate=head.get("date"), wants=len(old))

    if wa.get("batch") == batch:
        status(ok=True, note="already applied", **info)
        return
    if age > 3:
        status(ok=False, reason=f"newest complete batch is {age} days old", **info)
        return
    if head.get("base") != ids_hash(old):
        status(ok=False, reason="base mismatch: batch was computed against a different want list", **info)
        sys.exit(1)

    items = {k: dict(v) for k, v in old.items()}
    added, removed, changed, added_t = [], [], [], []
    for p in parts:
        for k in p.get("del") or []:
            if k in items:
                items.pop(k)
                removed.append(k)
        for k, v in (p.get("add") or {}).items():
            if not ID_RE.match(str(k)) or not isinstance(v, list) or not v or v[0] not in ("s", "n"):
                continue
            prev = items.get(k, {})
            title = v[1] if len(v) > 1 and isinstance(v[1], str) and v[1] else prev.get("title") or (tracked.get(k) or {}).get("title") or k
            it = {"title": title[:200], "cond": "sealed" if v[0] == "s" else "nm"}
            st = v[2] if len(v) > 2 and isinstance(v[2], str) and v[2] else prev.get("set")
            if st:
                it["set"] = st[:120]
            if len(v) > 3 and isinstance(v[3], (int, float)) and 0 < v[3] < 100000:
                it["target"] = round(float(v[3]), 2)
            if k.startswith("jumbo-"):
                it["kind"] = "jumbo"
            for f in ("kind", "tcgProductId", "market", "status"):
                if f in prev and f not in it:
                    it[f] = prev[f]
            (changed if k in items else added).append(k)
            items[k] = it
        for k, t in (p.get("tr") or {}).items():
            if not NEW_TRACKED_RE.match(str(k)) or k in tracked or not isinstance(t, list) or not t:
                continue
            pid = t[0]
            if not isinstance(pid, int) or not (1000 <= pid < 10_000_000):
                continue
            tracked[k] = {"productId": pid, "title": str(t[1] if len(t) > 1 else k)[:200],
                          "variant": t[2] if len(t) > 2 and isinstance(t[2], str) else None}
            added_t.append(k)

    if ids_hash(items) != head.get("chk") or len(items) != head.get("n"):
        status(ok=False, reason=f"checksum mismatch after applying ({len(items)} vs {head.get('n')}); files unchanged", **info)
        sys.exit(1)

    wa.update({"generated": datetime.date.today().isoformat(), "payloadDate": head.get("date"), "batch": batch,
               "source": "Pokémon TCG Ledger, synced daily by the Tracker task via the Ledger sync form",
               "items": items})
    json.dump(wa, open(os.path.join(ROOT, "wants_auto.json"), "w"), indent=1, ensure_ascii=False)
    if added_t:
        json.dump(tracked, open(os.path.join(ROOT, "tracked.json"), "w"), indent=2, ensure_ascii=False)
    info["wants"] = len(items)
    status(ok=True, added=added, removed=removed, changed=len(changed), newTracked=added_t, **info)


if __name__ == "__main__":
    main()
