"""Feed-staleness check, run by the daily price workflow. Flags any listed feed whose `generated` date is older than its limit.
Writes feed_staleness.json, adds a `feedStaleness` list to prices.json (the daily run's output) and prints GitHub warnings. Never fails the run."""
import json, os, datetime
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
NOW = datetime.datetime.now(datetime.timezone.utc)
FEEDS = {"untracked_sealed.json": 7}          # file -> max age in days; add more feeds here
def parse(v):
    try:
        d = datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except Exception: return None
def main():
    out = []
    for f, mx in FEEDS.items():
        try: g = json.load(open(os.path.join(ROOT, f))); gen = g.get("generatedAt") or g.get("generated")
        except Exception as e: out.append({"feed": f, "status": "unreadable", "maxAgeDays": mx, "error": str(e)[:80]}); continue
        d = parse(gen)
        age = round((NOW - d).total_seconds() / 86400, 1) if d else None
        st = "missing generated date" if d is None else ("STALE" if age > mx else "ok")
        out.append({"feed": f, "generated": gen, "ageDays": age, "maxAgeDays": mx, "status": st})
        if st != "ok": print(f"::warning::feed {f} is {st}: generated {gen}, age {age} days (limit {mx})")
    res = {"checked": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "feeds": out, "stale": [x["feed"] for x in out if x["status"] != "ok"]}
    json.dump(res, open(os.path.join(ROOT, "feed_staleness.json"), "w"), indent=1)
    try:
        pj = os.path.join(ROOT, "prices.json"); p = json.load(open(pj)); p["feedStaleness"] = res
        json.dump(p, open(pj, "w"), indent=1)
    except Exception as e: print("prices.json not updated:", e)
    print("stale feeds:", res["stale"] or "none")
if __name__ == "__main__": main()
