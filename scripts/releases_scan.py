#!/usr/bin/env python3
"""Weekly release calendar feed (Gaz, Nov 17): upcoming Pokémon TCG sets and products from free public sources.
Writes releases.json {generated, sources {name: status}, items [{date, name, lang, kind, source, url, confirmed}]}.
The Tracker copies upcoming items into the ledger's calendar (auto entries). Sources:
  tcgplayer-en / tcgplayer-jp : TCGplayer catalog via tcgcsv (sets with a publishedOn date from 30 days ago to 9 months ahead)
  pokemon-news               : official Pokémon news / press RSS (TCG headlines with a date in them)
  pokebeach                  : PokeBeach RSS (English release dates and leaks)
  pokemon-card-jp            : Pokémon Japan's card site product list (Japanese release dates, 2-3 months ahead of English)
Each source fails independently; the status says which worked."""
import json, os, re, datetime, html, urllib.request, xml.etree.ElementTree as ET
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TODAY = datetime.date.today()
MONTHS = {m: i for i, m in enumerate(["january","february","march","april","may","june","july","august","september","october","november","december"], 1)}
def fetch(url, accept="*/*"):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "en-US,en;q=0.9"}), timeout=40) as r:
        return r.read()
def window(d): return d and TODAY - datetime.timedelta(days=30) <= d <= TODAY + datetime.timedelta(days=270)
def en_dates(t):
    out = []
    for m in re.finditer(r"\b(" + "|".join(MONTHS) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", t, re.I):
        try: out.append(datetime.date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))))
        except ValueError: pass
    return out
items, status = [], {}
def add(date, name, lang, kind, source, url, confirmed):
    if window(date): items.append({"date": date.isoformat(), "name": name.strip()[:160], "lang": lang, "kind": kind, "source": source, "url": url, "confirmed": confirmed})
# 1. TCGplayer catalog (tcgcsv)
for cat, lang in ((3, "EN"), (85, "JP")):
    try:
        g = json.loads(fetch(f"https://tcgcsv.com/tcgplayer/{cat}/groups"))["results"]; n0 = len(items)
        for x in g:
            try: d = datetime.date.fromisoformat(x["publishedOn"][:10])
            except Exception: continue
            add(d, x["name"], lang, "set", "TCGplayer catalog", f"https://www.tcgplayer.com/search/pokemon{'-japan' if cat == 85 else ''}/{x.get('abbreviation') or ''}".rstrip('/'), True)
        status[f"tcgplayer-{lang.lower()}"] = f"ok ({len(items) - n0} in window)"
    except Exception as e: status[f"tcgplayer-{lang.lower()}"] = f"failed: {e}"[:120]
# 2-3. RSS: official Pokémon news / press, PokeBeach
TCG = re.compile(r"\b(TCG|Trading Card|expansion|Elite Trainer|Booster|Collection|Premium|set)\b", re.I)
for name, url in (("pokemon-news", "https://press.pokemon.com/en/rss"), ("pokemon-news-alt", "https://www.pokemon.com/us/pokemon-news/rss"),
                  ("pokebeach", "https://www.pokebeach.com/feed"), ("pokebeach-alt", "https://www.pokebeach.com/forums/forums/-/index.rss")):
    try:
        root = ET.fromstring(fetch(url, "application/rss+xml, application/xml, text/xml")); n0 = len(items)
        for it in root.iter():
            if it.tag.split("}")[-1] not in ("item", "entry"): continue
            get = lambda k: next((c.text or "" for c in it if c.tag.split("}")[-1] == k), "")
            title, link = html.unescape(get("title")), get("link") or next((c.get("href") for c in it if c.tag.split("}")[-1] == "link"), "")
            body = re.sub(r"<[^>]+>", " ", html.unescape(get("description") or get("summary") or get("encoded")))
            if not TCG.search(title): continue
            for d in en_dates(title + " " + body)[:2]:
                add(d, title, "EN", "news", name.replace("-alt", ""), link, name.startswith("pokemon-news"))
        status[name] = f"ok ({len(items) - n0} dated)"
    except Exception as e: status[name] = f"failed: {e}"[:120]
# 4. Pokémon Japan card site: product list with 発売日 (release date)
try:
    t = fetch("https://www.pokemon-card.com/products/").decode("utf-8", "ignore"); n0 = len(items)
    for m in re.finditer(r"(20\d\d)年\s*(\d{1,2})月\s*(\d{1,2})日[^<]{0,40}?発売.{0,400}?", t, re.S):
        try: d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError: continue
        near = t[max(0, m.start() - 600): m.end() + 200]
        nm = re.findall(r"(?:alt|title)=\"([^\"]{4,80})\"|>([^<>]{6,80}(?:パック|デッキ|ボックス|セット|コレクション)[^<>]{0,40})<", near)
        name = next((a or b for a, b in nm if (a or b).strip()), "Japanese product")
        add(d, html.unescape(name), "JP", "product", "pokemon-card.com", "https://www.pokemon-card.com/products/", True)
    status["pokemon-card-jp"] = f"ok ({len(items) - n0} dated)"
except Exception as e: status["pokemon-card-jp"] = f"failed: {e}"[:120]
# de-duplicate (same date + similar name), sort
seen, out = set(), []
for x in sorted(items, key=lambda x: (x["date"], not x["confirmed"])):
    k = (x["date"], re.sub(r"[^a-z0-9]", "", x["name"].lower())[:24])
    if k in seen: continue
    seen.add(k); out.append(x)
json.dump({"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "note": "Upcoming and recent (last 30 days) Pokemon TCG releases. confirmed = official or TCGplayer catalog; news items are reported dates, verify.",
           "sources": status, "items": out}, open(os.path.join(ROOT, "releases.json"), "w"), indent=1, ensure_ascii=False)
print(json.dumps(status, indent=1)); print(len(out), "items")
