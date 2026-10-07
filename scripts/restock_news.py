#!/usr/bin/env python3
"""Reprint / restock news from public RSS feeds only (no retailer scraping) -> restock_news.json.
Feeds are listed in restock_feeds.json. Headlines and links only. Fails soft per feed."""
import json, os, re, time, datetime, hashlib, urllib.request, email.utils
import xml.etree.ElementTree as ET
TODAY = datetime.date.today()
UA = "sealed-ledger-news/1.0 (personal research; RSS reader)"
CLASSES = {"reprint": r"reprint|print run|overprint", "restock": r"restock|re-stock|back in stock|in stock|sold out|allocation|limit per",
           "preorder": r"pre-?order", "delay": r"delay", "release": r"release date|launch", "price": r"price (increase|hike)|msrp"}
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
def txt(e, *names):
    for n in names:
        x = e.find(n)
        if x is not None and (x.text or "").strip(): return x.text.strip()
        for c in e:
            if c.tag.split("}")[-1] == n.split("}")[-1] and (c.text or "").strip(): return c.text.strip()
    return ""
def parse_date(s):
    try: return email.utils.parsedate_to_datetime(s).date().isoformat()
    except Exception:
        try: return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
        except Exception: return None
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml"})
    with urllib.request.urlopen(req, timeout=30) as r: return r.read()
def main():
    cfg = load("restock_feeds.json", {"feeds": [], "keywords": []})
    kws = [k.lower() for k in cfg["keywords"]]
    prev = load("restock_news.json", {}); items = {i["id"]: i for i in prev.get("items", []) if re.search(r"pok[eé]mon|\btcg\b", i["title"].lower())}
    status = {}; new = 0
    for f in cfg["feeds"]:
        if not f.get("enabled"): status[f["id"]] = "disabled"; continue
        try:
            root = ET.fromstring(fetch(f["url"]))
            ent = root.findall(".//item") or [e for e in root.iter() if e.tag.split("}")[-1] == "entry"]
            n = 0
            for e in ent[:60]:
                title = re.sub(r"\s+", " ", txt(e, "title")); 
                link = txt(e, "link") or next((c.get("href") for c in e if c.tag.split("}")[-1] == "link" and c.get("href")), "")
                desc = re.sub(r"<[^>]+>", " ", txt(e, "description", "summary"))[:400]
                hay = (title + " " + desc).lower()
                hit = [k for k in kws if k in hay]
                if not hit or not re.search(r"pok[eé]mon|\btcg\b", hay): continue
                iid = hashlib.sha1((f["id"] + (link or title)).encode()).hexdigest()[:12]
                if iid in items: continue
                cls = [c for c, rx in CLASSES.items() if re.search(rx, hay)]
                items[iid] = {"id": iid, "feed": f["id"], "title": title, "link": link, "published": parse_date(txt(e, "pubDate", "published", "updated")),
                              "firstSeen": TODAY.isoformat(), "classes": cls, "matched": hit[:6]}
                n += 1; new += 1
            status[f["id"]] = f"ok ({len(ent)} entries, {n} new matches)"
        except Exception as ex:
            status[f["id"]] = f"failed: {type(ex).__name__} {getattr(ex, 'code', '')}".strip()
        time.sleep(2)
    cut = (TODAY - datetime.timedelta(days=90)).isoformat()
    kept = sorted([i for i in items.values() if (i.get("published") or i["firstSeen"]) >= cut], key=lambda i: i.get("published") or i["firstSeen"], reverse=True)
    json.dump({"generated": TODAY.isoformat(), "note": "Headlines and links from public RSS feeds. News signal only; verify at the source. No retailer pages are scraped.",
               "feedStatus": status, "items": kept}, open("restock_news.json", "w"), indent=1, ensure_ascii=False)
    print(f"{new} new, {len(kept)} kept |", status)
if __name__ == "__main__": main()
