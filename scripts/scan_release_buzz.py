#!/usr/bin/env python3
"""Weekly release-buzz scan. For each upcoming release/restock/drawing in drops.json
(within the next ~35 days), searches Reddit's public search (r/pkmntcgtrades,
r/PokemonTCG) and Google News for what people are saying about actually getting it
at MSRP. Pure collection, no judgment — writes buzz.json / buzz.md for Claude to
read and summarize in the weekly digest. Stdlib only; failures are logged and
skipped rather than crashing the run."""
import json, re, sys, time, datetime, urllib.request, urllib.parse
import xml.etree.ElementTree as ET

ROOT = "."
TODAY = datetime.date.today()
WINDOW_DAYS = 35
SUBS = ["pkmntcgtrades", "PokemonTCG"]
UA = "Mozilla/5.0 (compatible; sealed-ledger-buzz/1.0; +https://github.com/Gaz1a/sealed-ledger-prices)"

def get(url, headers=None, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                print("FAIL", url, e, file=sys.stderr)
                return None
            time.sleep(2 * (i + 1))

def clean_query(text):
    text = re.sub(r"\(.*?\)", "", text)          # drop parenthetical asides
    text = re.split(r"[:—-]", text, 1)[0]     # keep the part before a dash/colon
    text = re.sub(r"[^\w\s]", " ", text)
    words = text.split()
    return " ".join(words[:8])

def reddit_search(query):
    out = []
    q = urllib.parse.quote(query + " (restock OR drawing OR MSRP OR in-store)")
    for sub in SUBS:
        url = f"https://www.reddit.com/r/{sub}/search.json?q={q}&restrict_sr=1&sort=new&limit=5&t=month"
        raw = get(url)
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except Exception:
            continue
        for c in d.get("data", {}).get("children", []):
            p = c.get("data", {})
            out.append({"source": "r/" + sub, "title": p.get("title"),
                        "url": "https://reddit.com" + p.get("permalink", ""),
                        "created": datetime.datetime.utcfromtimestamp(p.get("created_utc", 0)).strftime("%Y-%m-%d"),
                        "score": p.get("score", 0)})
        time.sleep(1)
    out.sort(key=lambda x: -x["score"])
    return out[:5]

def news_search(query):
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}+when:35d&hl=en-US&gl=US&ceid=US:en"
    raw = get(url)
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except Exception:
        return []
    out = []
    for item in root.findall(".//item")[:5]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        source = item.findtext("source") or ""
        out.append({"source": source or "Google News", "title": title, "url": link, "created": pub})
    return out

def main():
    try:
        drops = json.load(open(f"{ROOT}/drops.json"))
    except Exception as e:
        sys.exit(f"could not read drops.json: {e}")
    upcoming = []
    for d in drops:
        try:
            dd = datetime.date.fromisoformat(d["date"])
        except Exception:
            continue
        age = (dd - TODAY).days
        if 0 <= age <= WINDOW_DAYS:
            upcoming.append({"date": d["date"], "days_out": age, "text": d["text"]})
    upcoming.sort(key=lambda x: x["date"])

    entries = []
    for u in upcoming:
        q = clean_query(u["text"])
        if not q:
            continue
        reddit = reddit_search(q)
        news = news_search(q)
        entries.append({**u, "query": q, "reddit": reddit, "news": news})

    out = {"generated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
           "window_days": WINDOW_DAYS, "entries": entries}
    json.dump(out, open(f"{ROOT}/buzz.json", "w"), indent=1, ensure_ascii=False)

    lines = [f"# Release buzz — {TODAY}", f"Upcoming releases in the next {WINDOW_DAYS} days, and what Reddit/News say about getting them.", ""]
    if not entries:
        lines.append("Nothing upcoming in the window right now.")
    for e in entries:
        lines.append(f"## {e['date']} — {e['text']}  (in {e['days_out']}d)")
        if e["reddit"]:
            for r in e["reddit"]:
                lines.append(f"- Reddit ({r['source']}, {r['created']}, score {r['score']}): [{r['title']}]({r['url']})")
        if e["news"]:
            for n in e["news"]:
                lines.append(f"- News ({n['source']}): [{n['title']}]({n['url']})")
        if not e["reddit"] and not e["news"]:
            lines.append("- No matches this week.")
        lines.append("")
    open(f"{ROOT}/buzz.md", "w").write("\n".join(lines) + "\n")
    print(f"scanned {len(upcoming)} upcoming release(s), wrote buzz.json/buzz.md")

if __name__ == "__main__":
    main()
