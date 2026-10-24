#!/usr/bin/env python3
"""Daily bridge from the Claude ledger tasks to this repo.

Scheduled Claude tasks cannot push to GitHub, so the Tracker posts a small JSON
payload to a private Jotform form ("Ledger sync") once a day. This job reads the
newest submission with a read-only Jotform API key and updates:

  wants_auto.json  - every unowned ledger row (drives the daily eBay scans)
  tracked.json     - NEW rows only (w-/rp- ids) so the daily price feed covers them

Payload (v2): {"v": 2, "date": "YYYY-MM-DD",
               "wants": {id: [cond 's'|'n', title, set, target]},
               "tracked": {id: {"productId": int, "title": str, "variant": str|null}}}

Everything is validated; anything malformed is skipped, never written.
Secrets: JOTFORM_API_KEY (read-only key is enough). Stdlib only."""
import datetime, json, os, re, sys, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORM_ID = os.environ.get("JOTFORM_FORM_ID", "262965110035047")
KEY = os.environ.get("JOTFORM_API_KEY", "")
API = os.environ.get("JOTFORM_API", "https://api.jotform.com")
TODAY = datetime.date.today()
ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,90}$")
NEW_TRACKED_RE = re.compile(r"^(w|rp)-\d{3,8}$")


def load(name, default):
    p = os.path.join(ROOT, name)
    try:
        return json.load(open(p))
    except Exception:
        return default


def latest_payload():
    # Do not trust the API's sort order: fetch a page and pick the newest valid payload ourselves.
    q = urllib.parse.urlencode({"apiKey": KEY, "orderby": "created_at", "direction": "DESC", "limit": 100})
    with urllib.request.urlopen(f"{API}/form/{FORM_ID}/submissions?{q}", timeout=40) as r:
        subs = json.load(r).get("content") or []
    found = []
    for s in subs:
        if s.get("status") == "DELETED":
            continue
        for a in (s.get("answers") or {}).values():
            ans = a.get("answer")
            if not isinstance(ans, str) or not ans.lstrip().startswith("{"):
                continue
            try:
                p = json.loads(ans)
            except Exception:
                continue
            if isinstance(p, dict) and p.get("v") in (1, 2) and isinstance(p.get("wants"), dict):
                found.append((str(p.get("date") or ""), s.get("created_at") or "", p))
    print(f"{len(subs)} submissions, {len(found)} valid payloads")
    if not found:
        return None, None
    found.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return found[0][2], found[0][1]


def status(**kw):
    """sync_status.json: what the last run did (Actions logs are not readable from the ledger tasks)."""
    kw["ran"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ")
    json.dump(kw, open(os.path.join(ROOT, "sync_status.json"), "w"), indent=1)


def main():
    if not KEY:
        sys.exit("JOTFORM_API_KEY not set")
    p, created = latest_payload()
    if not p:
        status(ok=False, reason="no valid payload found")
        sys.exit("no valid ledger-sync payload found")
    try:
        age = (TODAY - datetime.date.fromisoformat(str(p.get("date"))[:10])).days
    except Exception:
        age = 99
    print(f"newest payload: date {p.get('date')}, submitted {created}, {len(p['wants'])} wants")
    if age > 3:
        print(f"newest payload is {age} days old; leaving files unchanged")
        status(ok=False, reason=f"newest payload is {age} days old", payloadDate=p.get("date"), submittedAt=created)
        return

    tracked = load("tracked.json", {})
    old = load("wants_auto.json", {}).get("items", {})
    items = {}
    for k, v in p["wants"].items():
        if not ID_RE.match(str(k)):
            continue
        if isinstance(v, str):            # v1: just the condition code
            v = [v]
        if not isinstance(v, list) or not v or v[0] not in ("s", "n"):
            continue
        title = (v[1] if len(v) > 1 and isinstance(v[1], str) else "") or (tracked.get(k) or {}).get("title") or (old.get(k) or {}).get("title") or k
        item = {"title": title[:200], "cond": "sealed" if v[0] == "s" else "nm"}
        if len(v) > 2 and isinstance(v[2], str) and v[2]:
            item["set"] = v[2][:120]
        if len(v) > 3 and isinstance(v[3], (int, float)) and 0 < v[3] < 100000:
            item["target"] = round(float(v[3]), 2)
        if k.startswith("jumbo-"):
            item["kind"] = "jumbo"
        items[k] = item
    if not (20 <= len(items) <= 3000):
        status(ok=False, reason=f"suspicious want count {len(items)}", payloadDate=p.get("date"))
        sys.exit(f"suspicious want count {len(items)}; leaving files unchanged")

    added_t = []
    for k, t in (p.get("tracked") or {}).items():
        if not NEW_TRACKED_RE.match(str(k)) or k in tracked or not isinstance(t, dict):
            continue
        pid = t.get("productId")
        if not isinstance(pid, int) or not (1000 <= pid < 10_000_000):
            continue
        tracked[k] = {"productId": pid, "title": str(t.get("title") or k)[:200], "variant": t.get("variant") if isinstance(t.get("variant"), str) else None}
        added_t.append(k)

    added = sorted(set(items) - set(old))
    removed = sorted(set(old) - set(items))
    out = {"generated": TODAY.isoformat(), "payloadDate": p.get("date"), "submittedAt": created,
           "source": "Pokémon TCG Ledger, posted daily by the Tracker task via the Ledger sync form",
           "items": items}
    json.dump(out, open(os.path.join(ROOT, "wants_auto.json"), "w"), indent=1, ensure_ascii=False)
    if added_t:
        json.dump(tracked, open(os.path.join(ROOT, "tracked.json"), "w"), indent=2, ensure_ascii=False)
    status(ok=True, payloadDate=p.get("date"), submittedAt=created, wants=len(items), added=len(added), removed=len(removed), newTracked=added_t)
    print(f"wants: {len(items)} rows (+{len(added)} / -{len(removed)}); tracked.json: +{len(added_t)} {added_t}")


if __name__ == "__main__":
    main()
